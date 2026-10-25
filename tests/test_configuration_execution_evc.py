"""Issue 154 synthetic execution; no device connections."""
from dataclasses import replace
from types import SimpleNamespace
import socket

import pytest

from orbitflow.configuration import execution as ex
from orbitflow.configuration.v2.planning import request, plan
from orbitflow.configuration.plans import PlanError
from orbitflow.vendors.cisco import evc_execution as evc
from orbitflow.vendors.cisco.evc import child_commands
from orbitflow.capabilities.save import save_configuration
from orbitflow.transport import DeviceCredentials
from orbitflow.result_spool import ResultJournal
from test_configuration_v2_approved_services import observation, template, evc_inputs, evc_config, IP, NOW
from test_configuration_execution import context, fake_runtime, WorkerCLI, cli_with


def fixture(family, config=None, inputs=None, function='EVC'):
    ctx = replace(context(family, IP), platform='cisco_ios' if family == 'ME3600X' else 'cisco_xe',
                  capability_profile='me3600x_evc' if family == 'ME3600X' else 'asr920_evc')
    config = config or evc_config(family, parent=' mtu 9000\n shutdown\n')
    obs = observation(family, config)
    # Use the same canonical identity as the synthetic live resolver.
    obs['identity'] = ex.identity(ctx)
    obs['vlan_lookups'] = {'445': dict(status='present', name='Customer', operational_status='active')}
    p = inputs or evc_inputs()
    r = request(template(family, function).id, p)
    original = plan([r], {IP: obs}, now=NOW)
    result = ex.evaluate_decisions(original, {r['row_id']: 'Approve'}, expected_digest=original.digest, now=NOW).to_dict()['results'][0]
    return ctx, obs, r, original, dict(request=r, result=result)


def post(family, p, **kw):
    config = evc_config(family, ' service instance ' + str(p['service_instance_id']) + ' ethernet\n' +
                        ''.join('  ' + line + '\n' for line in child_commands(p)),
                        ' mtu 9000\n shutdown\n' + (' description ' + p['interface_description'] + '\n' if p.get('interface_description') else ''))
    obs = observation(family, config.replace(kw.get('remove', '\0'), ''))
    obs['vlan_lookups'] = {'445': dict(status='present', name='Customer', operational_status='active')}
    return obs


@pytest.mark.parametrize('family', ['ME3600X', 'ASR920'])
@pytest.mark.parametrize('existing', [False, True])
def test_create_recreate_fresh_checks_verifier_and_summary(tmp_path, family, existing):
    p = evc_inputs(split_horizon_group=0, description='CHILD', interface_description='PARENT')
    config = evc_config(family, (' service instance 3000 ethernet\n  encapsulation dot1q 445\n  rewrite ingress tag pop 1 symmetric\n  bridge-domain 445\n' if existing else ''), ' mtu 9000\n shutdown\n')
    ctx, before, r, original, entry = fixture(family, config, p)
    assert not evc.target_blocker(entry, before, ctx)
    after = post(family, p)
    assert evc.verify(entry, before, after, ctx)['status'] == 'Verified'
    assert evc.verify(entry, before, post(family, p, remove=' shutdown\n'), ctx)['status'] == 'Failed'
    prepared = ex.ExecutionService(tmp_path).prepare(original, {r['row_id']: 'Approve'}, expected_digest=original.digest)
    assert len(prepared['summary']['selected']) == 1
    assert 'Forwarding may be interrupted' in ex.render_summary(ex.operator_summary(prepared))
    assert 'switchport' not in ' '.join(ex.verification_commands(r, entry['result']))


@pytest.mark.parametrize('family', ['ME3600X', 'ASR920'])
@pytest.mark.parametrize('change,code', [
    (' service instance 20 ethernet\n  encapsulation dot1q 445\n  bridge-domain 800\n', 'INGRESS_TAG_OVERLAP'),
    (' service instance 3000 ethernet\n  encapsulation dot1q 446\n  bridge-domain 446\n', 'SERVICE_INSTANCE_DRIFT'),
    (' ip address 192.0.2.1 255.255.255.0\n', 'INCOMPATIBLE_EVC_PARENT'),
    (' channel-group 1 mode active\n', 'OWNERSHIP_REQUIRES_REVIEW'),
])
def test_fresh_negative_gates(family, change, code):
    ctx, before, _, _, entry = fixture(family)
    fresh = observation(family, evc_config(family, change))
    fresh['vlan_lookups'] = before['vlan_lookups']
    assert evc.target_blocker(entry, fresh, ctx) == code


