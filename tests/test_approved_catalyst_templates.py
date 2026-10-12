"""Milestone 1 signed-off fixtures, exclusively synthetic read-only evidence."""
from dataclasses import asdict
import pytest
from openpyxl import load_workbook
from test_bulk_configuration_v2 import NOW, IP, template, observed
from orbitflow.configuration.v2.planning import request, plan, BulkPlan, load, save
from orbitflow.configuration.v2.workbook import create_input, read_input, export_plan, EXTRA, consume_decisions
from orbitflow.configuration.v2.evidence import scoped_evidence
from orbitflow.configuration.plans import PlanError, canonical
from orbitflow.vendors.configuration_facts import observe_configuration
from orbitflow.vendors.cisco.vlans import parse_ios_running_config, parse_vlan_lookup
from orbitflow.compliance.resolvers import reconstruct_allowed

NAME = 'GigabitEthernet1/0/1'
FAMILIES = ['C3750X', 'C3850X']


def observation(family, config, lookups=None):
    t = template(family, 'Access Port')
    obs = observed(t)
    platform = obs['identity']['platform']
    nodes = observe_configuration(config, platform, preserve_full_evidence=True)
    interfaces, objects = parse_ios_running_config(config)
    obs.update(facts=[asdict(n) for n in nodes], vlans=[asdict(i) for i in interfaces],
               objects=[asdict(o) for o in objects])
    from orbitflow.models import DeviceContext, VlanState
    from orbitflow.compliance.resolvers import resolver_for, evidence
    profile = 'c3750x_switching' if family == 'C3750X' else 'c3850_switching'
    ctx = DeviceContext('one', IP, (IP,), 'example', 'Cisco', platform, family if family == 'C3750X' else 'C3850', family,
                        profile, (), 'EXAMPLE', '1', '', NOW, NOW)
    resolver = resolver_for(ctx)(ctx, VlanState('example', IP, platform, interfaces, objects, NOW, nodes), planning=True)
    resolver.resolve()
    obs.update(audit=list(resolver.rows.values()), evidence=evidence(nodes), problems=resolver.problems,
               methodologies=[])
    if lookups is not None:
        obs['vlan_lookups'] = lookups
    from orbitflow.compliance.vlan import safe_data
    from orbitflow.vendors.configuration_facts import _safe_source
    return safe_data(obs, lambda text: _safe_source(text, platform))


def result(family, function, config, params, lookups=None):
    t = template(family, function)
    r = request(t.id, dict(management_ip=IP, **params))
    obs = observation(family, config, lookups)
    return plan([r], {IP: obs}, now=NOW, decisions={r['row_id']: 'Approve'}).to_dict()['results'][0], r, obs


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('lookup', [None, {'status': 'error', 'name': '', 'operational_status': ''}, {'status': 'unknown', 'name': '', 'operational_status': ''}])
def test_range_lookup_fallback_rename_evidence(family, lookup):
    config = 'vlan 1035-1109\n!\n'
    row, r, obs = result(family, 'VLAN Database', config, dict(vlan_id=1040, name='Customer'), None if lookup is None else {'1040': lookup})
    assert row['commands'] == ['configure terminal', 'vlan 1040', 'name Customer', 'end']
    assert {'VLAN_LOOKUP_FALLBACK', 'VLAN_RENAME_IMPACT'} <= set(row['warnings'])
    assert not row['blockers']
    assert scoped_evidence(r, obs)[0]['excerpt'] == 'vlan 1035-1109'


@pytest.mark.parametrize('family', FAMILIES)
def test_lookup_inactive_noop_absence_and_unknown(family):
    lookup = {'445': dict(status='present', name='Customer', operational_status='suspended')}
    row, _, _ = result(family, 'VLAN Database', 'hostname example\n', dict(vlan_id=445, name='Customer'), lookup)
    assert row['no_op'] and not row['commands'] and 'VLAN_INACTIVE' in row['warnings']
    row, _, _ = result(family, 'VLAN Database', 'hostname example\n', dict(vlan_id=445, name='Customer'), {'445': dict(status='absent', name='', operational_status='')})
    assert not row['no_op'] and not row['blockers']
    t = template(family, 'VLAN Database')
    r = request(t.id, dict(management_ip=IP, vlan_id=445, name='Customer'))
    row = plan([r], {IP: {'status': 'evidence_unavailable'}}, now=NOW).to_dict()['results'][0]
    assert 'VLAN_STATE_UNKNOWN' in row['blockers']
    with pytest.raises(PlanError):
        request(t.id, dict(management_ip=IP, vlan_id=445, name='Customer Site'))


