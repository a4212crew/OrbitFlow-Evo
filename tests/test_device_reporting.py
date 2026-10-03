from dataclasses import replace
from datetime import datetime, timezone
from io import StringIO
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from unittest.mock import Mock

from openpyxl import Workbook, load_workbook
from paramiko import ChannelException
import pytest

from orbitflow import reporting
from orbitflow.config import ExecutionConfig
from orbitflow.capabilities.interfaces import InterfaceCapabilityError
from orbitflow.models import DeviceContext, InterfaceRecord, InterfaceVlanObservation, VlanObject, VlanState
from orbitflow.targets import load_targets
from orbitflow.transport import DeviceSession, TransportConfig
from orbitflow.vendors.interface_names import canonical_interface_name
from orbitflow.vendors.cisco.vlans import parse_ios_running_config
from orbitflow.vendors.huawei.vlans import parse_huawei_config
from orbitflow.vendors.ubiquiti.vlans import parse_edgeswitch_config
from test_cli_lifecycle import Channel

NOW = datetime(2026, 9, 25, tzinfo=timezone.utc)
CONFIG = TransportConfig('proxy', 'cluster', 'bastion', 'operator')


def context(ip='192.0.2.1', platform='cisco_xe'):
    return DeviceContext('id-' + ip, ip, (ip,), 'router', 'Cisco', platform, 'ASR920',
                         '', 'asr920_evc', ('evc',), '', '', '', NOW, NOW)


def interface(name='Gi0/1', description='uplink'):
    return InterfaceRecord('router', '192.0.2.1', 'cisco_xe', name, description, 'up', 'down', NOW)


def state(*observations, objects=()):
    return VlanState('router', '192.0.2.1', 'cisco_xe', observations, objects, NOW)


@pytest.mark.parametrize('platform,parser,name,terminator,options', [
    ('cisco_ios', parse_ios_running_config, 'Gi0/1', '!', {}),
    ('cisco_xe', parse_ios_running_config, 'Gi0/1', '!', {'evc': True}),
    ('huawei_vrp', parse_huawei_config, 'GE0/1', '#', {}),
    ('ubiquiti_edgeswitch', parse_edgeswitch_config, '0/1', 'exit', {}),
])
@pytest.mark.parametrize('body', [
    '',
    ' description spare\n shutdown\n',
    ' description spare\n no shutdown\n',
    ' description spare\n mtu 1500\n',
    ' description ip address is not forwarding evidence\n',
])
def test_unclassified_configuration_keeps_real_report_row_blank(
    platform, parser, name, terminator, options, body
):
    observations, objects = parser(f'interface {name}\n{body}{terminator}\n', **options)
    assert observations == ()
    assert objects == ()
    actual = replace(interface(name), platform=platform)
    vlans = replace(state(*observations, objects=objects), platform=platform)
    rows, database = reporting.build_rows(context(platform=platform), [actual], vlans)
    assert len(rows) == 1
    row = dict(zip(reporting.INTERFACE_COLUMNS, rows[0]))
    assert row['Interface'] == name
    assert row['Description'] == actual.port_description
    assert (row['Admin Status'], row['Oper Status']) == ('up', 'down')
    for field in ('Port Type', 'Untagged VLAN', 'Tagged VLANs', 'Bridge Domains', 'Service Mappings'):
        assert row[field] == ''
    assert database == []


