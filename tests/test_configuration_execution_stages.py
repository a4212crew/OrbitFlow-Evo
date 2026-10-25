"""Ordered stage execution with real planners/verifiers and deterministic device facts."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from orbitflow.configuration import execution as ex
from orbitflow.configuration.v2.planning import plan, request
from orbitflow.transport import DeviceCredentials
from orbitflow.result_spool import ResultJournal
from test_configuration_execution import (context, observation, template, fake_runtime,
                                         WorkerCLI, IP, NOW, cli_with)

CASES = [(family, function) for family in ('C3750X', 'C3850X', 'EdgeSwitch')
         for function in (('VLAN Database', 'VLAN Port', 'Interface Description') if family == 'EdgeSwitch'
                          else ('VLAN Database', 'Access Port', 'Trunk Port', 'Interface Description'))]


def fixture(family, function, count=2):
    ctx = context(family)
    edge = family == 'EdgeSwitch'
    global_config = 'vlan database\n vlan 445,545\nexit\n' if edge else 'vlan 445\n name Customer\n!\nvlan 545\n name Other\n!\n'
    old, new, requests = [], [], []
    for i in range(1, count + 1):
        port = f'0/{i}' if edge else f'GigabitEthernet1/0/{i}'
        params = dict(management_ip=IP)
        a = b = ''
        if function == 'VLAN Database':
            params.update(vlan_id=700+i, name='Customer')
        else:
            params['interface'] = port
            if function == 'Interface Description':
                params['description'] = 'new'
                a, b = ' description old\n', ' description new\n'
            elif function == 'Access Port':
                params['vlan_id'] = 445
                a = ' switchport mode access\n switchport access vlan 545\n'
                b = a.replace('545', '445')
            elif function == 'Trunk Port':
                params.update(action='Add', vlans=[545])
                a = ' switchport mode trunk\n switchport trunk native vlan 1\n switchport trunk allowed vlan 445\n'
                b = a.replace('allowed vlan 445', 'allowed vlan 445,545')
            else:
                params.update(action='Add/Change', tagged_vlans='545')
                a = ' vlan pvid 445\n vlan participation include 445\n'
                b = a + ' vlan participation include 545\n vlan tagging 545\n'
            tail = ' shutdown\n' + ('exit\n' if edge else '!\n')
            old.append(f'interface {port}\n' + a + tail)
            new.append(f'interface {port}\n' + b + tail)
        requests.append(request(template(family, function).id, params, row=i+2))
    before = observation(ctx, global_config + ''.join(old) + ('end\n' if not edge else ''))
    after = observation(ctx, global_config + ''.join(new) + ('end\n' if not edge else ''))
    for obs in (before, after):
        obs['vlan_lookups'] = {str(v): dict(status='present', name='Customer', operational_status='active', ports_complete=True,
            ports=[dict(interface=f'0/{i}', configured='Include', current='Exclude', tagging='Tagged')
                   for i in range(1, count+1)]) for v in (445, 545, *range(701, 701+count))}
    for v in (445, 545):
        for obs in (before, after):
            obs['vlan_lookups'][str(v)]['name'] = str(v) if edge else ('Customer' if v == 445 else 'Other')
    for v in range(701, 701+count):
        before['vlan_lookups'][str(v)].update(status='absent', name='', operational_status='')
    return ctx, requests, before, after


def execute(tmp_path, monkeypatch, ctx, requests, before, after, *, verifier=None, observe=None, cli_type=None, switch_facts=None):
    logger_factory = ex.module_logger
    monkeypatch.setattr(ex, 'module_logger', lambda *a, **kw: logger_factory(*a, log_root=tmp_path/'logs', **kw))
    real_verify = ex._verify_observed
    saves = fake_runtime(monkeypatch, ctx, before)
    monkeypatch.setattr(ex, '_verify_observed', verifier or real_verify)
    reads = []
    def collect(*args):
        reads.append(args[3])
        return observe(len(reads)) if observe else (before if len(reads) == 1 else after)
    monkeypatch.setattr(ex, '_observe', collect)
    if cli_type:
        monkeypatch.setattr(ex, 'DeviceCLI', cli_type)
    facts = dict(enabled=True, administrative_mode='static access', access_vlan=445,
                 native_vlan=1, allowed_vlans=[445,545], pvid=445, tagged_vlans=[545], untagged_vlans=[445])
    facts.update(switch_facts or {})
    if 'trunk_port' in requests[0]['template_id']:
        facts['administrative_mode'] = 'trunk'
    monkeypatch.setattr(ex, 'SwitchportService', lambda **kw: SimpleNamespace(collect=lambda *a, **kw: SimpleNamespace(to_dict=lambda: dict(facts=facts))))
    original = plan(requests, {IP: before}, now=NOW)
    service = ex.ExecutionService(tmp_path/'authority')
    prepared = service.prepare(original, {r['row_id']: 'Approve' for r in requests}, expected_digest=original.digest,
                               settings=ex.ApplySettings(connection_start_interval=0))
    assert len(prepared['summary']['selected']) == len(requests)
    spool = service.confirm(prepared['reference'], summary_digest=prepared['summary_digest'], apply=True,
        credentials={IP: DeviceCredentials('user','hidden')}, run_root=tmp_path/'runs', inventory_path=tmp_path/'inventory.json')
    rows = next(spool.records())['payload']['rows']
    events = list(ResultJournal(spool.path/'events.jsonl').records())
    return rows, events, reads, saves, prepared


@pytest.mark.parametrize('family,function', CASES)
def test_all_templates_shared_fresh_stage_real_verification(tmp_path, monkeypatch, family, function):
    ctx, requests, before, after = fixture(family, function)
    rows, events, reads, saves, prepared = execute(tmp_path, monkeypatch, ctx, requests, before, after)
    assert [r['status'] for r in rows] == ['Verified', 'Verified']
    assert len(reads) == (1 if function == 'VLAN Database' else 2)
    assert len(saves) == 1
    assert WorkerCLI.instances[0].sent == [c for e in prepared['summary']['selected'] for c in e['result']['commands']]
    assert {r['stage_id'] for r in rows} == {'stage-1'}
    assert all(r['verification']['observation_scope'] == 'stage final state; independent target' for r in rows)
    first_send = next(i for i,e in enumerate(events) if e['stage'] == 'command_intent')
    assert len([e for e in events[:first_send] if e['stage'] == 'pre_row_evidence']) == 2
    assert all(any(e['stage'] == 'row_result' and e['row_id'] == r['row_id'] for e in events) for r in rows)
    assert [e['stage'] for e in events if e['stage'].startswith('stage_')] == ['stage_precheck', 'stage_post_observation', 'stage_result']


@pytest.mark.parametrize('family,function', [
    ('C3750X', 'Access Port'), ('C3850X', 'Trunk Port'), ('EdgeSwitch', 'VLAN Port')])
def test_shared_post_observation_retains_distinct_real_switchport_reads(monkeypatch, family, function):
    ctx, requests, before, after = fixture(family, function)
    original = plan(requests, {IP: before}, decisions={r['row_id']: 'Approve' for r in requests}, now=NOW)
    edge = family == 'EdgeSwitch'
    prompt = '(<fixture>) #' if edge else 'fixture#'
    responses = [('terminal length 0\n'+prompt).encode()]
    if not edge:
        responses.append(('terminal width 511\n'+prompt).encode())
    commands = []
    for i in (1, 2):
        target = f'0/{i}' if edge else f'GigabitEthernet1/0/{i}'
        command = f'show interfaces switchport {target}' if edge else f'show interfaces {target} switchport'
        commands.append(command)
        text = (f'Port: {target}\nGeneral Mode PVID: 445\nGeneral Mode Untagged VLANs: 445\nGeneral Mode Tagged VLANs: 545'
                if edge else f'Name: Gi1/0/{i}\nSwitchport: Enabled\nAdministrative Mode: '+
                ('trunk\nTrunking Native Mode VLAN: 1\nTrunking VLANs Enabled: 445,545'
                 if function == 'Trunk Port' else 'static access\nAccess Mode VLAN: 445'))
        responses.append((command+'\n'+text+'\n'+prompt).encode())
    cli, channel = cli_with(responses, prompt)
    cli._reuse_session_setup = True
    def no_recollect(*a, **kw):
        pytest.fail('independent rows must share the supplied post-stage observation')
    monkeypatch.setattr(ex, '_observe', no_recollect)
    for request, result in zip(requests, original.to_dict()['results']):
        verified = ex._verify_observed(cli.session, ctx, cli, dict(request=request, result=result), before, after=after)
        assert verified['status'] == 'Verified'
    assert [value.decode().strip() for value in channel.sent if value.decode().startswith('show ')] == commands


@pytest.mark.parametrize('fault,expected', [('preservation','Failed'), ('missing','Unknown'), ('unreliable','Unknown')])
def test_stage_target_drift_preservation_and_incomplete_evidence(tmp_path, monkeypatch, fault, expected):
    ctx, requests, before, after = fixture('C3750X', 'Interface Description')
    if fault == 'preservation':
        for node in after['facts']:
            if node['kind'] == 'interface':
                node['children'] = [n for n in node['children'] if n['kind'] != 'shutdown']
    elif fault == 'missing':
        after['interfaces'] = []
    else:
        after['configuration_reliable'] = False
    rows, _, _, _, _ = execute(tmp_path, monkeypatch, ctx, requests, before, after)
    assert all(r['status'] == expected for r in rows)


def test_stage_splits_noncontiguous_templates_dependencies_and_aliases():
    ctx, requests, before, _ = fixture('C3750X', 'Interface Description', 3)
    entries = [dict(request=r, result=dict(resolved_target=r['inputs']['interface'], dependencies=[]), identity=dict(platform=ctx.platform)) for r in requests]
    assert list(ex._template_stages(entries)) == [entries]
    entries[1]['result']['dependencies'] = [requests[0]['row_id']]
    assert [len(s) for s in ex._template_stages(entries)] == [1,2]
    entries[1]['result']['dependencies'] = []
    entries[1]['result']['resolved_target'] = 'Gi1/0/1'
    assert [len(s) for s in ex._template_stages(entries)] == [1,2]
    entries[1]['request'] = dict(entries[1]['request'], template_id=template('C3750X','Access Port').id)
    assert [s[0]['request']['template_id'] for s in ex._template_stages(entries)] == [e['request']['template_id'] for e in entries]


@pytest.mark.parametrize('fault', ['reject','timeout','lost_mode'])
def test_partial_stage_failure_never_invents_verification(tmp_path, monkeypatch, fault):
    ctx, requests, before, after = fixture('C3750X', 'VLAN Database')
    class FaultCLI(WorkerCLI):
        def run_command(self, command, **kw):
            if command == 'name Customer' and self.sent.count('vlan 701') and not self.sent.count('vlan 702'):
                if fault == 'reject':
                    self.sent.append(command)
                    return '% Invalid input'
                if fault == 'timeout':
                    self.dead = True
                    raise TimeoutError()
                self.prompt = 'foreign(config)#'
                raise RuntimeError('unexpected mode')
            return super().run_command(command, **kw)
    rows, events, _, saves, _ = execute(tmp_path, monkeypatch, ctx, requests, before, after, cli_type=FaultCLI)
    assert rows[0]['status'] == ('Failed' if fault == 'reject' else 'Unknown')
    assert rows[1]['status'] == ('Verified' if fault == 'reject' else 'Not executed')
    assert len(saves) == (1 if fault == 'reject' else 0)
    if fault != 'reject':
        assert not any(e['stage'] == 'command_intent' and e['row_id'] == requests[1]['row_id'] for e in events)


@pytest.mark.parametrize('external_drift', [False, True])
def test_ordered_template_reentry_description_supersession_and_external_drift(tmp_path, monkeypatch, external_drift):
    ctx, access, before, final = fixture('C3750X', 'Access Port')
    first = dict(access[0], inputs=dict(access[0]['inputs'], description='middle'),
                 source_inputs=dict(access[0]['inputs'], description='middle'))
    desc = request(template('C3750X','Interface Description').id,
                   dict(management_ip=IP, interface=first['inputs']['interface'], description='final'), sheet_order=1)
    last = dict(access[1], sheet_order=2)
    # Independently observed intermediate access state precedes later description.
    base_config = 'vlan 445\n name Customer\n!\nvlan 545\n name Other\n!\n'
    port1 = 'interface GigabitEthernet1/0/1\n description middle\n switchport mode access\n switchport access vlan 445\n shutdown\n!\n'
    port2 = 'interface GigabitEthernet1/0/2\n switchport mode access\n switchport access vlan 545\n shutdown\n!\nend\n'
    middle = observation(ctx, base_config+port1+port2)
    described = observation(ctx, base_config+port1.replace('middle','final')+port2)
    finished = observation(ctx, base_config+port1.replace('middle','final')+port2.replace('vlan 545','vlan 445'))
    for obs in (middle, described, finished):
        obs['vlan_lookups'] = deepcopy(before['vlan_lookups'])
    changed = observation(ctx, base_config+port1.replace('middle','final')+
                          port2.replace(' shutdown', ' description external\n shutdown')) if external_drift else described
    if external_drift:
        finished = observation(ctx, base_config+port1.replace('middle','final')+
                               port2.replace('vlan 545','vlan 445').replace(' shutdown', ' description external\n shutdown'))
    for obs in (changed, finished):
        obs['vlan_lookups'] = deepcopy(before['vlan_lookups'])
    sequence = [before, middle, middle, described, changed, finished]
    rows, events, reads, saves, _ = execute(tmp_path, monkeypatch, ctx, [first, desc, last], before, finished,
                                           observe=lambda n: sequence[n-1])
    assert [r['stage_id'] for r in rows] == ['stage-1','stage-2','stage-3']
    assert [r['status'] for r in rows] == ['Verified','Verified','Verified']
    assert rows[0]['verification']['evidence']['description']['port_description'] == 'middle'
    assert rows[1]['verification']['evidence']['description']['port_description'] == 'final'
    assert len(reads) == 6
    assert len(saves) == 1
    ends = [i for i,e in enumerate(events) if e['stage']=='stage_result']
    starts = [i for i,e in enumerate(events) if e['stage']=='stage_precheck']
    assert ends[0] < starts[1] and ends[1] < starts[2]


def test_noop_stage_still_fresh_and_save_independent(tmp_path, monkeypatch):
    ctx, requests, before, after = fixture('C3750X','Interface Description')
    rows, _, reads, saves, _ = execute(tmp_path, monkeypatch, ctx, requests, after, after)
    assert all(r['status']=='Verified' for r in rows)
    assert len(reads)==2 and not saves and not WorkerCLI.instances[0].sent


@pytest.mark.parametrize('family,function', CASES)
def test_approved_cli_survives_fresh_noop_without_execution_planning(tmp_path, monkeypatch, family, function):
    from orbitflow.configuration.v2 import planning
    ctx, requests, before, after = fixture(family, function)
    fresh = plan(requests, {IP: after}, now=NOW).to_dict()['results']
    assert all(r['no_op'] for r in fresh)
    def forbidden(*a, **kw):
        pytest.fail('execution must not plan fresh device state')
    def observe(count):
        # Immutable source validation happens before connection. From the first
        # fresh collection onward neither rendering nor plan evaluation is allowed.
        monkeypatch.setattr(planning, 'plan', forbidden)
        monkeypatch.setattr(planning, '_build', forbidden)
        return after
    rows, _, reads, saves, prepared = execute(tmp_path, monkeypatch, ctx, requests, before, after, observe=observe)
    assert [r['status'] for r in rows] == ['Verified', 'Verified']
    approved = [c for e in prepared['summary']['selected'] for c in e['result']['commands']]
    assert approved and WorkerCLI.instances[0].sent == approved
    assert len(reads) == (1 if function == 'VLAN Database' else 2)
    assert len(saves) == 1


@pytest.mark.parametrize('family', ['C3750X', 'C3850X'])
@pytest.mark.parametrize('function', ['Access Port', 'Trunk Port', 'Interface Description'])
@pytest.mark.parametrize('damage', ['missing', 'duplicate', 'membership'])
def test_fresh_target_identity_and_bundle_ownership(tmp_path, monkeypatch, family, function, damage):
    ctx, requests, before, after = fixture(family, function)
    fresh = deepcopy(before)
    first = requests[0]['inputs']['interface']
    node = next(n for n in fresh['facts'] if n['kind'] == 'interface' and n['value'] == first)
    if damage == 'missing':
        fresh['interfaces'] = [i for i in fresh['interfaces'] if i['port_name'] != first]
    elif damage == 'duplicate':
        fresh['facts'].append(deepcopy(node))
    else:
        member = dict(node['children'][0], kind='aggregate', value=9, children=[], excerpt=' channel-group 9 mode active')
        node['children'].append(member)
        next(n for n in after['facts'] if n['kind'] == 'interface' and n['value'] == first)['children'].append(deepcopy(member))
    rows, events, _, saves, prepared = execute(tmp_path, monkeypatch, ctx, requests, before, after,
        observe=lambda n: fresh if n == 1 else after)
    allowed = function == 'Interface Description' and damage == 'membership'
    assert rows[0]['status'] == ('Verified' if allowed else 'Not executed')
    assert rows[1]['status'] == 'Verified'
    sent = [e for e in events if e['stage'] == 'command_intent']
    assert any(e['row_id'] == requests[0]['row_id'] for e in sent) == allowed
    assert len(saves) == 1


@pytest.mark.parametrize('family', ['C3750X', 'C3850X'])
def test_child_forwarding_historical_redirect_rejected(tmp_path, monkeypatch, family):
    ctx, requests, before, after = fixture(family, 'Trunk Port')
    common = 'vlan 445\n name Customer\n!\nvlan 545\n name Other\n!\n'
    member = 'interface GigabitEthernet1/0/1\n channel-group 1 mode active\n!\n'
    owner = 'interface Port-channel1\n switchport mode trunk\n switchport trunk native vlan 1\n switchport trunk allowed vlan 445\n shutdown\n!\n'
    other = owner.replace('Port-channel1', 'GigabitEthernet1/0/2')
    lookups = before['vlan_lookups']
    before = observation(ctx, common+member+owner+other+'end\n')
    after = observation(ctx, common+member+(owner+other).replace('allowed vlan 445', 'allowed vlan 445,545')+'end\n')
    for obs in (before, after):
        obs['vlan_lookups'] = deepcopy(lookups)
    from orbitflow.configuration.execution import ExecutionService
    original = plan(requests, {IP: before}, now=NOW)
    prepared = ExecutionService(tmp_path / 'authority').prepare(original,
        {r['row_id']: 'Approve' for r in requests}, expected_digest=original.digest)
    assert prepared['summary']['skipped'][0]['reason'] in {'BLOCKED', 'NOT_ALLOW_ON_CHILD_PORT_CHANNEL'}
    # Simulate the historical decision evaluator accepting a saved redirect.
    historical = original.to_dict()
    historical['results'][0].update(deployment_ready=True, blockers=[],
        resolved_target='Port-channel1', decision='Approve')
    monkeypatch.setattr(ex, 'evaluate_decisions', lambda *a, **kw:
        SimpleNamespace(to_dict=lambda: historical))
    prepared = ExecutionService(tmp_path / 'old-authority').prepare(original,
        {r['row_id']: 'Approve' for r in requests}, expected_digest=original.digest)
    assert prepared['summary']['skipped'][0]['reason'] == 'NOT_ALLOW_ON_CHILD_PORT_CHANNEL'

    # Historical approved redirect artifacts must also fail at the fresh gate.
    entry = dict(request=requests[0], result=dict(resolved_target='Port-channel1'))
    with pytest.raises(ex.ExecutionBlocked) as error:
        ex._check_target(entry, before, ctx)
    assert error.value.code == 'NOT_ALLOW_ON_CHILD_PORT_CHANNEL'
    # Expressly selecting the logical parent still passes normal fresh gates.
    parent_request = deepcopy(requests[0])
    parent_request['inputs']['interface'] = 'Port-channel1'
    ex._check_target(dict(request=parent_request, result=dict(resolved_target='Port-channel1')), before, ctx)




@pytest.mark.parametrize('family', ['C3750X', 'C3850X'])
@pytest.mark.parametrize('function,kind,value,code', [
    ('Access Port', 'mode', 'trunk', 'ACCESS_CONVERSION_BLOCKED'),
    ('Trunk Port', 'mode', 'access', 'TRUNK_CONVERSION_BLOCKED'),
    ('Access Port', 'methodology_unknown', True, 'UNRESOLVED_CONFIGURATION'),
    ('Trunk Port', 'routed', True, 'TRUNK_CONVERSION_BLOCKED')])
def test_known_target_prerequisites_without_planning(family, function, kind, value, code):
    ctx, requests, before, _ = fixture(family, function, 1)
    original = plan(requests, {IP: before}, now=NOW).to_dict()
    node = next(n for n in before['facts'] if n['kind'] == 'interface')
    node['children'].append(dict(kind=kind, value=value, children=[]))
    with pytest.raises(ex.ExecutionBlocked) as error:
        ex._check_target(dict(request=requests[0], result=original['results'][0]), before, ctx)
    assert error.value.code == code


@pytest.mark.parametrize('function', ['VLAN Port', 'Interface Description'])
def test_edgeswitch_ownership_gate_is_port_only(function):
    ctx, requests, before, _ = fixture('EdgeSwitch', function, 1)
    original = plan(requests, {IP: before}, now=NOW).to_dict()
    before['audit'][0]['configuration_owner'] = 'lag 1'
    entry = dict(request=requests[0], result=original['results'][0])
    if function == 'VLAN Port':
        with pytest.raises(ex.ExecutionBlocked) as error:
            ex._check_target(entry, before, ctx)
        assert error.value.code == 'OWNERSHIP_REQUIRES_REVIEW'
    else:
        ex._check_target(entry, before, ctx)


@pytest.mark.parametrize('family,function', [
    ('C3750X', 'Trunk Port'), ('C3850X', 'Access Port'), ('EdgeSwitch', 'VLAN Port')])
@pytest.mark.parametrize('damage', ['missing', 'duplicate'])
def test_missing_or_ambiguous_owner_evidence_blocks_port(family, function, damage):
    ctx, requests, before, _ = fixture(family, function, 1)
    original = plan(requests, {IP: before}, now=NOW).to_dict()
    before['audit'] = [] if damage == 'missing' else before['audit'] * 2
    with pytest.raises(ex.ExecutionBlocked):
        ex._check_target(dict(request=requests[0], result=original['results'][0]), before, ctx)


def test_failed_catalyst_database_allows_port_and_description(tmp_path, monkeypatch):
    ctx, _, before, after = fixture('C3750X', 'Access Port', 1)
    db = request(template('C3750X','VLAN Database').id, dict(management_ip=IP, vlan_id=701, name='Customer'))
    port = request(template('C3750X','Access Port').id,
                   dict(management_ip=IP, interface='GigabitEthernet1/0/1', vlan_id=701), sheet_order=1)
    desc = request(template('C3750X','Interface Description').id,
                   dict(management_ip=IP, interface='GigabitEthernet1/0/1', description='new'), sheet_order=2)
    class RejectCLI(WorkerCLI):
        def run_command(self, command, **kw):
            response = super().run_command(command, **kw)
            return '% Invalid input' if command == 'name Customer' else response
    def verify(session, context, cli, entry, *args, **kw):
        return dict(status='Verified')
    rows, events, _, saves, prepared = execute(tmp_path, monkeypatch, ctx, [db,port,desc], before, after,
        verifier=verify, cli_type=RejectCLI)
    assert prepared['summary']['selected'][1]['result']['dependencies'] == []
    assert [r['status'] for r in rows] == ['Failed', 'Verified', 'Verified']
    assert any(e['stage'] == 'command_intent' and e['row_id'] == port['row_id'] for e in events)
    assert len(saves) == 1


@pytest.mark.parametrize('complete', [False, True])
def test_edgeswitch_stage_prerequisite_is_row_scoped_and_ambiguous_post_is_unknown(tmp_path, monkeypatch, complete):
    ctx, requests, before, after = fixture('EdgeSwitch','VLAN Port')
    after['vlan_lookups']['545']['ports_complete'] = complete
    rows, _, _, _, _ = execute(tmp_path, monkeypatch, ctx, requests, before, after)
    assert [r['status'] for r in rows] == (['Verified','Verified'] if complete else ['Unknown','Unknown'])


def test_verified_edgeswitch_database_satisfies_later_port_stage_prerequisite(tmp_path, monkeypatch):
    ctx, _, before, _ = fixture('EdgeSwitch', 'VLAN Port', 1)
    db = request(template('EdgeSwitch','VLAN Database').id, dict(management_ip=IP, vlan_id=701, name='Customer'))
    port = request(template('EdgeSwitch','VLAN Port').id, dict(management_ip=IP, interface='0/1', action='Add/Change', tagged_vlans='545', pvid=701), sheet_order=1)
    config = 'vlan database\n vlan 445,545,701\n vlan name 701 "Customer"\nexit\ninterface 0/1\n vlan pvid 445\n vlan participation include 445\n shutdown\nexit\n'
    database = observation(ctx, config)
    after = observation(ctx, config.replace('vlan pvid 445', 'vlan pvid 701').replace(' vlan participation include 445', ' vlan participation include 445,545,701\n vlan tagging 545'))
    for obs in (database, after):
        obs['vlan_lookups'] = deepcopy(before['vlan_lookups'])
        obs['vlan_lookups']['701'].update(status='present', name='Customer', operational_status='Static')
        obs['vlan_lookups']['701']['ports'] = [dict(interface='0/1', configured='Include', current='Exclude', tagging='Untagged')]
    rows, _, reads, saves, prepared = execute(tmp_path, monkeypatch, ctx, [db,port], before, after,
        observe=lambda n: [before,database,after][n-1], switch_facts=dict(pvid=701, untagged_vlans=[701]))
    assert [r['status'] for r in rows] == ['Verified','Verified']
    assert [r['stage_id'] for r in rows] == ['stage-1','stage-2']
    assert len(reads)==3 and len(saves)==1


def test_stage_timing_extraction_keeps_only_safe_stage_ids(tmp_path):
    from scripts.configuration_execution_timings import summarize
    path=tmp_path/'execution.log'
    path.write_text('\n'.join(json.dumps(dict(message='Execution timing', stage='template_stage',
        elapsed_seconds=0.25, stage_id=stage_id)) for stage_id in ('stage-1','password raw secret')), encoding='utf-8')
    result=summarize([path], group_by=['stage_id'])
    assert {row['stage_id'] for row in result} == {'stage-1','-'}
    assert 'secret' not in json.dumps(result)


def test_verified_database_preserves_later_stage_order(tmp_path, monkeypatch):
    ctx, requests, before, _ = fixture('C3750X','Access Port',1)
    db=request(template('C3750X','VLAN Database').id, dict(management_ip=IP,vlan_id=701,name='Customer'))
    port=request(template('C3750X','Access Port').id, dict(management_ip=IP,interface='GigabitEthernet1/0/1',vlan_id=701),sheet_order=1)
    config='vlan 445\n name Customer\n!\nvlan 545\n name Other\n!\nvlan 701\n name Customer\n!\ninterface GigabitEthernet1/0/1\n switchport mode access\n switchport access vlan 545\n shutdown\n!\nend\n'
    database=observation(ctx,config)
    after=observation(ctx,config.replace('access vlan 545','access vlan 701'))
    for obs in (database,after):
        obs['vlan_lookups']=deepcopy(before['vlan_lookups'])
        obs['vlan_lookups']['701'].update(status='present',name='Customer',operational_status='active')
    rows,events,_,saves,prepared=execute(tmp_path,monkeypatch,ctx,[db,port],before,after,
        observe=lambda n:[before,database,after][n-1],switch_facts=dict(access_vlan=701))
    assert prepared['summary']['selected'][1]['result']['dependencies']==[]
    assert [r['status'] for r in rows]==['Verified','Verified']
    assert len(saves)==1
    first_result=next(i for i,e in enumerate(events) if e['stage']=='row_result' and e['row_id']==db['row_id'])
    port_send=next(i for i,e in enumerate(events) if e['stage']=='command_intent' and e['row_id']==port['row_id'])
    assert first_result<port_send


@pytest.mark.parametrize('family', ['C3750X', 'C3850X', 'EdgeSwitch'])
def test_stage_changing_prompt_presentation_keeps_verification_and_save(tmp_path, monkeypatch, family):
    ctx, requests, before, after = fixture(family, 'Interface Description')
    class ChangingCLI(WorkerCLI):
        def run_command(self, command, **kw):
            response = super().run_command(command, **kw)
            if self.edge:
                if command == 'configure':
                    self.prompt = '(ES24 Something)#'
                elif command.startswith('interface '):
                    self.prompt = '(ES24) (Something)#'
                elif command == 'exit':
                    self.prompt = '(ES24) #'
            elif command == 'end':
                self.prompt = 'SW-ABBREV#'
            else:
                self.prompt = 'SW-ABBREV(config-if-srv)#'
            return response
    rows, events, _, saves, _ = execute(tmp_path, monkeypatch, ctx, requests, before, after, cli_type=ChangingCLI)
    assert [r['status'] for r in rows] == ['Verified', 'Verified']
    assert len(saves) == 1
    assert not any(e.get('status') == 'Rejected' for e in events)



def test_rejected_exec_recovery_blocks_further_rows_and_save(tmp_path, monkeypatch):
    ctx, requests, before, after = fixture('C3750X', 'Interface Description')
    class RecoveryCLI(WorkerCLI):
        def run_command(self, command, **kw):
            response = super().run_command(command, **kw)
            if command == 'end':
                self.prompt = 'fixture(config-if-srv)#'
            # The recovery command also fails; never assume EXEC from an error.
            if command == 'end' and self.sent.count('end') > 1:
                self.prompt = 'fixture#'
                return '% Invalid input'
            return response
    rows, _, _, saves, _ = execute(tmp_path, monkeypatch, ctx, requests, before, after, cli_type=RecoveryCLI)
    assert rows[0]['status'] == 'Unknown'
    assert rows[1]['status'] == 'Not executed'
    assert not saves



@pytest.mark.parametrize('family', ['C3750X', 'EdgeSwitch'])
def test_fresh_observation_exec_presentation_can_anchor_save(tmp_path, monkeypatch, family):
    ctx, requests, before, after = fixture(family, 'Interface Description')
    def collect(count):
        if count > 1:
            WorkerCLI.instances[0].prompt = '(OBSERVED) #' if family == 'EdgeSwitch' else 'OBSERVED#'
        return before if count == 1 else after
    rows, _, _, saves, _ = execute(tmp_path, monkeypatch, ctx, requests, before, after, observe=collect)
    assert [r['status'] for r in rows] == ['Verified', 'Verified']
    assert len(saves) == 1
