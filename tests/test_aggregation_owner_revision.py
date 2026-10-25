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