def test_join_normalized_service_details_and_actual_identity():
    vlans = state(
        InterfaceVlanObservation('GigabitEthernet0/1', port_type='evc',
            tagged_vlans=(100, 200), bridge_domains=('888', '999'),
            service_mappings=('100 -> 888', '200 -> 999')),
        InterfaceVlanObservation('GigabitEthernet0/1.42', port_type='service'),
        objects=(VlanObject('bridge_domain', '999'), VlanObject('vlan', '100', 'users')),
    )
    rows, objects = reporting.build_rows(context(), [interface(), interface('Gi0/2')], vlans)
    summary = dict(zip(reporting.INTERFACE_COLUMNS, rows[0]))
    assert summary['Tagged VLANs'] == '100, 200'
    assert summary['Bridge Domains'] == '888, 999'
    assert summary['Service Mappings'] == '100 -> 888; 200 -> 999'
    assert summary['Description'] == 'uplink'
    assert (summary['Admin Status'], summary['Oper Status']) == ('up', 'down')
    assert len(rows) == 2
    assert objects[0][3:7] == ['bridge_domain', '999', '999', '999']
    assert objects[1][3:7] == ['vlan', '100', '100', 'users']
    assert reporting.build_rows(context(), [], vlans)[0] == []
    assert reporting.build_rows(context(), [interface('Gi0/2'), interface()], replace(vlans, interfaces=tuple(reversed(vlans.interfaces)))) == (rows, objects)


@pytest.mark.parametrize('tags,expected', [('ALL', 'ALL'), ('NONE', 'NONE'), ((), ''), ((10, 20), '10, 20')])
def test_report_preserves_normalized_fields_without_reinterpreting(tags, expected):
    vlans = state(InterfaceVlanObservation('Gi0/1', access_vlan=999, inner_vlan=888,
                  tagged_vlans=tags, port_type='trunk', untagged_vlan='10'))
    rows, _ = reporting.build_rows(context(), [interface()], vlans)
    row = dict(zip(reporting.INTERFACE_COLUMNS, rows[0]))
    assert row['Tagged VLANs'] == expected
    assert row['Untagged VLAN'] == '10'
    assert row['Bridge Domains'] == ''
    assert reporting.build_rows(context(), [], None) == ([], [])


@pytest.mark.parametrize('platform,left,right', [
    ('cisco_ios', 'Gi1/0/1', 'GigabitEthernet1/0/1'),
    ('cisco_xe', 'Te0/1', 'TenGigabitEthernet0/1'),
    ('cisco_xr', 'BE10.3', 'Bundle-Ether10.3'),
    ('cisco_xr', 'Te0/0/0/1.2', 'TenGigE0/0/0/1.2'),
    ('huawei_vrp', 'GE0/1/0.2', 'GigabitEthernet0/1/0.2'),
    ('huawei_vrp', 'Eth0/1/0', 'Ethernet0/1/0'),
    ('ubiquiti_edgeswitch', '0/1', '0/1'),
])
def test_canonical_names(platform, left, right):
    assert canonical_interface_name(platform, left) == canonical_interface_name(platform, right)
    assert canonical_interface_name(platform, left + '.99') != canonical_interface_name(platform, right)


def test_workbook_headers_formatting_and_literal_text(tmp_path):
    path = tmp_path / 'report.xlsx'
    rows, objects = reporting.build_rows(context(), [interface(description='=HYPERLINK("bad")')], state())
    reporting.write_workbook(path, rows, objects, [])
    with_workbook = load_workbook(path)
    try:
        assert with_workbook.sheetnames == ['Interfaces', 'VLAN_Database', 'Run_Errors']
        for sheet, columns in zip(with_workbook, [reporting.INTERFACE_COLUMNS, reporting.DATABASE_COLUMNS, reporting.ERROR_COLUMNS]):
            assert tuple(cell.value for cell in sheet[1]) == columns
            assert sheet.freeze_panes == 'A2'
            assert sheet.auto_filter.ref.endswith(str(sheet.max_row))
            assert sheet.column_dimensions['A'].width >= 18
        assert with_workbook['Interfaces']['F2'].data_type == 's'
        assert with_workbook['Interfaces']['F2'].value == '=HYPERLINK("bad")'
    finally:
        with_workbook.close()