def test_distinct_profiles_and_me_database_prerequisite():
    ctx, before, _, _, entry = fixture('ME3600X')
    before['vlan_lookups'] = {}
    assert evc.target_blocker(entry, before, ctx) == 'VLAN_PREREQUISITE_UNAVAILABLE'
    assert not evc.supported_context(replace(ctx, platform='cisco_xe'))
    ctx, before, _, _, entry = fixture('ASR920')
    before['vlan_lookups'] = {}
    assert not evc.target_blocker(entry, before, ctx)


def test_me_database_conflict_and_unknown_verification():
    ctx, before, r, _, entry = fixture('ME3600X')
    after = post('ME3600X', r['inputs'])
    after['vlan_lookups'] = {}
    assert evc.verify(entry, before, after, ctx)['status'] == 'Unknown'
    before['objects'] = []
    assert evc.target_blocker(entry, before, ctx) == 'VLAN_PREREQUISITE_UNAVAILABLE'


@pytest.mark.parametrize('family', ['ME3600X', 'ASR920'])
@pytest.mark.parametrize('decision', ['Pending', 'Reject'])
def test_nonapproved_never_selected(tmp_path, monkeypatch, family, decision):
    _, _, r, original, _ = fixture(family)
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: pytest.fail('offline preparation connected'))
    prepared = ex.ExecutionService(tmp_path).prepare(original, {r['row_id']: decision}, expected_digest=original.digest)
    assert not prepared['summary']['selected']


@pytest.mark.parametrize('family,function', [('ME3600X', 'VLAN Database'), ('ME3600X', 'Interface Description'), ('ASR920', 'Interface Description')])
def test_non_evc_templates_selected_and_verified(tmp_path, monkeypatch, family, function):
    p = dict(management_ip=IP, vlan_id=445, name='Customer') if function == 'VLAN Database' else dict(management_ip=IP, interface='GigabitEthernet0/1', description='NEW')
    ctx, before, r, original, entry = fixture(family, inputs=p, function=function)
    prepared = ex.ExecutionService(tmp_path).prepare(original, {r['row_id']: 'Approve'}, expected_digest=original.digest)
    assert len(prepared['summary']['selected']) == 1
    after = observation(family, evc_config(family, parent=' description NEW\n mtu 9000\n shutdown\n'))
    monkeypatch.setattr(ex, 'VlanService', lambda **kw: SimpleNamespace(lookup=lambda *a, **k: dict(status='present', name='Customer', operational_status='active')))
    result = ex._verify_observed(None, ctx, None, entry, before, after=after if function != 'VLAN Database' else None)
    # InterfaceService supplies independent description evidence in real collections.
    if function != 'VLAN Database':
        after['interfaces'][0]['port_description'] = 'NEW'
        result = ex._verify_observed(None, ctx, None, entry, before, after=after)
    assert result['status'] == 'Verified'


@pytest.mark.parametrize('family', ['ME3600X', 'ASR920'])
@pytest.mark.parametrize('failure', ['', 'reject', 'timeout'])
def test_real_lifecycle_exact_order_partial_save_recovery(tmp_path, monkeypatch, family, failure):
    ctx, before, r, original, entry = fixture(family)
    verifier = ex._verify_observed
    saves = fake_runtime(monkeypatch, ctx, before)
    monkeypatch.setattr(ex, '_verify_observed', verifier)
    after = post(family, r['inputs'])
    calls = iter([before, after])
    monkeypatch.setattr(ex, '_observe', lambda *a: next(calls))
    send = WorkerCLI.run_command
    def command(self, cmd, **kw):
        if cmd.startswith('bridge-domain') and failure:
            self.sent.append(cmd)
            if failure == 'timeout':
                self.dead = True
                raise TimeoutError()
            return '% Invalid input'
        return send(self, cmd, **kw)
    monkeypatch.setattr(WorkerCLI, 'run_command', command)
    service = ex.ExecutionService(tmp_path / 'authority')
    prepared = service.prepare(original, {r['row_id']: 'Approve'}, expected_digest=original.digest)
    with pytest.raises(PlanError):
        service.confirm(prepared['reference'], summary_digest=prepared['summary_digest'])
    spool = service.confirm(prepared['reference'], summary_digest=prepared['summary_digest'], apply=True,
                            credentials={IP: DeviceCredentials('test-user', 'hidden')}, run_root=tmp_path / 'runs')
    row = next(spool.records())['payload']['rows'][0]
    assert row['status'] == {'': 'Verified', 'reject': 'Failed', 'timeout': 'Unknown'}[failure]
    assert len(saves) == (0 if failure == 'timeout' else 1)
    commands = entry['result']['commands']
    sent = WorkerCLI.instances[0].sent
    if not failure:
        assert sent == commands
    else:
        index = commands.index('bridge-domain 445')
        assert sent[:index + 1] == commands[:index + 1]
        assert sent[index + 1:] == ([] if failure == 'timeout' else ['end'])
    events = list(ResultJournal(spool.path / 'events.jsonl').records())
    assert any(e['stage'] == 'pre_row_evidence' for e in events)
    assert ex.export_results(spool.path, tmp_path / 'execution.xlsx').exists()
    with pytest.raises(PlanError):
        service.confirm(prepared['reference'], summary_digest=prepared['summary_digest'], apply=True)