@pytest.mark.parametrize('output,status', [
    ('VLAN Name Status Ports\n---- -------- -------- -----\n445 PPPoE active Te1/0/1,\n                         Te1/0/2, Gi1/0/3\n', 'present'),
    ('% VLAN id 445 not found in current VLAN database', 'absent'),
    ('VLAN 445 does not exist', 'absent'),
    ('% Invalid input detected at marker', 'error'),
    ('% Error fetching VLAN', 'error'), ('garbage', 'unknown'),
])
def test_tabular_lookup(output, status):
    lookup = parse_vlan_lookup(output, 445)
    assert lookup['status'] == status
    if status == 'present':
        assert lookup['name'] == 'PPPoE' and lookup['operational_status'] == 'active'


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('mode,warning,blocker', [
    ('switchport mode access\n switchport trunk allowed vlan 130', 'RESIDUAL_TRUNK_CONFIGURATION', None),
    ('switchport mode dynamic auto', 'UNSPECIFIED_OR_DYNAMIC_ACCESS_MODE', None),
    ('switchport mode dynamic desirable', 'UNSPECIFIED_OR_DYNAMIC_ACCESS_MODE', None),
    ('', 'UNSPECIFIED_OR_DYNAMIC_ACCESS_MODE', None),
    ('switchport mode trunk', None, 'ACCESS_CONVERSION_BLOCKED'),
    ('no switchport', None, 'ACCESS_CONVERSION_BLOCKED'),
])
def test_access_modes_full_cli_shutdown(family, mode, warning, blocker):
    config = f'interface {NAME}\n {mode}\n description Before\n switchport access vlan 130\n shutdown\n spanning-tree portfast\n authentication password DO_NOT_KEEP\n!\n'
    row, r, obs = result(family, 'Access Port', config, dict(interface=NAME, vlan_id=445, description='After'))
    assert row['commands'] == ['configure terminal', f'interface {NAME}', 'description After', 'switchport', 'switchport mode access', 'switchport access vlan 445', 'end']
    assert 'GLOBAL_VLAN_REQUIRED' in row['warnings']
    assert 'no shutdown' not in row['commands']
    if warning:
        assert warning in row['warnings']
    if blocker:
        assert blocker in row['blockers'] and not row['deployment_ready']
    excerpts = '\n'.join(e['excerpt'] for e in scoped_evidence(r, obs))
    assert ' shutdown' in excerpts and ' spanning-tree portfast' in excerpts and excerpts.endswith('!')
    assert 'DO_NOT_KEEP' not in excerpts


@pytest.mark.parametrize('family', FAMILIES)
def test_access_exact_noop_requires_explicit_vlan(family):
    for vlan, noop in [(' switchport access vlan 445\n', True), ('', False)]:
        row, _, _ = result(family, 'Access Port', f'interface {NAME}\n switchport mode access\n{vlan}!\n', dict(interface=NAME, vlan_id=445))
        assert row['no_op'] is noop
        assert bool(row['commands']) != noop