def install_fakes(monkeypatch, failing_stage=None, fail_ip='192.0.2.1'):
    events, closed = [], []
    def connect(ip, credentials, config):
        events.append(('connect', ip))
        assert credentials.password == 'synthetic-password'
        assert config is CONFIG
        if failing_stage == 'connect' and ip == fail_ip:
            raise RuntimeError('synthetic-password')
        def close():
            closed.append(ip)
            if failing_stage == 'disconnect' and ip == fail_ip:
                raise RuntimeError('synthetic-password')
        channel = Channel("router#", {"": "", "terminal length 0": ""})
        session = DeviceSession(Mock(invoke_shell=Mock(return_value=channel)), close)
        session.ip = ip
        return session
    def resolve(session, *, management_ip, cli):
        assert cli.session is session
        session.cli = cli
        events.append(('inventory', session))
        if failing_stage == 'inventory' and management_ip == fail_ip:
            raise RuntimeError('synthetic-password')
        session.context = context(management_ip)
        return session.context
    def collect(stage):
        def run(session, ctx, *, cli):
            assert cli is session.cli
            cli.require_session(session)
            assert session.context is ctx
            assert session.ip == ctx.management_ip
            events.append((stage, session))
            if stage == failing_stage and session.ip == fail_ip:
                raise RuntimeError('synthetic-password token=never-output')
            if stage == 'interfaces':
                return [interface(description='synthetic-password token=never-output')]
            return state(InterfaceVlanObservation('Gi0/1', access_vlan=100), objects=(VlanObject('vlan', '100', 'users', (100,)),))
        return run
    monkeypatch.setattr(reporting, 'connect_device', connect)
    monkeypatch.setattr(reporting, 'DeviceInventoryResolver', Mock(return_value=Mock(resolve=resolve)))
    monkeypatch.setattr(reporting, 'InterfaceService', Mock(return_value=Mock(collect=collect('interfaces'))))
    monkeypatch.setattr(reporting, 'VlanService', Mock(return_value=Mock(collect=collect('vlans'))))
    return events, closed


def test_concurrent_report_owns_device_resources_and_aggregates_on_caller(tmp_path, monkeypatch):
    from threading import Barrier, get_ident
    from orbitflow.config import ExecutionConfig
    events, closed = install_fakes(monkeypatch, 'interfaces')
    barrier = Barrier(2)
    caller = get_ident()
    connect = reporting.connect_device
    def overlapping_connect(*args):
        assert get_ident() != caller
        session = connect(*args)
        barrier.wait(timeout=10)
        return session
    monkeypatch.setattr(reporting, 'connect_device', overlapping_connect)
    writer = reporting.write_workbook
    def write(*args, **kwargs):
        assert get_ident() == caller
        assert len(closed) == 2
        return writer(*args, **kwargs)
    monkeypatch.setattr(reporting, 'write_workbook', write)
    targets = [{'management_ip': f'192.0.2.{i}', 'username': 'synthetic-user',
                'password': 'synthetic-password'} for i in (1, 2)]
    path = reporting.run_report(targets, CONFIG, inventory_path=tmp_path / 'inventory.json',
                                reports_dir=tmp_path, spool_root=tmp_path / 'runs', log_root=tmp_path / 'logs',
                                output=StringIO(), execution_config=ExecutionConfig(2))
    sessions = [value for event, value in events if event == 'inventory']
    assert len({id(session) for session in sessions}) == 2
    assert len({id(session.cli) for session in sessions}) == 2
    assert len({id(session.context) for session in sessions}) == 2
    for session in sessions:
        assert [event for event, value in events if value is session] == ['inventory', 'interfaces', 'vlans']
    assert reporting.DeviceInventoryResolver.call_count == 2
    assert reporting.InterfaceService.call_count == reporting.VlanService.call_count == 2
    workbook = load_workbook(path)
    try:
        assert workbook['Interfaces']['B2'].value == '192.0.2.2'
        assert [row[1] for row in list(workbook['VLAN_Database'].values)[1:]] == ['192.0.2.1', '192.0.2.2']
        assert workbook['Run_Errors']['C2'].value == 'interfaces'
    finally:
        workbook.close()


