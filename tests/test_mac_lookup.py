"""Offline owner-supplied MAC shapes and independent capability contracts."""
from types import SimpleNamespace as NS
from contextlib import contextmanager
import pytest
from openpyxl import load_workbook
from orbitflow.capabilities.mac import normalize_mac, parse_mac_table, resolve_attachment, MacService
from orbitflow.capabilities.bridge_domains import parse_bridge_domains
from orbitflow.capabilities.mac_forwarding import enrich
from orbitflow.mac_lookup import resolve_target, validate_vlan, run_lookup, export_mac_spool, MAIN_COLUMNS


@pytest.mark.parametrize('value', ['AABB.CCDD.EEFF', 'AA:BB:CC:DD:EE:FF', 'aabb-ccdd-eeff'])
def test_normalize(value):
    assert normalize_mac(value) == 'aa:bb:cc:dd:ee:ff'


@pytest.mark.parametrize('value', ['', 'aabbccddeeff', 'aa-bb-cc-dd-ee-ff', 'aabb.ccdd.ee', 'aa:bb:cc:dd:ee:gg', 'aa:bb:cc-dd:ee:ff'])
def test_invalid(value):
    with pytest.raises(ValueError):
        normalize_mac(value)


IOS = '''Vlan Mac Address Type Ports
All 0100.0ccc.cccc STATIC CPU
1100 d401.c312.96f0 DYNAMIC Gi1/0/46
545 00eb.d543.8472 STATIC Vl545
2437 0ea2.03b1.2437 DYNAMIC Te1/0/12
4001 9a49.254f.1f0f DYNAMIC Gi0/24+Efp3999
1201 e8a5.5acc.fed0 DYNAMIC Po2
Total Mac Addresses for this criterion: 30'''
XR = '''Mac Address Type Learned from/Filtered on LC learned Resync Age/Last Change Mapped to
789a.18d9.0fbc dynamic Te0/0/0/19.2440 N/A 17 Oct 10:36:24 N/A
ae78.d132.d87b EVPN (192.0.2.20, 2445) N/A 17 Oct 10:36:24 N/A
9a49.254f.1f0f dynamic (192.0.2.20, 4001) N/A 17 Oct 10:36:24 N/A
4464.3cd7.5481 routed BD id: 0 N/A N/A N/A'''
BRIDGE = '''Bridge group: VLAN545, bridge-domain: BD_VLAN545, id: 0, state: up, ShgId: 0, MSTi: 0
 List of ACs:
 BV545, state: up, BVI MAC addresses: 1
 Te0/0/0/19.545, state: up, Static MAC addresses: 0
Bridge group: LBB-PPPOE, bridge-domain: LBB-PPPOE, id: 2, state: up, ShgId: 0, MSTi: 0
 List of ACs:
 Te0/0/0/19.445, state: up, Static MAC addresses: 0
 List of Access PWs:
 Neighbor 192.0.2.20 pw-id 2445, state: up, Static MAC addresses: 0
 Neighbor 192.0.2.21 pw-id 2445, state: down, Static MAC addresses: 0, backup'''


def test_ios_totals_and_local_selection():
    table = parse_mac_table(IOS, 'cisco_ios')
    assert table.total == 30
    assert len(table.entries) == 6
    assert table.lookup(domain=545).total == 1
    assert table.lookup(mac='9A49.254F.1F0F').entries[0].attachment == 'Gi0/24+Efp3999'
    assert not table.lookup(interface='Gi0/24', platform='cisco_ios').entries
    assert table.lookup(domain=22).total == 0


def test_asr_and_empty():
    output = 'Nile Mac Address Entries\nBD mac addr type ports\nALL 0100.0ccc.cccc STATIC CPU\n2200 e8a5.5acc.fed0 DYNAMIC Gi0/0/1.Efp2200'
    assert parse_mac_table(output, 'cisco_xe').total == 2
    assert parse_mac_table('Vlan Mac Address Type Ports\n----', 'cisco_ios').total == 0