@pytest.mark.parametrize('family', FAMILIES)
def test_lag_access_block_trunk_redirect_description_exact(family):
    config = f'interface {NAME}\n channel-group 1 mode active\n description Physical\n!\ninterface Port-channel1\n switchport mode trunk\n switchport trunk encapsulation dot1q\n switchport trunk allowed vlan 130-135\n description Aggregate\n!\n'
    row, r, obs = result(family, 'Access Port', config, dict(interface=NAME, vlan_id=445))
    assert 'PHYSICAL_PORT_CHANNEL_MEMBER' in row['blockers'] and f'interface {NAME}' in row['commands']
    assert 'interface Port-channel1' in '\n'.join(e['excerpt'] for e in scoped_evidence(r, obs))
    row, _, _ = result(family, 'Trunk Port', config, dict(interface=NAME, action='Add', vlans=[130, 445]))
    assert row['resolved_target'] == 'Port-channel1'
    assert 'interface Port-channel1' in row['commands'] and 'switchport trunk allowed vlan add 130,445' in row['commands']
    row, _, _ = result(family, 'Interface Description', config, dict(interface=NAME, description='After'))
    assert row['commands'] == ['configure terminal', f'interface {NAME}', 'description After', 'end']
    assert not row['blockers']
    row, _, _ = result(family, 'Trunk Port', config.split('interface Port-channel1')[0], dict(interface=NAME, action='Replace', vlans=[445]))
    assert 'PORT_CHANNEL_OWNER_UNRESOLVED' in row['blockers']
    t = template(family, 'Trunk Port')
    a = request(t.id, dict(management_ip=IP, interface=NAME, action='Replace', vlans=[445]))
    b = request(t.id, dict(management_ip=IP, interface='Port-channel1', action='Replace', vlans=[545]), row=4)
    rows = plan([a,b], {IP: obs}, now=NOW).to_dict()['results']
    assert all('ORDERED_RESOURCE_OVERLAP' in row['findings'] and row['conflicting_rows'] for row in rows)


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('action,baseline,vlans,noop,blocker', [
    ('Add', ' switchport trunk allowed vlan 130-135\n switchport trunk allowed vlan remove 133\n switchport trunk allowed vlan add 445\n', [130,445], True, None),
    ('Add', ' switchport trunk allowed vlan 130-135\n switchport trunk allowed vlan remove 133\n', [130,133], False, None),
    ('Add', '', [445], True, 'ADD_REQUIRES_EXPLICIT_BASELINE'),
    ('Remove', '', [445], False, None),
    ('Remove', ' switchport trunk allowed vlan remove 445\n', [445], True, None),
    ('Remove', ' switchport trunk allowed vlan none\n', [445], True, None),
    ('Replace', '', [445], False, None),
])
def test_trunk_ordered_all_actions(family, action, baseline, vlans, noop, blocker):
    config = f'interface {NAME}\n switchport mode trunk\n switchport trunk encapsulation dot1q\n{baseline}!\n'
    row, _, _ = result(family, 'Trunk Port', config, dict(interface=NAME, action=action, vlans=vlans))
    assert row['no_op'] is noop
    if blocker:
        assert blocker in row['blockers']
    else:
        assert not row['blockers']
    if not noop:
        fragment = '' if action == 'Replace' else action.lower()+' '
        assert 'switchport trunk allowed vlan '+fragment+','.join(map(str,vlans)) in row['commands']
    if action in {'Replace','Remove'} and not noop:
        assert 'SERVICE_IMPACT_REVIEW' in row['warnings']


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('mode,blocked', [('', False), ('switchport mode access', True), ('no switchport', True)])
def test_trunk_conversion_encapsulation(family, mode, blocked):
    row, _, _ = result(family, 'Trunk Port', f'interface {NAME}\n {mode}\n shutdown\n!\n', dict(interface=NAME, action='Replace', vlans=[445]))
    assert ('TRUNK_CONVERSION_BLOCKED' in row['blockers']) is blocked
    assert ('switchport trunk encapsulation dot1q' in row['commands']) == (family == 'C3750X')
    assert 'no shutdown' not in row['commands']


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('target', [NAME, 'Port-channel1', 'Vlan1035', NAME+'.100'])
def test_description_exact_target_noop_unrelated(family, target):
    config = f'interface {target}\n switchport mode access\n switchport access vlan 445\n switchport trunk allowed vlan 545\n shutdown\n!\n'
    row, _, _ = result(family, 'Interface Description', config, dict(interface=target, description='After'))
    assert row['commands'] == ['configure terminal', f'interface {target}', 'description After', 'end']
    assert not row['blockers']
    row, _, _ = result(family, 'Interface Description', config.replace(' shutdown', ' description After\n shutdown'), dict(interface=target, description='After'))
    assert row['no_op'] and not row['commands']


def test_symbolic_all_operations():
    assert reconstruct_allowed([('allowed_remove', [445]), ('allowed_add', [445,545])]) == dict(all=True, values=[], explicit=True)
    assert reconstruct_allowed([('allowed_except', [130,131]), ('allowed_remove', [132])]) == dict(all=True, values=[130,131,132], explicit=True)


@pytest.mark.parametrize('family', FAMILIES)
def test_invalid_rows_retained_fields_safe_continuation(family, tmp_path):
    t = template(family, 'Access Port')
    source = tmp_path/'input.xlsx'
    create_input(source)
    book = load_workbook(source)
    sheet = book[t.sheet]
    for n, values in enumerate([(IP, NAME, 445, None), (IP, 'Gi1/0/1', 1002, 'password DO_NOT_KEEP'), (IP, NAME, 545, None)], 3):
        for col,value in enumerate(values,1):
            sheet.cell(n,col,value)
    book.save(source)
    rows = read_input(source)
    assert len(rows) == 2 and len(rows.errors) == 1
    assert {'interface', 'vlan_id', 'description'} <= {s.split(':')[0] for s in rows.errors[0]['details']}
    original = plan(rows, {IP: observation(family, f'interface {NAME}\n!\n')}, now=NOW)
    dest = tmp_path/'plan.xlsx'
    export_plan(original,dest)
    book = load_workbook(dest)
    sheet = book[t.sheet]
    extra = lambda label,row: sheet.cell(row,len(t.columns)+EXTRA.index(label)+1).value
    assert sheet.cell(4,2).value == 'Gi1/0/1' and sheet.cell(4,3).value == '1002'
    assert extra('Validation Status',4) == 'Invalid' and extra('Proposed CLI',4) is None
    assert 'row 5' in extra('Error Details',3) and 'row 3' in extra('Error Details',5)
    assert 'DO_NOT_KEEP' not in canonical(original.to_dict())
    save(original,tmp_path/'plan.json')
    assert load(tmp_path/'plan.json').digest == original.digest
    assert consume_decisions(original,dest,expected_digest=original.digest,now=NOW).digest == original.digest
    with pytest.raises(PlanError):
        export_plan(original,dest)