@pytest.mark.parametrize('stage', ['connect', 'inventory', 'interfaces', 'vlans', 'disconnect', None])
def test_batch_isolation_session_context_and_secrets(tmp_path, monkeypatch, stage):
    events, closed = install_fakes(monkeypatch, stage)
    targets = [{'management_ip': f'192.0.2.{i}', 'username': 'synthetic-user', 'password': 'synthetic-password'} for i in (1, 2)]
    writer = Mock(wraps=reporting.write_workbook)
    monkeypatch.setattr(reporting, 'write_workbook', writer)
    output = StringIO()
    path = reporting.run_report(targets, CONFIG, inventory_path=tmp_path / 'inventory.json',
                                reports_dir=tmp_path, spool_root=tmp_path / 'runs', log_root=tmp_path / 'logs', output=output, clock=lambda: NOW)
    assert writer.call_count == 1
    console = output.getvalue()
    assert 'Interface/VLAN batch started: 2 devices' in console
    assert '[2/2] 192.0.2.2: completed' in console
    assert 'Interface/VLAN batch: workbook generation' in console
    assert f'Devices: 2; stage failures: {int(bool(stage))}; report: {path}' in console
    if stage:
        assert f'[1/2] 192.0.2.1: {stage} failed (RuntimeError)' in console
        assert '[1/2] 192.0.2.1: completed with 1 stage failure(s)' in console
    workbook = load_workbook(path)
    try:
        assert workbook['Run_Errors'].max_row == (2 if stage else 1)
        if stage:
            assert workbook['Run_Errors']['C2'].value == stage
            assert workbook['Run_Errors']['D2'].value == 'RuntimeError'
        assert any(row[1] == '192.0.2.2' for row in workbook['Interfaces'].iter_rows(min_row=2, values_only=True))
        if stage == 'interfaces':
            assert all(row[1] != '192.0.2.1' for row in workbook['Interfaces'].iter_rows(min_row=2, values_only=True))
        if stage == 'vlans':
            assert workbook['Interfaces']['J2'].value is None
        rendered = str([[row for row in sheet.values] for sheet in workbook])
    finally:
        workbook.close()
    log = next((tmp_path / 'logs' / 'reporting').glob('*/interface_vlan_report.log')).read_text()
    failures = [json.loads(line) for line in log.splitlines() if json.loads(line)['level'] == 'ERROR']
    assert len(failures) == bool(stage)
    if stage:
        assert stage in failures[0]['message']
        assert failures[0]['management_ip'] == '192.0.2.1'
        assert failures[0]['exception_chain'][0]['category'] == 'RuntimeError'
        assert failures[0]['exception_chain'][0]['frames']
    for secret in ['synthetic-user', 'synthetic-password', 'never-output']:
        assert secret not in rendered + log + output.getvalue()
    sessions = [value for event, value in events if event == 'inventory']
    for session in sessions:
        collected = [(event, value) for event, value in events if event in {'interfaces', 'vlans'} and value is session]
        assert [event for event, _ in collected] == ([] if stage == 'inventory' and session.ip == '192.0.2.1' else ['interfaces', 'vlans'])
    assert len(closed) == (1 if stage == 'connect' else 2)