@pytest.mark.parametrize('family', ['ME3600X', 'ASR920'])
def test_service_submode_and_independent_save(family):
    ctx, *_ = fixture(family)
    cli, channel = cli_with([b'configure terminal\nfixture(config)#',
        b'interface GigabitEthernet0/1\nfixture(config-if)#',
        b'service instance 3000 ethernet\nfixture(config-if-srv)#',
        b'end\nfixture#', b'write memory\n% Error saving configuration\nfixture#'])
    for cmd in ('configure terminal', 'interface GigabitEthernet0/1', 'service instance 3000 ethernet', 'end'):
        cli.execution_mode('fixture#', ctx.platform)
        cli.run_command(cmd)
    result = save_configuration(cli.session, ctx, cli=cli, exec_prompt='fixture#', timeout=10)
    assert result['status'] == 'Saved' and result['explicit_error']


@pytest.mark.parametrize('family', ['ME3600X', 'ASR920'])
@pytest.mark.parametrize('enc,outer,inner,rewrite', [
    ('Untagged', None, None, 'Push dot1q'),
    ('Untagged', None, None, 'None'),
    ('Dot1q', '445', None, 'Pop 1 symmetric'),
    ('Dot1q', '2-444,446-544', None, 'Push dot1q symmetric'),
    ('QinQ', '300', '200', 'Pop 2 symmetric'),
    ('QinQ', '100', '1-4094', 'Pop 1 symmetric'),
])
def test_configured_intent_matrix_and_mutations(family, enc, outer, inner, rewrite):
    p = evc_inputs()
    p.update(encapsulation=enc, rewrite=rewrite, split_horizon_group=0)
    p.pop('outer_vlan')
    if outer:
        p['outer_vlan'] = outer
    if inner:
        p['inner_vlan'] = inner
    if rewrite.startswith('Push'):
        p['push_vlan'] = 1402
    ctx, before, _, _, entry = fixture(family, inputs=p)
    after = post(family, p)
    assert evc.verify(entry, before, after, ctx)['status'] == 'Verified'
    altered = dict(p, split_horizon_group=1)
    assert evc.verify(entry, before, post(family, altered), ctx)['status'] == 'Failed'


@pytest.mark.parametrize('family', ['ME3600X', 'ASR920'])
def test_operational_conflict_and_unreliable_evidence(family):
    ctx, before, r, _, entry = fixture(family)
    key = r['inputs']['interface'] + ':3000'
    before['service_details'] = {key: dict(status='present', facts=[])}
    assert evc.target_blocker(entry, before, ctx) == 'SERVICE_OBSERVATION_CONFLICT'
    after = post(family, r['inputs'])
    after['service_details'] = {key: dict(status='absent')}
    assert evc.verify(entry, before, after, ctx)['status'] == 'Failed'
    after['configuration_reliable'] = False
    assert evc.verify(entry, before, after, ctx)['status'] == 'Unknown'
    after = post(family, r['inputs'])
    after['interfaces'] = []
    assert evc.verify(entry, before, after, ctx)['error_category'] == 'InterfaceEvidenceUnavailable'


@pytest.mark.parametrize('family', ['ME3600X', 'ASR920'])
def test_preserve_other_service_policies_and_optional_omissions(family):
    child = ' service instance 3000 ethernet\n  description OLD\n  encapsulation dot1q 445\n  rewrite ingress tag pop 1 symmetric\n  bridge-domain 445 split-horizon group 0\n  service-policy input CHILD\n'
    sibling = ' service instance 20 ethernet\n  encapsulation dot1q 800\n  bridge-domain 800\n  service-policy input OTHER\n'
    ctx, before, r, _, entry = fixture(family, evc_config(family, child + sibling, ' mtu 9000\n shutdown\n service-policy input PARENT\n'))
    # Rebuild actual full configuration with unrelated settings still present.
    text = evc_config(family, ' service instance 3000 ethernet\n' + ''.join('  ' + c + '\n' for c in child_commands(r['inputs'])) + sibling,
                      ' mtu 9000\n shutdown\n service-policy input PARENT\n')
    after = observation(family, text)
    after['vlan_lookups'] = before['vlan_lookups']
    assert evc.verify(entry, before, after, ctx)['status'] == 'Verified'
    damaged = observation(family, text.replace('  service-policy input OTHER\n', ''))
    damaged['vlan_lookups'] = before['vlan_lookups']
    assert evc.verify(entry, before, damaged, ctx)['status'] == 'Failed'