def test_huawei_and_edge():
    output = '''MAC address table of slot 0:
MAC Address VLAN/ PEVLAN CEVLAN Port Type LSP/LSR-ID
            VSI/SI MAC-Tunnel
0ea2-03b1-2435 SUPERLOOP2-PPPOE-2435 - - GE0/2/5.303 dynamic 0/0
744d-289f-92db 745 - - GE0/2/6 dynamic 0/-
Total matching items on slot 0 displayed = 153'''
    table = parse_mac_table(output, 'huawei_vrp')
    assert table.total == 2 and table.scoped_totals == (('slot 0', 153),)
    assert table.entries[0].domain == 'SUPERLOOP2-PPPOE-2435'
    edge = parse_mac_table('VLAN ID MAC Address Interface IfIndex Status\n445 00:26:DE:13:35:FE 0/8 8 Learned\n545 B4:FB:E4:19:9A:6E 5/1 65 Management', 'ubiquiti_edgeswitch')
    assert edge.total == 2 and edge.entries[0].kind == 'dynamic'
    assert edge.entries[1].kind == 'management' and edge.entries[1].ifindex == '65'


@pytest.mark.parametrize('text', ['', 'garbage', 'Vlan Mac Address Type Ports\nbroken row', IOS + '\n--More--', IOS + '\n% Invalid input'])
def test_reject_incomplete(text):
    with pytest.raises(ValueError):
        parse_mac_table(text, 'cisco_ios')


def test_xr_exact_scope():
    table = parse_mac_table(XR, 'cisco_xr')
    assert table.total == 4 and table.entries[1].attachment == '(192.0.2.20, 2445)'
    bridge = parse_bridge_domains(BRIDGE)
    assert bridge.for_destination('BD id: 0')[0].name == 'BD_VLAN545'
    assert bridge.for_destination('(192.0.2.20, 2445)')[0].name == 'LBB-PPPOE'
    assert bridge.domains[1].attachments[-1].backup
    assert bridge.domains[0].attachments[0].bvi_count == 1
    assert bridge.domains[0].attachments[0].static_count is None
    assert bridge.lookup(interface='TenGigE0/0/0/19.545')[0].internal_id == '0'
    assert bridge.lookup(interface='BVI545')[0].internal_id == '0'
    ambiguous = parse_bridge_domains(BRIDGE + '\n' + BRIDGE)
    assert len(ambiguous.for_destination('(192.0.2.20, 2445)')) == 2


@pytest.mark.parametrize('platform,name,attachment,expected', [
    ('cisco_ios', 'Gi0/24', 'Gi0/24+Efp3999', 'GigabitEthernet0/24'),
    ('cisco_xe', 'Te1/0/12', 'Te1/0/12', 'TenGigabitEthernet1/0/12'),
    ('cisco_xr', 'Te0/0/0/19', 'Te0/0/0/19.2440', 'TenGigE0/0/0/19'),
    ('ubiquiti_edgeswitch', '0/8', '0/8', '0/8')])
def test_physical(platform, name, attachment, expected):
    result = resolve_attachment(attachment, platform, [NS(port_name=name)])
    assert result.physical == expected and result.port_type == 'Unknown'
    assert resolve_attachment(attachment, platform, []).physical == ''


def test_domain_not_vlan():
    table = parse_mac_table('BD mac addr type ports\n4001 9a49.254f.1f0f DYNAMIC Gi0/24+Efp3999', 'cisco_ios')
    context = NS(platform='cisco_ios', device_family='ME3600X')
    detail = NS(interface_name='GigabitEthernet0/24', service_details=(), service_mappings=('445 -> 4001',), port_type='evc')
    from orbitflow.vendors.configuration_facts import observe_configuration
    facts = observe_configuration('interface GigabitEthernet0/24\n service instance 3999 ethernet\n  encapsulation dot1q 445\n  bridge-domain 4001', 'cisco_ios')
    rows = enrich(table, context, [NS(port_name='Gi0/24')], NS(interfaces=[detail], configuration=facts))
    assert rows[0].vlans == (445,) and rows[0].resolution.port_type == 'Unknown'
    assert enrich(table, context)[0].vlans == ()