@pytest.mark.parametrize('stage', ['interfaces', 'workbook'])
def test_reporting_failure_logs_safe_exception_chain(tmp_path, monkeypatch, stage):
    install_fakes(monkeypatch)

    def fail(*args, **kwargs):
        local_secret = 'local-only-sensitive-value'
        try:
            raise ChannelException(4, 'raw-device-output synthetic-password')
        except ChannelException as exc:
            raise InterfaceCapabilityError('raw-wrapper-error token=never-output') from exc

    if stage == 'interfaces':
        monkeypatch.setattr(reporting, 'InterfaceService', Mock(return_value=Mock(collect=fail)))
    else:
        monkeypatch.setattr(reporting, 'write_workbook', fail)
    targets = [{'management_ip': '192.0.2.1', 'username': 'synthetic-user', 'password': 'synthetic-password'}]
    output = StringIO()

    def run():
        return reporting.run_report(targets, CONFIG, reports_dir=tmp_path, spool_root=tmp_path / 'runs',
                                    log_root=tmp_path / 'logs', output=output, clock=lambda: NOW)

    if stage == 'workbook':
        with pytest.raises(InterfaceCapabilityError):
            run()
        assert 'workbook generation failed (InterfaceCapabilityError)' in output.getvalue()
        assert '; report:' not in output.getvalue()
        rendered = ''
    else:
        workbook = load_workbook(run())
        try:
            rows = list(workbook['Run_Errors'].values)
            assert rows == [reporting.ERROR_COLUMNS,
                            ('192.0.2.1', 'router', 'interfaces', 'InterfaceCapabilityError', NOW.isoformat())]
            rendered = str(rows)
        finally:
            workbook.close()
    log = next((tmp_path / 'logs' / 'reporting').glob('*/interface_vlan_report.log')).read_text()
    failures = [record for line in log.splitlines() if (record := json.loads(line))['level'] == 'ERROR']
    assert len(failures) == 1
    chain = failures[0]['exception_chain']
    assert [item['category'] for item in chain] == ['InterfaceCapabilityError', 'ChannelException']
    for item in chain:
        assert set(item) == {'category', 'errno', 'frames'}
        assert item['frames']
        for frame in item['frames']:
            assert set(frame) == {'file', 'line', 'function'}
    for sensitive in ('raw-device-output', 'synthetic-password', 'raw-wrapper-error',
                      'never-output', 'local-only-sensitive-value', 'raise ChannelException'):
        assert sensitive not in log + rendered + output.getvalue()


def test_shared_loader_preserves_legacy_validation_and_isolates_bad_row(tmp_path, monkeypatch):
    path = tmp_path / 'targets.xlsx'
    workbook = Workbook()
    workbook.active.append(['management_ip', 'username', 'password', 'unused'])
    workbook.active.append(['192.0.2.1', 'synthetic-user', None, 'ignored'])
    workbook.active.append(['192.0.2.2', 'synthetic-user', 'synthetic-password'])
    workbook.save(path)
    with pytest.raises(ValueError, match='row 2'):
        load_targets(path)
    targets = load_targets(path, isolate_invalid=True)
    events, _ = install_fakes(monkeypatch)
    result = reporting.run_report(targets, CONFIG, reports_dir=tmp_path / 'reports', spool_root=tmp_path / 'runs',
                                 log_root=tmp_path / 'logs', output=StringIO(), clock=lambda: NOW)
    workbook = load_workbook(result)
    assert workbook['Run_Errors']['C2'].value == 'input'
    workbook.close()
    assert [value for event, value in events if event == 'connect'] == ['192.0.2.2']


def test_1500_device_batch_writes_once(tmp_path, monkeypatch):
    install_fakes(monkeypatch)
    targets = [{'management_ip': f'device-{i}', 'username': 'synthetic-user', 'password': 'synthetic-password'} for i in range(1500)]
    original = reporting.write_workbook
    def streaming_writer(path, interfaces, database, errors, **kwargs):
        import json
        assert all(iter(rows) is rows for rows in (interfaces, database, errors))
        spool = next((tmp_path / 'runs').iterdir())
        with (spool / 'results.jsonl').open() as source:
            positions = [json.loads(line)['input_position'] for line in source]
        assert sorted(positions) == list(range(1, 1501))
        return original(path, interfaces, database, errors, **kwargs)
    writer = Mock(side_effect=streaming_writer)
    monkeypatch.setattr(reporting, 'write_workbook', writer)
    path = reporting.run_report(targets, CONFIG, reports_dir=tmp_path, spool_root=tmp_path / 'runs', log_root=tmp_path / 'logs',
                                output=StringIO(), clock=lambda: NOW, execution_config=ExecutionConfig(5))
    assert writer.call_count == 1
    workbook = load_workbook(path, read_only=True)
    assert sum(1 for _ in workbook['Interfaces'].values) == 1501
    assert sum(1 for _ in workbook['VLAN_Database'].values) == 1501
    workbook.close()
    assert list((tmp_path / 'runs').iterdir()) == []


