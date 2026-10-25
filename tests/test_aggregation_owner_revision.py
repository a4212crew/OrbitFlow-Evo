"""Issue 149 owner revision: synthetic identities and no device connections."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from test_configuration_v2_approved_services import observation, template, NOW, IP
from orbitflow.configuration.v2.planning import request, plan
from orbitflow.configuration.execution import _check_target, ExecutionBlocked
from orbitflow.vendors.aggregation import for_observation
from orbitflow.vendors.configuration_facts import interface_settings

MEMBER = 'interface 0/17\n addport 3/2\nexit\n'
SETTINGS = 'interface 0/17\n description old\n vlan participation include 445\n vlan pvid 445\nexit\n'
PARENT = 'interface lag 2\n vlan participation include 445\n vlan pvid 445\nexit\n'

def fixture(body=MEMBER+SETTINGS, function='Interface Description'):
    obs = observation('EdgeSwitch', 'vlan database\n vlan 445\nexit\n'+PARENT+body+'end\n')
    # Actual operational collection observes one physical interface, independently
    # of how many saved configuration headings name it.
    obs['interfaces'] = list({i['port_name']: i for i in obs['interfaces']}.values())
    p = dict(management_ip=IP, interface='0/17')
    p.update(description='new') if function == 'Interface Description' else p.update(action='Add/Change', tagged_vlans='445')
    r = request(template('EdgeSwitch', function).id, p)
    return obs, r

def evaluate(obs, r):
    return plan([r], {IP: obs}, now=NOW).to_dict()['results'][0]

def test_membership_then_settings_exact_description_planning_and_execution():
    obs, r = fixture()
    original = deepcopy(obs['facts'])
    result = evaluate(obs, r)
    assert result['consistency'] == 'consistent'
    assert not result['deployment_ready']  # Pending remains pending.
    assert result['resolved_target'] == '0/17'
    assert 'interface 0/17' in result['commands']
    aggregation = for_observation(obs, 'ubiquiti_edgeswitch')
    assert aggregation.display_name(aggregation.owner('0/17')) == 'lag 2'
    _check_target(dict(request=r, result=result), obs, SimpleNamespace(platform='ubiquiti_edgeswitch'))
    assert obs['facts'] == original

@pytest.mark.parametrize('body', [MEMBER, MEMBER+SETTINGS+SETTINGS.replace('old', 'contradiction'), SETTINGS+MEMBER, MEMBER.replace('exit\n', '')+SETTINGS])
def test_missing_or_conflicting_settings_fail_closed(body):
    obs, r = fixture(body)
    row = evaluate(obs, r)
    assert 'INTERFACE_CONFIGURATION_ABSENT_OR_AMBIGUOUS' in row['blockers']
    with pytest.raises(ExecutionBlocked):
        _check_target(dict(request=r, result=row), obs, SimpleNamespace(platform='ubiquiti_edgeswitch'))

def test_multiple_addport_same_stanza_conflict_preserved():
    obs, r = fixture(MEMBER.replace(' addport 3/2', ' addport 3/2\n addport 3/3')+SETTINGS)
    aggregation = for_observation(obs, 'ubiquiti_edgeswitch')
    assert aggregation.owner('0/17') is None
    assert 'contradictory member binding' in aggregation.problems
    assert len(interface_settings(obs['facts'], 'ubiquiti_edgeswitch', '0/17')) == 1

def test_two_actual_observed_interfaces_remain_ambiguous():
    obs, r = fixture()
    obs['interfaces'].append(deepcopy(next(i for i in obs['interfaces'] if i['port_name'] == '0/17')))
    row = evaluate(obs, r)
    assert 'INTERFACE_ABSENT_OR_AMBIGUOUS' in row['blockers']
    with pytest.raises(ExecutionBlocked, match='INTERFACE_ABSENT_OR_AMBIGUOUS'):
        _check_target(dict(request=r, result=row), obs, SimpleNamespace(platform='ubiquiti_edgeswitch'))

def test_forwarding_child_new_code_at_both_gates():
    obs, r = fixture(function='VLAN Port')
    row = evaluate(obs, r)
    assert 'NOT_ALLOW_ON_CHILD_PORT_CHANNEL' in row['blockers']
    with pytest.raises(ExecutionBlocked, match='NOT_ALLOW_ON_CHILD_PORT_CHANNEL'):
        _check_target(dict(request=r, result=row), obs, SimpleNamespace(platform='ubiquiti_edgeswitch'))


def test_incomplete_membership_does_not_prove_standalone_forwarding():
    obs, r = fixture(function='VLAN Port')
    obs['aggregation'].update(complete=False, bindings=[],
        configuration_command='show running-config', problems=['incomplete member configuration'])
    row = evaluate(obs, r)
    assert 'OWNERSHIP_REQUIRES_REVIEW' in row['blockers']
    with pytest.raises(ExecutionBlocked, match='OWNERSHIP_REQUIRES_REVIEW'):
        _check_target(dict(request=r, result=row), obs, SimpleNamespace(platform='ubiquiti_edgeswitch'))


def test_description_verification_uses_same_authoritative_settings():
    from orbitflow.configuration.execution import _verify_observed
    before, r = fixture()
    row = evaluate(before, r)
    after = deepcopy(before)
    for i in after['interfaces']:
        if i['port_name'] == '0/17':
            i['port_description'] = 'new'
    for node in interface_settings(after['facts'], 'ubiquiti_edgeswitch', '0/17'):
        for c in node['children']:
            if c['kind'] == 'description':
                c['value'] = 'new'
    result = _verify_observed(None, SimpleNamespace(platform='ubiquiti_edgeswitch'), None,
        dict(request=r, result=row), before, after=after)
    assert result['status'] == 'Verified'

# Owner 06:01 UTC reproduction: member operational attributes precede settings.
MIXED = MEMBER.replace(' addport', ' auto-negotiate\n addport')

@pytest.mark.parametrize('function', ['Interface Description', 'VLAN Port'])
def test_mixed_member_operational_049_shared_gates_and_evidence(function, tmp_path):
    body = (MIXED+SETTINGS).replace('0/17', '0/49').replace('3/2', '3/1')
    # Supply the independently observed actual logical parent for this case.
    obs, _ = fixture((PARENT+body).replace('lag 2', 'lag 1'), function)
    r = request(template('EdgeSwitch', function).id,
        dict(management_ip=IP, interface='0/49', **(
            dict(description='new') if function == 'Interface Description' else
            dict(action='Add/Change', tagged_vlans='445'))))
    original = deepcopy(obs['facts'])
    row = evaluate(obs, r)
    from orbitflow.configuration.execution import ExecutionService
    draft = plan([r], {IP: obs}, now=NOW)
    prepared = ExecutionService(tmp_path / 'authority').prepare(draft,
        {r['row_id']: 'Approve'}, expected_digest=draft.digest)['summary']
    assert 'INTERFACE_CONFIGURATION_ABSENT_OR_AMBIGUOUS' not in row['blockers']
    assert not row['deployment_ready']
    assert row['resolved_target'] == '0/49'
    selected = interface_settings(obs['facts'], 'ubiquiti_edgeswitch', '0/49')
    assert len(selected) == 1
    assert any(c['kind'] == 'description' for c in selected[0]['children'])
    aggregation = for_observation(obs, 'ubiquiti_edgeswitch')
    assert aggregation.display_name(aggregation.owner('0/49')) == 'lag 1'
    context = SimpleNamespace(platform='ubiquiti_edgeswitch')
    if function == 'VLAN Port':
        assert not prepared['selected']
        assert 'NOT_ALLOW_ON_CHILD_PORT_CHANNEL' in prepared['skipped'][0]['blockers']
        assert 'NOT_ALLOW_ON_CHILD_PORT_CHANNEL' in row['blockers']
        with pytest.raises(ExecutionBlocked, match='^NOT_ALLOW_ON_CHILD_PORT_CHANNEL$'):
            _check_target(dict(request=r, result=row), obs, context)
        parent_request = request(template('EdgeSwitch', function).id,
            dict(management_ip=IP, interface='lag 1', action='Add/Change', tagged_vlans='445'))
        parent_row = evaluate(obs, parent_request)
        assert not parent_row['blockers']
        _check_target(dict(request=parent_request, result=parent_row), obs, context)
    else:
        assert len(prepared['selected']) == 1
        assert prepared['selected'][0]['result']['resolved_target'] == '0/49'
        assert row['consistency'] == 'consistent'
        assert 'interface 0/49' in row['commands']
        _check_target(dict(request=r, result=row), obs, context)
        from orbitflow.configuration.execution import _verify_observed
        after = deepcopy(obs)
        for i in after['interfaces']:
            if i['port_name'] == '0/49':
                i['port_description'] = 'new'
        for c in interface_settings(after['facts'], context.platform, '0/49')[0]['children']:
            if c['kind'] == 'description':
                c['value'] = 'new'
        assert _verify_observed(None, context, None, dict(request=r, result=row), obs,
                                after=after)['status'] == 'Verified'
    assert obs['facts'] == original
    member = next(n for n in original if n['value'] == '0/49')
    assert [c['excerpt'].strip() for c in member['children']] == [
        'auto-negotiate', 'addport 3/1', 'exit']
    assert [c['line'] for c in member['children']] == sorted(c['line'] for c in member['children'])

@pytest.mark.parametrize('body', [
    MIXED,
    MIXED+'interface 0/17\nexit\n',
    MIXED+SETTINGS+SETTINGS.replace('445', '545'),
    MIXED.replace('exit\n', '')+SETTINGS,
    MIXED+SETTINGS.replace('exit\n', ''),
    *[MIXED.replace(' auto-negotiate', ' '+command)+SETTINGS for command in (
        'unknown-member-option', 'port-security', 'shutdown', 'auto-negotiate unsupported',
        'vlan pvid 545', 'description competing')],
])
def test_mixed_stanza_unknown_unsafe_incomplete_and_conflicting_fail_closed(body):
    obs, r = fixture(body)
    row = evaluate(obs, r)
    assert 'INTERFACE_CONFIGURATION_ABSENT_OR_AMBIGUOUS' in row['blockers']
    with pytest.raises(ExecutionBlocked, match='INTERFACE_DECLARATION_ABSENT_OR_AMBIGUOUS'):
        _check_target(dict(request=r, result=row), obs, SimpleNamespace(platform='ubiquiti_edgeswitch'))


def test_mixed_stanza_contradictory_ownership_and_duplicate_identity_fail_closed():
    for duplicate in (False, True):
        obs, r = fixture(MIXED.replace(' addport 3/2', ' addport 3/2\n addport 3/3')+SETTINGS,
                         function='VLAN Port')
        if duplicate:
            obs['interfaces'].append(deepcopy(next(i for i in obs['interfaces'] if i['port_name'] == '0/17')))
        row = evaluate(obs, r)
        assert row['blockers']
        with pytest.raises(ExecutionBlocked):
            _check_target(dict(request=r, result=row), obs, SimpleNamespace(platform='ubiquiti_edgeswitch'))


def test_mixed_member_partial_ownership_and_post_verification_ambiguity():
    obs, r = fixture(MIXED+SETTINGS, function='VLAN Port')
    obs['aggregation'].update(complete=False, bindings=[],
        configuration_command='show running-config', problems=['incomplete member configuration'])
    row = evaluate(obs, r)
    assert 'OWNERSHIP_REQUIRES_REVIEW' in row['blockers']
    with pytest.raises(ExecutionBlocked, match='OWNERSHIP_REQUIRES_REVIEW'):
        _check_target(dict(request=r, result=row), obs, SimpleNamespace(platform='ubiquiti_edgeswitch'))

    from orbitflow.configuration.execution import _verify_observed
    before, r = fixture(MIXED+SETTINGS)
    after, _ = fixture(MIXED+SETTINGS+SETTINGS.replace('old', 'new'))
    result = _verify_observed(None, SimpleNamespace(platform='ubiquiti_edgeswitch'), None,
        dict(request=r, result=evaluate(before, r)), before, after=after)
    assert result == dict(status='Unknown', error_category='ConfigurationEvidenceUnavailable')