def test_target_and_validation():
    target = dict(management_ip='192.0.2.1', username='fixture', password='private-fixture')
    assert resolve_target([target], '192.0.2.1') is target
    for targets in ([], [target, target]):
        with pytest.raises(ValueError):
            resolve_target(targets, '192.0.2.1')
    for vlan in ('0', '4095', 'x', True):
        with pytest.raises(ValueError):
            validate_vlan(vlan)


def test_batch_spool_isolation_and_recovery(tmp_path, monkeypatch):
    import orbitflow.mac_lookup as app
    def collect(target, *args, **kwargs):
        if target['management_ip'] == '192.0.2.2':
            raise ValueError('private-fixture')
        return [[['192.0.2.1', '=formula', 'C3750X', 'GigabitEthernet1/1', 'trunk', 'aa:bb:cc:dd:ee:ff']] * 4, [], [['192.0.2.1', 'table', 30]], []]
    monkeypatch.setattr(app, 'collect_device', collect)
    targets = [dict(management_ip=f'192.0.2.{i}', username='fixture', password='private-fixture') for i in (1, 2)]
    path = run_lookup(targets, None, reports_dir=tmp_path/'reports', spool_root=tmp_path/'runs', inventory_path=tmp_path/'inventory.json', log_root=tmp_path/'logs')
    book = load_workbook(path)
    assert tuple(c.value for c in book['MAC Addresses'][1]) == MAIN_COLUMNS
    assert book['MAC Addresses'].max_row == 5
    assert book['MAC Addresses']['B2'].data_type == 's'
    assert book['Run Errors'].max_row == 2
    book.close()
    spool = next((tmp_path/'runs').iterdir())
    export_mac_spool(spool, tmp_path/'recovered.xlsx')
    assert (tmp_path/'recovered.xlsx').exists()
    assert all('private-fixture' not in p.read_text(errors='ignore') for p in spool.rglob('*') if p.is_file())


@pytest.mark.parametrize('platform,command,output', [
    ('cisco_ios', 'show mac address-table', IOS),
    ('cisco_xe', 'show mac address-table', 'BD mac addr type ports'),
    ('cisco_xr', 'show l2vpn forwarding bridge-domain mac-address location 0/RP0/CPU0', XR),
    ('huawei_vrp', 'display mac-address', 'MAC Address VLAN/ PEVLAN CEVLAN Port Type\nVSI/SI MAC-Tunnel'),
    ('ubiquiti_edgeswitch', 'show mac-addr-table all', 'VLAN ID MAC Address Interface IfIndex Status')])
def test_independent_borrowed_collection(monkeypatch, platform, command, output):
    import orbitflow.vendors.mac_tables as vendor
    calls = []
    shell = NS(run_command=lambda cmd, **kw: calls.append(cmd) or output)
    @contextmanager
    def opened(session, observed_platform, **kwargs):
        assert kwargs['cli'] is shell and session == 'session' and platform == observed_platform
        yield shell
    monkeypatch.setattr(vendor, 'operational_cli', opened)
    MacService().collect('session', NS(platform=platform), cli=shell)
    assert calls == [command]


def test_exact_service_conflicts_and_wrong_efp():
    from orbitflow.vendors.configuration_facts import observe_configuration
    from orbitflow.capabilities.mac_forwarding import exact_efp_vlans
    facts = observe_configuration('interface GigabitEthernet0/24\n service instance 3999 ethernet\n  encapsulation dot1q 445\n  bridge-domain 4001', 'cisco_ios')
    assert exact_efp_vlans(facts, 'cisco_ios', 'Gi0/24', '3999', '4001') == (445,)
    assert exact_efp_vlans(facts, 'cisco_ios', 'Gi0/24', '4001', '4001') == ()
    assert exact_efp_vlans(facts, 'cisco_ios', 'Gi0/24', '3999', '445') == ()