def test_command_uses_shared_loader_and_supplied_routing(tmp_path, monkeypatch):
    script = Path(__file__).parents[1] / 'scripts' / 'device_interface_vlan_report.py'
    spec = spec_from_file_location('report_command', script)
    command = module_from_spec(spec)
    spec.loader.exec_module(command)
    targets = [{'management_ip': '192.0.2.1', 'username': 'test-user', 'password': 'test-password'}]
    loader, runner = Mock(return_value=targets), Mock(return_value=tmp_path / 'result.xlsx')
    monkeypatch.setattr(command, 'load_targets', loader)
    monkeypatch.setattr(command, 'run_report', runner)
    command.main(['targets.xlsx', '--proxy', 'proxy:443', '--cluster', 'cluster',
                  '--bastion-host', 'bastion', '--bastion-user', 'operator',
                  '--teleport-key-path', 'identity', '--teleport-cert-path', 'identity-cert.pub',
                  '--reports-dir', str(tmp_path)])
    loader.assert_called_once_with('targets.xlsx', isolate_invalid=True)
    args, kwargs = runner.call_args
    assert args[0] is targets
    assert args[1].proxy == 'proxy:443'
    assert args[1].teleport_key_path == Path('identity')
    assert args[1].teleport_cert_path == Path('identity-cert.pub')
    assert kwargs['reports_dir'] == tmp_path


def test_full_vlan_range_is_not_truncated_by_log_sanitizer(tmp_path):
    rows, _ = reporting.build_rows(context(), [interface()], state(
        InterfaceVlanObservation('Gi0/1', tagged_vlans=tuple(range(1, 4095)))))
    path = tmp_path / 'full-range.xlsx'
    reporting.write_workbook(path, rows, [], [])
    workbook = load_workbook(path)
    assert workbook['Interfaces']['K2'].value == ', '.join(map(str, range(1, 4095)))
    workbook.close()


def test_database_report_preserves_named_domains_and_object_types(tmp_path):
    objects = (
        VlanObject('vlan', '100'),
        VlanObject('bridge_domain', '100'),
        VlanObject('bridge_domain', 'BG/DOMAIN', 'DOMAIN', domain_id='DOMAIN'),
        VlanObject('vsi', 'CUSTOMER'),
    )
    rows, database = reporting.build_rows(context(), [], state(objects=objects))
    assert rows == []
    path = tmp_path / 'domains.xlsx'
    reporting.write_workbook(path, rows, database, [])
    workbook = load_workbook(path)
    try:
        actual = {tuple(row[3:7]) for row in workbook['VLAN_Database'].iter_rows(min_row=2, values_only=True)}
        assert actual == {
            ('vlan', '100', '100', '100'),
            ('bridge_domain', '100', '100', '100'),
            ('bridge_domain', 'BG/DOMAIN', 'DOMAIN', 'DOMAIN'),
            ('vsi', 'CUSTOMER', 'CUSTOMER', 'CUSTOMER'),
        }
    finally:
        workbook.close()


