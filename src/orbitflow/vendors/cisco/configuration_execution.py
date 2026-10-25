"""Approved Catalyst execution modes and read-only verification commands."""
import re
from orbitflow.vendors.aggregation import for_observation, relationship_uncertain
from orbitflow.vendors.interface_names import canonical_interface_name


def target_blocker(function, source, target, observed, platform):
    """Check normalized Catalyst target ownership and known switchport prerequisites.

    Never evaluate a plan, render CLI, or require equality with planning state.
    Interface existence/uniqueness is checked by the execution boundary first.
    """
    key = lambda name: canonical_interface_name(platform, name, normalize_aggregation=True)
    node = next(n for n in observed['facts'] if n['kind'] == 'interface' and key(n['value']) == key(source))
    if function == 'Interface Description':
        return '' if key(source) == key(target) else 'TARGET_DRIFT'
    aggregation = for_observation(observed, platform)
    owner = aggregation.owner(source)
    if relationship_uncertain(aggregation, source, node['children']) or (observed.get('aggregation') is not None and aggregation.capture_incomplete):
        return 'PORT_CHANNEL_OWNER_UNRESOLVED'
    if owner and function == 'Access Port':
        return 'PHYSICAL_PORT_CHANNEL_MEMBER'
    expected = owner or source
    audit = [a for a in observed['audit'] if key(a['config_interface_name']) == key(source)]
    if len(audit) != 1 or key(audit[0].get('configuration_owner', '')) != key(expected):
        return 'PORT_CHANNEL_OWNER_UNRESOLVED'
    if key(target) != key(expected):
        return 'TARGET_DRIFT'
    for audit in observed['audit']:
        if key(audit['config_interface_name']) in {key(source), key(target)} or key(audit.get('configuration_owner', '')) == key(target):
            if any(d['code'] == 'PORT_CHANNEL_CONFIG_CONFLICT' for d in audit.get('configuration_findings', [])):
                return 'PORT_CHANNEL_CONFIG_CONFLICT'
    node = next(n for n in observed['facts'] if n['kind'] == 'interface' and key(n['value']) == key(target))
    kinds = {n['kind'] for n in node['children']}
    modes = [n['value'] for n in node['children'] if n['kind'] == 'mode']
    if 'methodology_unknown' in kinds:
        return 'UNRESOLVED_CONFIGURATION'
    if 'routed' in kinds or function == 'Access Port' and 'trunk' in modes:
        return 'ACCESS_CONVERSION_BLOCKED' if function == 'Access Port' else 'TRUNK_CONVERSION_BLOCKED'
    if function == 'Trunk Port' and ('access' in modes or not modes and 'access' in kinds):
        return 'TRUNK_CONVERSION_BLOCKED'
    return ''

# Execution framing deliberately does not bind the presentation hostname.
HOST = r"[A-Za-z0-9_.-]*[A-Za-z0-9][A-Za-z0-9_.-]*"
PROMPT = HOST + r"(?:\([A-Za-z0-9_./:-]+\))?#"


def is_execution_prompt(prompt):
    """Validate hostname plus an optional arbitrary parenthesized mode token."""
    return re.fullmatch(PROMPT, prompt) is not None


def is_exec_prompt(prompt):
    """Privileged EXEC structure, excluding every configuration submode."""
    return re.fullmatch(HOST + '#', prompt) is not None


def verification_commands(function, inputs, target):
    if function == 'VLAN Database':
        return [f"show vlan id {inputs['vlan_id']}"]
    commands = ['show running-config', 'show interfaces description']
    if function != 'Interface Description':
        commands.append(f'show interfaces {target} switchport')
    if function == 'Access Port':
        commands.append(f"show vlan id {inputs['vlan_id']}")
    return commands