def test_hybrid_aggregate_nonphysical_and_huawei():
    interfaces = [NS(port_name='Po2'), NS(port_name='GigabitEthernet0/2/6')]
    vlans = NS(interfaces=[NS(interface_name='Port-channel2', port_type='hybrid')])
    result = resolve_attachment('Po2', 'cisco_ios', interfaces, vlans)
    assert result.classification == 'aggregate' and result.physical == 'Port-channel2' and result.port_type == 'hybrid'
    assert resolve_attachment('GE0/2/6', 'huawei_vrp', interfaces).physical == 'GigabitEthernet0/2/6'
    for attachment in ('CPU', 'Vl545', '(192.0.2.20, 2445)', 'BD id: 0'):
        assert not resolve_attachment(attachment, 'cisco_xr', interfaces).physical
    assert not resolve_attachment('5/1', 'ubiquiti_edgeswitch', [NS(port_name='5/1')]).physical


def test_xr_vlan_requires_explicit_relationship_and_unique_join():
    from orbitflow.capabilities.mac_forwarding import lookup_vlan
    table = parse_mac_table(XR, 'cisco_xr')
    bridge = parse_bridge_domains(BRIDGE)
    profile = NS(interface_name='TenGigE0/0/0/19.445', service_details=(), service_mappings=('860 -> LBB-PPPOE',), port_type='service')
    context = NS(platform='cisco_xr', device_family='NCS540')
    enriched = enrich(table, context, [], NS(interfaces=[profile], configuration=()), bridge)
    assert [r.entry.mac for r in lookup_vlan(enriched, 860)] == ['ae:78:d1:32:d8:7b']
    assert not lookup_vlan(enriched, 445) and not lookup_vlan(enriched, 2445)
    assert not lookup_vlan(enrich(table, context, [], NS(interfaces=[profile]), parse_bridge_domains(BRIDGE+'\n'+BRIDGE)), 860)


def test_export_failure_retains_spool(tmp_path, monkeypatch):
    import orbitflow.mac_lookup as app
    monkeypatch.setattr(app, 'collect_device', lambda *a, **k: [[], [], [], []])
    real = app.write_tables
    def fail(*args, **kwargs):
        raise OSError('disk unavailable')
    monkeypatch.setattr(app, 'write_tables', fail)
    with pytest.raises(OSError):
        run_lookup([dict(management_ip='192.0.2.1')], None, reports_dir=tmp_path/'reports', spool_root=tmp_path/'runs', inventory_path=tmp_path/'inventory.json', log_root=tmp_path/'logs')
    monkeypatch.setattr(app, 'write_tables', real)
    export_mac_spool(next((tmp_path/'runs').iterdir()), tmp_path/'recovered.xlsx')
    assert (tmp_path/'recovered.xlsx').exists()


def test_one_session_partial_enrichment_and_no_match(monkeypatch):
    import orbitflow.mac_lookup as app
    calls, session, shell = [], object(), object()
    @contextmanager
    def connect(*args, **kwargs):
        calls.append('connect')
        yield session
        calls.append('disconnect')
    @contextmanager
    def cli(observed_session):
        assert observed_session is session
        yield shell
    context = NS(platform='cisco_ios', device_family='C3750X', hostname='sample', hardware_model='WS-C3750X')
    def collect(self, observed_session, observed_context, **kwargs):
        assert observed_session is session and observed_context is context and kwargs['cli'] is shell
        return parse_mac_table(IOS, 'cisco_ios')
    def failed(*args, **kwargs):
        raise ValueError('secret-bearing-device-diagnostic')
    monkeypatch.setattr(app, 'connect_device', connect)
    monkeypatch.setattr(app, 'DeviceCLI', cli)
    monkeypatch.setattr(app.DeviceInventoryResolver, 'resolve', lambda *a, **kw: context)
    monkeypatch.setattr(app.MacService, 'collect', collect)
    monkeypatch.setattr(app.InterfaceService, 'collect', failed)
    monkeypatch.setattr(app.VlanService, 'collect', failed)
    target = dict(management_ip='192.0.2.1', username='fixture', password='private-fixture')
    result = app.collect_device(target, None, None, mac='d401.c312.96f0')
    assert len(result[0]) == 1 and result[0][0][2] == 'WS-C3750X'
    assert result[0][0][3:5] == ['', 'Unknown']
    assert len(result[3]) == 2 and 'secret-bearing' not in repr(result)
    assert calls == ['connect', 'disconnect']
    empty = app.collect_device(target, None, None, mac='aaaa.bbbb.cccc')
    assert empty[0] == [] and empty[2][1][-1] == 0