@pytest.mark.parametrize('family', ['ME3600X', 'ASR920'])
@pytest.mark.parametrize('timeout', [False, True])
def test_independent_row_continuation_and_unknown_gate(tmp_path, monkeypatch, family, timeout):
    ctx, before, r, _, _ = fixture(family)
    p2 = dict(evc_inputs(), service_instance_id=3001, outer_vlan='446')
    r2 = request(template(family).id, p2, row=4)
    original = plan([r, r2], {IP: before}, now=NOW)
    verifier = ex._verify_observed
    saves = fake_runtime(monkeypatch, ctx, before)
    monkeypatch.setattr(ex, '_verify_observed', verifier)
    p1 = r['inputs']
    def child(p, bd=True):
        return ' service instance ' + str(p['service_instance_id']) + ' ethernet\n' + ''.join(
            '  ' + c + '\n' for c in child_commands(p) if bd or not c.startswith('bridge-domain'))
    middle = observation(family, evc_config(family, child(p1, False), ' mtu 9000\n shutdown\n'))
    final = observation(family, evc_config(family, child(p1, False) + child(p2), ' mtu 9000\n shutdown\n'))
    for obs in (middle, final):
        obs['vlan_lookups'] = before['vlan_lookups']
    observations = iter([before, middle, middle, final])
    monkeypatch.setattr(ex, '_observe', lambda *a: next(observations))
    send = WorkerCLI.run_command
    failed = []
    def command(self, cmd, **kw):
        if cmd.startswith('bridge-domain') and not failed:
            failed.append(True)
            self.sent.append(cmd)
            if timeout:
                self.dead = True
                raise TimeoutError()
            return '% Invalid input'
        return send(self, cmd, **kw)
    monkeypatch.setattr(WorkerCLI, 'run_command', command)
    service = ex.ExecutionService(tmp_path / 'authority')
    prepared = service.prepare(original, {r['row_id']: 'Approve', r2['row_id']: 'Approve'}, expected_digest=original.digest)
    assert len(prepared['summary']['selected']) == 2
    spool = service.confirm(prepared['reference'], summary_digest=prepared['summary_digest'], apply=True,
                            credentials={IP: DeviceCredentials('test-user', 'hidden')}, run_root=tmp_path / 'runs')
    rows = next(spool.records())['payload']['rows']
    assert [r['status'] for r in rows] == (['Unknown', 'Not executed'] if timeout else ['Failed', 'Verified'])
    assert len(saves) == (0 if timeout else 1)


@pytest.mark.parametrize('family', ['ME3600X', 'ASR920'])
def test_fresh_collector_uses_service_detail_not_switchport(monkeypatch, family):
    ctx, before, _, _, entry = fixture(family)
    calls = []
    class Vlans:
        def collect(self, *a, **kw):
            return object()
        def lookup(self, session, context, vid, **kw):
            calls.append(('vlan', vid))
            return dict(status='present')
        def service_detail(self, session, context, target, sid, **kw):
            calls.append(('service', target, sid))
            return dict(status='absent', evidence=['scoped'])
    monkeypatch.setattr(ex, 'InterfaceService', lambda **kw: SimpleNamespace(collect=lambda *a, **k: []))
    monkeypatch.setattr(ex, 'VlanService', lambda **kw: Vlans())
    monkeypatch.setattr(ex.observations, 'project', lambda *a: dict(before))
    observed = ex._observe(None, ctx, None, [entry], 1)
    assert calls == ([('vlan', 445)] if family == 'ME3600X' else []) + [('service', 'GigabitEthernet0/1', 3000)]
    assert observed['service_details']['GigabitEthernet0/1:3000']['status'] == 'absent'


@pytest.mark.parametrize('family', ['ME3600X', 'ASR920'])
def test_aggregate_conflict_blocks(family):
    ctx, before, _, _, entry = fixture(family)
    before['audit'][0]['configuration_findings'].append(dict(code='PORT_CHANNEL_CONFIG_CONFLICT'))
    assert evc.target_blocker(entry, before, ctx) == 'PORT_CHANNEL_CONFIG_CONFLICT'