def test_workbook_omits_vlan_one_and_preserves_global_evc_mapping(tmp_path):
    ports, objects = parse_ios_running_config('''vlan 1,10
!
bridge-domain 1
!
bridge-domain 13
 member Gi0/1 service-instance 13
!
bridge-domain 746
 member Gi0/1 service-instance 746 split-horizon group 0
!
interface Gi0/1
 switchport mode trunk
 service instance 13 ethernet
  encapsulation untagged
 service instance 10 ethernet
  encapsulation dot1q 10
  bridge-domain 10
 service instance 746 ethernet
  encapsulation dot1q 746
!
interface Gi0/2
 switchport mode trunk
 switchport trunk allowed vlan 1,10
!''', evc=True)
    rows, database = reporting.build_rows(
        context(), [interface(), interface('Gi0/2')], state(*ports, objects=objects))
    path = tmp_path / 'normalized.xlsx'
    reporting.write_workbook(path, rows, database, [])
    workbook = load_workbook(path)
    try:
        records = list(workbook['Interfaces'].values)
        headers = records[0]
        records = [dict(zip(headers, row)) for row in records[1:]]
        assert len(records) == 2
        assert str(records[0]['Untagged VLAN']) == '13'
        assert 'untagged -> 13' in records[0]['Service Mappings']
        assert records[0]['Tagged VLANs'] == '10, 746'
        assert records[0]['Bridge Domains'] == '13, 10, 746'
        assert '746 -> 746' in records[0]['Service Mappings']
        assert records[1]['Untagged VLAN'] is None
        assert str(records[1]['Tagged VLANs']) == '10'
        assert str(records[1]['Bridge Domains']) == '10'
        assert records[1]['Service Mappings'] == '10 -> 10'
        assert {str(row[5]) for row in workbook['VLAN_Database'].iter_rows(min_row=2, values_only=True)} == {'10', '13', '746'}
    finally:
        workbook.close()


def test_progress_is_flushed_before_each_stage(tmp_path, monkeypatch):
    install_fakes(monkeypatch)

    class FlushedOutput(StringIO):
        flushed = ''

        def flush(self):
            self.flushed = self.getvalue()

    output = FlushedOutput()

    def check(owner, attribute, stage):
        original = getattr(owner, attribute)

        def checked(*args, **kwargs):
            assert output.flushed.splitlines()[-1] == stage
            return original(*args, **kwargs)

        monkeypatch.setattr(owner, attribute, checked)

    label = '[1/1] 192.0.2.1'
    check(reporting, 'connect_device', f'{label}: connect')
    check(reporting.DeviceInventoryResolver.return_value, 'resolve', f'{label}: inventory')
    check(reporting.InterfaceService.return_value, 'collect', f'{label}: interfaces')
    check(reporting.VlanService.return_value, 'collect', f'{label}: vlans')
    check(reporting, 'build_rows', f'{label}: normalize')
    check(reporting, 'write_workbook', 'Interface/VLAN batch: workbook generation')
    reporting.run_report(
        [{'management_ip': '192.0.2.1', 'username': 'synthetic-user', 'password': 'synthetic-password'}],
        CONFIG, reports_dir=tmp_path, spool_root=tmp_path / 'runs', log_root=tmp_path / 'logs', output=output, clock=lambda: NOW)
    assert output.flushed == output.getvalue()


def test_progress_input_normalization_failures_and_empty_batch(tmp_path, monkeypatch):
    install_fakes(monkeypatch)
    monkeypatch.setattr(reporting, 'build_rows', Mock(side_effect=ValueError('raw secret output')))
    output = StringIO()
    reporting.run_report(
        [{'management_ip': 'synthetic-password\nforged', 'password': 'synthetic-password'},
         {'management_ip': '192.0.2.1', 'username': 'synthetic-user', 'password': 'synthetic-password'}],
        CONFIG, reports_dir=tmp_path, spool_root=tmp_path / 'runs', log_root=tmp_path / 'logs', output=output, clock=lambda: NOW)
    console = output.getvalue()
    assert '[1/2] [REDACTED]\\nforged: input failed (ValueError)' in console
    assert '[2/2] 192.0.2.1: normalize failed (ValueError)' in console
    assert 'synthetic-password' not in console
    assert 'raw secret output' not in console
    assert 'stage failures: 2; report:' in console
    output = StringIO()
    reporting.run_report([], CONFIG, reports_dir=tmp_path, spool_root=tmp_path / 'runs', log_root=tmp_path / 'logs', output=output)
    assert 'batch started: 0 devices' in output.getvalue()
    assert 'workbook generation' in output.getvalue()
    assert 'Devices: 0; stage failures: 0; report:' in output.getvalue()