def test_duplicate_domains_and_parent_lookup():
    table = parse_mac_table('Vlan Mac Address Type Ports\n100 aabb.ccdd.eeff DYNAMIC Gi0/1.100\n200 aabb.ccdd.eeff DYNAMIC Gi0/1.200', 'cisco_ios')
    assert table.lookup(mac='aabb.ccdd.eeff').total == 2
    assert table.lookup(interface='GigabitEthernet0/1', platform='cisco_ios', include_children=True).total == 2
    assert table.lookup(interface='GigabitEthernet0/1.100', platform='cisco_ios').total == 1


def test_cli_offline_export_does_not_load_profile(tmp_path, monkeypatch):
    import orbitflow.mac_cli as cli
    monkeypatch.setattr(cli, 'load_profile', lambda *a: pytest.fail('offline profile'))
    seen = []
    monkeypatch.setattr(cli, 'export_mac_spool', lambda *a, **k: seen.append((a, k)) or tmp_path/'out.xlsx')
    cli.main(['export', 'retained-run', str(tmp_path/'out.xlsx')])
    assert seen[0][1] == {'allow_partial': False}


def test_unresolved_local_attachment_cannot_borrow_sibling_vlan():
    table = parse_mac_table('Mac Address Type Learned from/Filtered on LC learned Resync Age/Last Change Mapped to\naabb.ccdd.eeff dynamic Te0/0/0/19.545 N/A N/A N/A', 'cisco_xr')
    profile = NS(interface_name='TenGigE0/0/0/20.860', service_details=(), service_mappings=('860 -> BD_VLAN545',), port_type='service')
    bridge = parse_bridge_domains(BRIDGE.replace('Te0/0/0/19.545, state:', 'Te0/0/0/20.860, state: up, Static MAC addresses: 0\n Te0/0/0/19.545, state:'))
    rows = enrich(table, NS(platform='cisco_xr', device_family='NCS540'), [], NS(interfaces=[profile]), bridge)
    assert rows[0].vlans == ()
    assert resolve_attachment('Tunnel1', 'cisco_ios', [NS(port_name='Tunnel1')]).physical == ''


def test_xr_preserves_reported_scope_and_rejects_truncated_row():
    table = parse_mac_table('Bridge-domain: supplied-scope, id: 0\n' + XR, 'cisco_xr')
    assert table.entries[0].scope == 'Bridge-domain: supplied-scope, id: 0'
    with pytest.raises(ValueError):
        parse_mac_table(XR.splitlines()[0] + '\naabb.ccdd.eeff dynamic Te0/0/0/19.545 N/A N/A', 'cisco_xr')


def test_actual_configured_parent_is_identity_but_service_reference_is_not():
    from orbitflow.vendors.configuration_facts import observe_configuration
    actual = observe_configuration('interface GigabitEthernet0/24\n service instance 3999 ethernet\n  encapsulation dot1q 445\n  bridge-domain 4001', 'cisco_ios')
    reference = observe_configuration('bridge-domain 4001\n member GigabitEthernet0/24 service-instance 3999', 'cisco_ios')
    assert resolve_attachment('Gi0/24+Efp3999', 'cisco_ios', [], NS(interfaces=[], configuration=actual)).physical == 'GigabitEthernet0/24'
    assert resolve_attachment('Gi0/24+Efp3999', 'cisco_ios', [], NS(interfaces=[], configuration=reference)).physical == ''
