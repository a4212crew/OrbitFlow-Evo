"""Freshness, isolation and log safety regressions; synthetic devices only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext, contextmanager
from dataclasses import replace
from datetime import timedelta
import json
import math
import socket
from types import SimpleNamespace

import pytest

from orbitflow.configuration import execution as ex, execution_observation as observation_cache
from orbitflow.configuration.v2.catalogue import CATALOGUE
from orbitflow.configuration.v2.planning import request, plan
from orbitflow.logging import module_logger, sanitize_text
from orbitflow.models import InterfaceRecord, VlanState
from orbitflow.timing import profiling, stage, device_wait, correlation
from orbitflow.vendors.common import DeviceCLI, InteractiveCLIError
from orbitflow.capabilities import InterfaceService, VlanService
from test_configuration_execution import context, NOW, IP, run_prepared, WorkerCLI
from test_configuration_execution_performance import synthetic
from test_configuration_execution_performance import SyntheticChannel
from test_interface_capability import CASES
from orbitflow.transport import DeviceSession, DeviceCredentials


SUPPORTED = [t for t in CATALOGUE if t.family in {'C3750X', 'C3850X', 'EdgeSwitch'}]


@pytest.mark.parametrize('template', SUPPORTED, ids=lambda t: t.id)
def test_every_template_fresh_input_and_planning_equivalence(template, monkeypatch):
    ctx = context(template.family)
    inputs = dict(management_ip=IP)
    if template.function == 'VLAN Database':
        inputs.update(vlan_id=445, name='Customer')
    else:
        inputs['interface'] = '0/1' if template.family == 'EdgeSwitch' else 'GigabitEthernet1/0/1'
        if template.function == 'Interface Description':
            inputs['description'] = 'new'
        elif template.function == 'Access Port':
            inputs['vlan_id'] = 445
        elif template.function == 'Trunk Port':
            inputs.update(action='Replace', vlans=[445])
        else:
            inputs.update(action='Add/Change', pvid=445, tagged_vlans='445')
    row = request(template.id, inputs)
    projections = []
    original_snapshot = ex.snapshot
    monkeypatch.setattr(ex, 'snapshot', lambda *a: projections.append(1) or original_snapshot(*a))
    comparisons = []
    counts = []
    for optimized in (False, True):
        session, channel = synthetic(template.family)
        if template.function == 'Trunk Port':
            channel.config_override = 'hostname fixture\nvlan 445\n name Customer\n!\ninterface Gi1/0/1\n description original\n switchport mode trunk\n switchport trunk allowed vlan 445,545\n!\nend\n'
        with session, DeviceCLI(session) as cli:
            cli._reuse_session_setup = optimized
            with observation_cache.observation_scope(session, cli) if optimized else nullcontext():
                values = [ex._observe(session, ctx, cli, [dict(request=row)], 30) for _ in range(2)]
                # Reused deterministic projection has exactly the same output as
                # recomputing the factory from the latest full normalized reads.
                for value in values:
                    for item in value['interfaces']:
                        item['collection_time'] = NOW.isoformat()
                    value['observed_at'] = NOW.isoformat()
                assert values[0] == values[1]
                comparisons.append((values[1], plan([row], {IP: values[1]}, now=NOW, decisions={row['row_id']: 'Approve'}).to_dict()['results']))
                assert comparisons[-1][1][0]['deployment_ready'], comparisons[-1][1][0]['findings']
                counts.append(channel.sent)
    assert comparisons[0] == comparisons[1]
    assert len(projections) == 3  # two baseline computations, one memoized
    for sent in counts:
        assert sent.count('show running-config') == 2
        assert sum(c.startswith('show vlan') for c in sent) == (0 if template.function == 'Interface Description' else 2)
    assert len(counts[1]) < len(counts[0])


def manager_inputs():
    session = object()
    cli = SimpleNamespace(require_session=lambda s: None)
    ctx = context()
    interfaces = [InterfaceRecord('fixture', IP, ctx.platform, 'Gi1/0/1', '', 'down', 'down', NOW)]
    vlans = VlanState('fixture', IP, ctx.platform, (), (), NOW, ())
    return session, ctx, cli, interfaces, vlans


def test_manager_rebases_times_invalidates_changes_and_bounds(monkeypatch):
    session, ctx, cli, interfaces, vlans = manager_inputs()
    calls = []
    def factory(ctx, records, state):
        calls.append(1)
        return dict(configuration_reliable=True, observed_at=state.collection_time.isoformat(),
                    interfaces=[dict(port_description=i.port_description, collection_time=i.collection_time.isoformat()) for i in records])
    manager = observation_cache.ObservationManager(session, cli)
    first = manager.project(session, ctx, cli, interfaces, vlans, factory)
    first['interfaces'].clear()  # Borrowers cannot mutate retained evidence.
    later = NOW + timedelta(seconds=3)
    changed_time = [replace(interfaces[0], collection_time=later)]
    value = manager.project(session, ctx, cli, changed_time, replace(vlans, collection_time=later), factory)
    assert value['interfaces'][0]['collection_time'] == value['observed_at'] == later.isoformat()
    assert len(calls) == 1
    manager.project(session, ctx, cli, [replace(interfaces[0], port_description='external drift')], vlans, factory)
    assert len(calls) == 2
    manager.invalidate()
    manager.project(session, ctx, cli, interfaces, vlans, factory)
    assert len(calls) == 3
    monkeypatch.setattr(observation_cache, 'MAX_PROJECTION_BYTES', 1)
    for _ in range(2):
        manager.project(session, ctx, cli, interfaces, vlans, factory)
        assert manager._value is None
    assert len(calls) == 5
    with pytest.raises(ValueError):
        manager.project(object(), ctx, cli, interfaces, vlans, factory)


def test_incomplete_unsynchronized_and_factory_failure_never_reuse():
    session, ctx, cli, interfaces, vlans = manager_inputs()
    manager = observation_cache.ObservationManager(session, cli)
    calls = []
    def factory(*args):
        calls.append(1)
        return dict(configuration_reliable=False, interfaces=[])
    for _ in range(2):
        manager.project(session, ctx, cli, interfaces, replace(vlans, configuration=None), factory)
    assert len(calls) == 2 and manager._value is None
    def fail(*args):
        raise TimeoutError('password=never log this')
    with pytest.raises(TimeoutError):
        manager.project(session, ctx, cli, interfaces, vlans, fail)
    assert manager._value is None
    manager.project(session, ctx, cli, interfaces, vlans,
                    lambda *args: dict(configuration_reliable=True, interfaces=[]))
    assert manager._value is not None
    cli.require_session = fail
    with pytest.raises(TimeoutError):
        manager.project(session, ctx, cli, interfaces, vlans, factory)
    assert manager._value is None


def test_observation_context_parallel_device_isolation():
    def worker(index):
        session, ctx, cli, interfaces, vlans = manager_inputs()
        with observation_cache.observation_scope(session, cli) as manager:
            factory = lambda *a: dict(configuration_reliable=True, interfaces=[], device=index)
            for _ in range(2):
                value = observation_cache.project(session, ctx, cli, interfaces, vlans, factory)
                assert value['device'] == index
            assert observation_cache._current.get() is manager
        assert observation_cache._current.get() is None and manager._value is None
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(worker, range(9)))


@pytest.mark.parametrize('failure', ['', 'reject', 'timeout', 'interrupt'])
def test_execution_timing_outcomes_and_safe_correlation(tmp_path, monkeypatch, failure):
    run, _, original = run_prepared(tmp_path, monkeypatch)
    WorkerCLI.rejection = '% Invalid input' if failure == 'reject' else ''
    WorkerCLI.timeout = failure == 'timeout'
    WorkerCLI.interrupt = failure == 'interrupt'
    with module_logger('configuration', 'execution', log_root=tmp_path/'logs') as (_, log_path):
        if failure == 'interrupt':
            with pytest.raises(KeyboardInterrupt):
                run()
        else:
            run()
    text = log_path.read_text()
    assert 'hidden' not in text and 'test-user' not in text and 'hostname fixture' not in text
    records = [json.loads(line) for line in text.splitlines()]
    timings = [r for r in records if r['message'] == 'Execution timing']
    stages = {r['stage'] for r in timings}
    assert {'connection', 'shell_setup', 'identification', 'initial_preflight', 'protected_backup_collection',
            'protected_backup_write', 'template_stage', 'pre_row_plan', 'pre_row_drift_checks',
            'scoped_evidence', 'approved_command', 'row_apply', 'device_total', 'run_total'} <= stages
    for record in timings:
        assert record['digest'] == original.digest
        if record['stage'] != 'run_total':
            assert record['device_family'] == 'C3750X'
        assert math.isfinite(float(record['elapsed_seconds'])) and float(record['elapsed_seconds']) >= 0
        assert 'command' not in record and len(record['run_id']) <= 128
        if 'device_wait_seconds' in record:
            assert 0 <= float(record['device_wait_seconds']) <= float(record['elapsed_seconds'])
            assert float(record['work_seconds']) >= 0
    commands = [r for r in timings if r['stage'] == 'approved_command']
    expected = 'Rejected' if failure == 'reject' else 'Unknown' if failure in {'timeout', 'interrupt'} else 'Returned'
    assert commands[-1]['outcome'] == expected
    assert all(r['row_id'] and r['template_id'] and r['command_index'] for r in commands)
    assert next(r for r in timings if r['stage'] == 'run_total')['outcome'] == ('Unknown' if failure == 'interrupt' else 'Completed')
    assert next(r for r in timings if r['stage'] == 'device_total')['outcome'] == ('Failed' if failure == 'reject' else 'Unknown' if failure in {'timeout', 'interrupt'} else 'Completed')


def test_real_collectors_cli_receive_timing_no_raw_cli_or_output(tmp_path):
    session, channel = synthetic('C3750X')
    with module_logger('configuration', 'execution', log_root=tmp_path) as (logger, path):
        with profiling(logger, sanitize_text, management_ip=IP, run_id='run', digest='a'*64):
            with correlation(row_id='row', template_id='template'):
                with session, DeviceCLI(session) as cli:
                    ex._observe(session, context(), cli, [dict(request=dict(inputs=dict(vlan_id=445)))], 30)
    text = path.read_text()
    records = [json.loads(line) for line in text.splitlines()]
    assert {'cli_command', 'full_observation', 'interface_collection', 'vlan_config_collection', 'normalized_snapshot', 'vlan_lookup'} <= {r['stage'] for r in records}
    assert any(float(r['device_wait_seconds']) > 0 for r in records)
    assert all(r['outcome'] == 'Completed' for r in records)
    assert 'Customer' not in text and 'show running-config' not in text


def test_paging_reuse_checks_prompt_session_and_rejection():
    session, channel = synthetic('C3750X')
    with session, DeviceCLI(session) as cli:
        with pytest.raises(ValueError):
            cli.run_command(None)
        cli._reuse_session_setup = True
        behavior = dict(paging_command='terminal length 0', prompt_pattern=r'^([^\r\n]+#)$',
                        rejected=lambda output: False, platform_name='Cisco')
        cli.configure(**behavior)
        cli.configure(**behavior)
        assert channel.sent.count('terminal length 0') == 2  # constructor + first trusted setup
        cli.prompt = 'unexpected>'
        with pytest.raises(InteractiveCLIError):
            cli.configure(**behavior)
        cli.prompt = 'fixture#'
        cli._synchronized = False
        with pytest.raises(InteractiveCLIError):
            cli.configure(**behavior)
    session, channel = synthetic('C3750X')
    with session, DeviceCLI(session) as cli:
        cli._reuse_session_setup = True
        behavior['rejected'] = lambda output: True
        with pytest.raises(InteractiveCLIError):
            cli.configure(**behavior)
        assert not cli._accepted_paging


def test_wait_measurement_uses_clock_and_no_secrets(tmp_path, monkeypatch):
    from orbitflow import timing
    times = iter([10.0, 11.0, 14.0, 16.0])
    monkeypatch.setattr(timing, 'monotonic', lambda: next(times))
    with module_logger('configuration', 'execution', log_root=tmp_path) as (logger, path):
        with profiling(logger, sanitize_text, run_id='x'*1000, row_id='password=hidden'):
            with pytest.raises(TimeoutError), stage('cli_command', failure='Unknown'):
                with device_wait():
                    raise TimeoutError('secret-bearing arbitrary output')
    record = json.loads(path.read_text())
    assert float(record['elapsed_seconds']) == 6 and float(record['device_wait_seconds']) == 3
    assert float(record['work_seconds']) == 3 and record['outcome'] == 'Unknown'
    assert len(record['run_id']) == 128
    assert 'hidden' not in path.read_text() and 'arbitrary output' not in path.read_text()


def test_offline_timing_extraction_only_safe_numeric_aggregates(tmp_path, capsys):
    from scripts.configuration_execution_timings import main, summarize
    path = tmp_path/'execution.log'
    records = [dict(message='Execution timing', stage='cli_command', command_category='vlan_read',
                    elapsed_seconds=v, run_id='run', response='sensitive-output') for v in (1, 2, 3, 'nan', -1)]
    records.append(dict(message='Execution timing', stage='unsafe raw output', elapsed_seconds=1))
    path.write_text('\n'.join(json.dumps(r) for r in records)+'\n{torn', encoding='utf-8')
    summary = summarize([path], 'run')
    assert summary == [dict(stage='cli_command', command_category='vlan_read', count=3,
                            min_seconds=1, median_seconds=2, p95_seconds=3, max_seconds=3)]
    assert main([str(path), '--run-id', 'run']) == 0
    assert 'sensitive-output' not in capsys.readouterr().out
    assert summarize([path], 'different-run') == []


def test_offline_device_row_attribution_rotation_and_overlap(tmp_path, capsys):
    from scripts.configuration_execution_timings import main, summarize, DIMENSIONS
    records = []
    for device, family, elapsed in [('192.0.2.1', 'C3750X', 4), ('192.0.2.2', 'EdgeSwitch', 9)]:
        for stage_name in ('full_observation', 'vlan_config_collection', 'cli_command'):
            records.append(dict(message='Execution timing', timestamp=f'{device}/{stage_name}',
                                run_id='a'*32, management_ip=device, device_family=family,
                                row_id='b'*24, template_id=('edgeswitch' if family == 'EdgeSwitch' else 'c3750x')+'.vlan_database.v2',
                                stage=stage_name, command_category='configuration_read' if stage_name == 'cli_command' else '-',
                                elapsed_seconds=elapsed, response='password=do-not-reflect'))
    path = tmp_path/'execution.log'
    rotation = tmp_path/'execution.log.1'
    text = '\n'.join(json.dumps(r) for r in records)+'\n'
    path.write_text(text, encoding='utf-8')
    rotation.write_text(text, encoding='utf-8')  # overlapping retained copy
    warnings = []
    result = summarize([path, rotation, path, tmp_path/'missing'], group_by=DIMENSIONS, warnings=warnings)
    assert len(result) == 6
    reads = [r for r in result if r['stage'] == 'cli_command']
    assert [(r['management_ip'], r['median_seconds'], r['count']) for r in reads] == [('192.0.2.1', 4, 1), ('192.0.2.2', 9, 1)]
    assert all(r['run_id'] == 'a'*32 and r['row_id'] == 'b'*24 for r in result)
    assert any('missing' in w for w in warnings) and any('Duplicate' in w for w in warnings)
    assert main([str(path)]) == 0
    captured = capsys.readouterr()
    assert 'Nested stages overlap' in captured.err and 'rotation omitted' in captured.err
    assert 'do-not-reflect' not in captured.out + captured.err


def test_offline_unknown_fields_and_bounded_corrupt_line(tmp_path, monkeypatch):
    from scripts.configuration_execution_timings import summarize, DIMENSIONS
    path = tmp_path/'execution.log'
    record = dict(message='Execution timing', stage='cli_command', command_category='configuration_read',
                  elapsed_seconds=3, run_id='password=private', management_ip='token=private',
                  device_family='password=private', template_id='password=private', row_id='password=private')
    path.write_text('x'*70000+'\n'+json.dumps(record), encoding='utf-8')
    result = summarize([path], group_by=DIMENSIONS)
    assert len(result) == 1 and result[0]['management_ip'] == result[0]['device_family'] == result[0]['template_id'] == '-'
    assert result[0]['run_id'].startswith('sha256:')
    assert 'private' not in json.dumps(result)
    with pytest.raises(ValueError):
        summarize([path], group_by=['response'])
    monkeypatch.setattr('scripts.configuration_execution_timings.MAX_SAMPLES', 2)
    path.write_text('\n'.join([json.dumps(record)]*3), encoding='utf-8')
    with pytest.raises(ValueError, match='sample limit'):
        summarize([path])


def test_offline_generated_run_identity_and_large_finite_durations(tmp_path):
    from scripts.configuration_execution_timings import summarize
    path = tmp_path/'execution.log'
    run_id = '20261018T120000_123456Z_'+'a'*32
    record = dict(message='Execution timing', stage='cli_command', elapsed_seconds=1e308, run_id=run_id)
    path.write_text('\n'.join([json.dumps(record)]*2), encoding='utf-8')
    result = summarize([path], group_by=['run_id'])
    assert result[0]['run_id'] == run_id and result[0]['median_seconds'] == 1e308
    json.dumps(result, allow_nan=False)


def test_noop_and_unknown_save_timing_remain_independent(tmp_path, monkeypatch):
    for no_op in (True, False):
        root = tmp_path/str(no_op)
        run, saves, _ = run_prepared(root, monkeypatch, no_op=no_op)
        monkeypatch.setattr(ex, 'save_configuration', lambda *a, **kw: dict(status='Unknown', error_category='SaveExchangeIncomplete'))
        with module_logger('configuration', 'execution', log_root=root/'logs') as (_, path):
            spool = run()
        value = next(spool.records())['payload']
        assert value['rows'][0]['status'] == 'Verified'
        records = [json.loads(line) for line in path.read_text().splitlines()]
        timings = [r for r in records if r['message'] == 'Execution timing']
        if no_op:
            assert value['save']['status'] == 'Not required'
            assert not any(r['stage'] in {'approved_command', 'device_save'} for r in timings)
        else:
            assert value['save']['status'] == 'Unknown'
            assert next(r for r in timings if r['stage'] == 'device_save')['outcome'] == 'Unknown'
        assert any(r['stage'] == 'post_row_verification' and r['outcome'] == 'Verified' for r in timings)


@pytest.mark.parametrize('template', SUPPORTED, ids=lambda t: t.id)
def test_actual_execution_baseline_equivalence_all_templates(tmp_path, monkeypatch, template):
    """Real shared CLI/collectors/verification/backup/save on synthetic channels.

    The baseline disables only the two optimizations, without replacing any safety
    decision, collector, parser, approved command, verifier or persistence layer.
    """
    edge = template.family == 'EdgeSwitch'
    ctx = context(template.family)
    interface = '0/1' if edge else 'GigabitEthernet1/0/1'
    inputs = dict(management_ip=IP)
    function = template.function
    if function == 'VLAN Database':
        inputs.update(vlan_id=445, name='Changed')
    else:
        inputs['interface'] = interface
        if function == 'Interface Description':
            inputs['description'] = 'new'
        elif function == 'Access Port':
            inputs.update(vlan_id=445, description='new')
        elif function == 'Trunk Port':
            inputs.update(action='Replace', vlans=[445])
        else:
            inputs.update(action='Add/Change', tagged_vlans='445')
    row = request(template.id, inputs)
    base = ('hostname fixture\nvlan database\n vlan 445\n vlan name 445 "Customer"\nexit\ninterface 0/1\n description old\n vlan pvid 445\n vlan participation include 445\nexit\n'
            if edge else 'hostname fixture\nvlan 445\n name Customer\n!\ninterface Gi1/0/1\n description original\n switchport mode access\n switchport access vlan 445\n!\nend\n')
    if function == 'Trunk Port':
        base = base.replace('switchport mode access\n switchport access vlan 445', 'switchport mode trunk\n switchport trunk allowed vlan 445,545')
    after = base
    if function == 'VLAN Database':
        after = base.replace('Customer', 'Changed')
    elif function in {'Interface Description', 'Access Port'}:
        after = base.replace('description old' if edge else 'description original', 'description new')
    elif function == 'Trunk Port':
        after = base.replace('allowed vlan 445,545', 'allowed vlan 445')
    else:
        after = base.replace('vlan participation include 445', 'vlan participation include 445\n vlan tagging 445')

    class ExecutionChannel(SyntheticChannel):
        def __init__(self, commands=()):
            super().__init__(edge)
            self.config_override = base
            self.commands = list(commands)
            self.index = 0
            self.applied = False

        def recv(self, size):
            if not self.pending:
                raise socket.timeout()
            return super().recv(size)

        def sendall(self, data):
            command = data.decode().strip()
            if self.index < len(self.commands) and command == self.commands[self.index]:
                self.index += 1
                if command in {'configure', 'configure terminal'}:
                    self.prompt = '(fixture) (Config)#' if edge else 'fixture(config)#'
                elif command == 'vlan database':
                    self.prompt = '(fixture) (Vlan)#'
                elif command.startswith('interface '):
                    self.prompt = '(fixture) (Interface 0/1)#' if edge else 'fixture(config-if)#'
                elif command == 'vlan 445' and not edge:
                    self.prompt = 'fixture(config-vl)#'
                elif command == 'end':
                    self.prompt = 'fixture#'
                elif command == 'exit':
                    self.prompt = '(fixture) (Config)#' if '(Interface ' in self.prompt else '(fixture) #'
                if self.index == len(self.commands):
                    self.config_override, self.applied = after, True
                self.sent.append(command)
                self.pending = (command+'\n'+self.prompt).encode()
                return
            if command == 'write memory':
                self.sent.append(command)
                self.pending = (command+'\n'+self.prompt).encode()
                return
            if 'switchport' in command:
                output = ('Port: 0/1\nGeneral Mode PVID: 445\nGeneral Mode Untagged VLANs: \nGeneral Mode Tagged VLANs: 445\n'
                          if edge else 'Name: Gi1/0/1\nSwitchport: Enabled\nAdministrative Mode: '+('trunk\nTrunking Native Mode VLAN: 1\nTrunking VLANs Enabled: 445' if function == 'Trunk Port' else 'static access\nAccess Mode VLAN: 445'))
                self.sent.append(command)
                self.pending = (command+'\n'+output+'\n'+self.prompt).encode()
                return
            super().sendall(data)
            if command.startswith('show vlan'):
                text = self.pending.decode()
                if self.applied and function == 'VLAN Database':
                    text = text.replace('Customer', 'Changed')
                if self.applied and function == 'VLAN Port':
                    text = text.replace('Untagged', 'Tagged')
                self.pending = text.encode()
            if command == 'show interfaces status all':
                self.pending = self.pending.replace(b'Unit 1', b'new   ' if self.applied and function == 'Interface Description' else b'old   ')
            if command == 'show interfaces description' and self.applied and function in {'Access Port', 'Interface Description'}:
                self.pending = self.pending.replace(b'original', b'new')

    def new_session(channel):
        return DeviceSession(SimpleNamespace(invoke_shell=lambda: channel), lambda: None)

    with new_session(ExecutionChannel()) as session, DeviceCLI(session) as cli:
        observed = ex._observe(session, ctx, cli, [dict(request=row)], 30)
    original = plan([row], {IP: observed}, decisions={row['row_id']: 'Approve'})
    approved = original.to_dict()['results'][0]
    assert approved['deployment_ready'] and not approved['no_op'], approved['findings']
    outcomes, journals, channels = [], [], []
    original_scope = observation_cache.observation_scope
    for optimized in (False, True):
        channel = ExecutionChannel(approved['commands'])
        channels.append(channel)
        @contextmanager
        def connect(*args):
            with new_session(channel) as session:
                yield session
        class SelectedCLI(DeviceCLI):
            def configure(self, **kwargs):
                if not optimized:
                    self._reuse_session_setup = False
                return super().configure(**kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(ex, 'connect_device', connect)
            patch.setattr(ex, 'DeviceCLI', SelectedCLI)
            patch.setattr(ex, 'DeviceInventoryResolver', lambda *a, **kw: SimpleNamespace(resolve=lambda *a, **kw: ctx))
            patch.setattr(observation_cache, 'observation_scope', original_scope if optimized else lambda *a: nullcontext())
            service = ex.ExecutionService(tmp_path/str(optimized)/'authority')
            prepared = service.prepare(original, {row['row_id']: 'Approve'}, expected_digest=original.digest)
            spool = service.confirm(prepared['reference'], summary_digest=prepared['summary_digest'], apply=True,
                                    credentials={IP: DeviceCredentials('user', 'hidden')}, run_root=tmp_path/str(optimized)/'runs',
                                    inventory_path=tmp_path/'inventory.json')
        outcome = next(spool.records())['payload']
        assert outcome['rows'][0]['status'] == 'Verified', outcome
        assert outcome['save']['status'] == 'Saved'
        outcomes.append(outcome)
        from orbitflow.result_spool import ResultJournal
        journals.append([{k: event[k] for k in ('stage', 'command', 'command_index', 'status') if k in event}
                         for event in ResultJournal(spool.path/'events.jsonl').records()])
        assert channel.index == len(approved['commands'])
        assert [e['command'] for e in journals[-1] if e['stage'] == 'command_intent'] == approved['commands']
    def stable(value):
        if isinstance(value, dict):
            return {k: stable(v) for k, v in value.items() if k not in {'collection_time', 'observed_at', 'verification_seconds', 'elapsed_seconds'}}
        return [stable(v) for v in value] if isinstance(value, list) else value
    assert stable(outcomes[0]) == stable(outcomes[1])
    assert journals[0] == journals[1]
    assert channels[1].sent.count('show running-config') == channels[0].sent.count('show running-config')
    assert channels[1].sent.count('show running-config') == (2 if function == 'VLAN Database' else 3)
    assert channels[1].sent.count('terminal length 0') < channels[0].sent.count('terminal length 0')