@pytest.mark.parametrize("system", ["windows", "linux"])
@pytest.mark.parametrize("propagate", [True, False])
def test_connection_traceback_is_file_only(tmp_path, monkeypatch, capsys, system, propagate):
    import logging
    from orbitflow import transport
    from orbitflow.transport import linux, windows

    install_fakes(monkeypatch)
    real_connect = transport.connect_device
    monkeypatch.setattr(reporting, "connect_device",
                        lambda *args: real_connect(*args, system=system))
    secret = "synthetic-private-diagnostic"
    error = transport.DeviceConnectionError(secret)

    def fail(*args):
        try:
            raise TimeoutError(secret)
        except TimeoutError as cause:
            logging.getLogger("paramiko.transport").exception("Traceback: " + secret)
            raise error from cause

    monkeypatch.setattr(windows if system == "windows" else linux, "connect_" + system, fail)
    dependency = logging.getLogger("paramiko.transport")
    handler = logging.StreamHandler()
    monkeypatch.setattr(dependency, "handlers", [handler])
    monkeypatch.setattr(dependency, "propagate", propagate)
    previous_level = dependency.level
    output = StringIO()
    try:
        path = reporting.run_report(
            [{"management_ip": "192.0.2.1", "username": "user", "password": secret}],
            CONFIG, reports_dir=tmp_path, spool_root=tmp_path / 'runs', log_root=tmp_path / "logs", output=output)
        assert dependency.handlers == [handler]
        assert dependency.propagate is propagate
        assert dependency.level == previous_level
        assert capsys.readouterr() == ("", "")
        assert "[1/1] 192.0.2.1: connect failed (ConnectionRetryExhausted)" in output.getvalue()
        assert f"stage failures: 1; report: {path}" in output.getvalue()
        logs = "".join(p.read_text() for p in (tmp_path / "logs").rglob("*.log"))
        assert secret not in logs + output.getvalue()
        transport_log = next((tmp_path / "logs" / "transport").glob("*/transport.log"))
        records = [json.loads(line) for line in transport_log.read_text().splitlines()]
        assert records[0]["error_category"] == "SSHDiagnostic"
        assert [item["category"] for item in records[-1]["exception_chain"]] == [
            "ConnectionRetryExhausted", "DeviceConnectionError", "TimeoutError"]
        assert records[-1]["exception_chain"][0]["frames"]
    finally:
        handler.close()


def test_report_spool_retry_without_connections(tmp_path, monkeypatch):
    events, closed = install_fakes(monkeypatch)
    original = reporting.write_workbook
    monkeypatch.setattr(reporting, 'write_workbook', Mock(side_effect=OSError('synthetic-password')))
    with pytest.raises(OSError):
        reporting.run_report(
            [{'management_ip': '192.0.2.1', 'username': 'synthetic-user', 'password': 'synthetic-password'}],
            CONFIG, reports_dir=tmp_path, spool_root=tmp_path / 'runs', log_root=tmp_path / 'logs', output=StringIO())
    spool = next((tmp_path / 'runs').iterdir())
    for file in spool.glob('*.json*'):
        assert 'synthetic-password' not in file.read_text()
    monkeypatch.setattr(reporting, 'connect_device', Mock(side_effect=AssertionError('must not reconnect')))
    monkeypatch.setattr(reporting, 'write_workbook', original)
    path = reporting.export_report_spool(spool, tmp_path / 'retry.xlsx')
    book = load_workbook(path, read_only=True)
    assert sum(1 for _ in book['Interfaces'].values) == 2
    book.close()
    assert not spool.exists()