@pytest.mark.parametrize('family', FAMILIES)
def test_optional_trunk_changes_do_not_repeat_membership(family):
    config = f'interface {NAME}\n switchport mode trunk\n switchport trunk encapsulation dot1q\n switchport trunk allowed vlan 445\n description Before\n!\n'
    row, _, _ = result(family, 'Trunk Port', config, dict(interface=NAME, action='Add', vlans=[445], description='After', native_vlan=545))
    assert row['commands'] == ['configure terminal', f'interface {NAME}', 'description After', 'switchport trunk native vlan 545', 'end']


@pytest.mark.parametrize('family', FAMILIES)
def test_malformed_operations_and_lag_conflicts_block(family):
    config = f'interface {NAME}\n switchport mode trunk\n switchport trunk allowed vlan frobnicate 445\n!\n'
    row, _, _ = result(family, 'Trunk Port', config, dict(interface=NAME, action='Replace', vlans=[445]))
    assert 'UNSUPPORTED_ALLOWED_VLAN_OPERATION' in row['blockers'] and row['commands']
    config = f'interface {NAME}\n channel-group 1 mode active\n switchport mode access\n switchport access vlan 445\n!\ninterface Port-channel1\n switchport mode trunk\n switchport trunk encapsulation dot1q\n switchport trunk allowed vlan 545\n!\n'
    row, _, _ = result(family, 'Trunk Port', config, dict(interface=NAME, action='Replace', vlans=[445]))
    assert 'PORT_CHANNEL_CONFIG_CONFLICT' in row['blockers']


def test_all_invalid_workbook_exports_without_observation(tmp_path):
    t = template('C3750X', 'VLAN Database')
    source = tmp_path/'input.xlsx'
    create_input(source)
    book = load_workbook(source)
    book[t.sheet].append([IP, 1002, 'Invalid Name'])
    book.save(source)
    rows = read_input(source)
    assert not rows and rows.errors
    original = plan(rows, now=NOW)
    export_plan(original, tmp_path/'plan.xlsx')
    assert not original.to_dict()['observations']


def test_lookup_service_borrows_cli_and_uses_only_show(monkeypatch):
    from orbitflow.capabilities.vlans import VlanService, VlanCapabilityError
    from orbitflow.models import DeviceContext
    ctx = DeviceContext('one', IP, (IP,), 'example', 'Cisco', 'cisco_xe', 'C3850', 'C3850',
                        'c3850_switching', (), 'EXAMPLE', '1', '', NOW, NOW)
    session = object()
    calls = []
    class CLI:
        def require_session(self, supplied):
            assert supplied is session
        def configure(self, **kwargs):
            assert kwargs['paging_command'] == 'terminal length 0'
        def run_command(self, command, **kwargs):
            calls.append(command)
            assert command == 'show vlan id 445'
            return 'VLAN Name Status Ports\n445 Customer active Gi1/0/1,\n                         Gi1/0/2'
    assert VlanService().lookup(session, ctx, 445, cli=CLI())['name'] == 'Customer'
    assert calls == ['show vlan id 445']
    with pytest.raises(VlanCapabilityError):
        VlanService().lookup(session, ctx, '445', cli=CLI())
    for stage in ('setup', 'command'):
        class FailedCLI(CLI):
            def configure(self, **kwargs):
                if stage == 'setup':
                    raise RuntimeError('password MUST_NOT_PERSIST')
                super().configure(**kwargs)
            def run_command(self, command, **kwargs):
                raise RuntimeError('password MUST_NOT_PERSIST')
        lookup = VlanService().lookup(session, ctx, 445, cli=FailedCLI())
        assert lookup == dict(status='error', name='', operational_status='')

@pytest.mark.parametrize('family', FAMILIES)
def test_explicit_unreliable_configuration_cannot_fallback(family):
    t = template(family, 'VLAN Database')
    r = request(t.id, dict(management_ip=IP, vlan_id=445, name='Customer'))
    obs = observation(family, 'vlan 445\n name Customer\n!\n', {'445': dict(status='error', name='', operational_status='')})
    obs['configuration_reliable'] = False
    row = plan([r], {IP: obs}, now=NOW).to_dict()['results'][0]
    assert 'VLAN_STATE_UNKNOWN' in row['blockers'] and not row['no_op']
