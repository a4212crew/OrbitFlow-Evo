"""Approved EdgeSwitch execution modes and verification command selection."""
import re

from orbitflow.vendors.vlan_types import parse_vlan_list
from orbitflow.vendors.ubiquiti.prompts import extract_edgeswitch_hostname
from orbitflow.vendors.interface_names import canonical_interface_name


def target_blocker(function, source, target, observed, platform):
    """Check exact normalized EdgeSwitch target/ownership, without replanning."""
    key = lambda name: canonical_interface_name(platform, name)
    if key(source) != key(target):
        return 'TARGET_DRIFT'
    if function == 'Interface Description':
        return ''
    node = next(n for n in observed['facts'] if n['kind'] == 'interface' and key(n['value']) == key(source))
    if any(n['kind'] == 'aggregate' for n in node['children']):
        return 'OWNERSHIP_REQUIRES_REVIEW'
    audit = [a for a in observed['audit'] if key(a['config_interface_name']) == key(source)]
    if len(audit) != 1 or key(audit[0].get('configuration_owner', '')) != key(target):
        return 'OWNERSHIP_REQUIRES_REVIEW'
    return ''

HOST = r"[A-Za-z0-9_.-]*[A-Za-z0-9][A-Za-z0-9_.-]*"
WRAPPED_HOST = r"(?:<" + HOST + r">|" + HOST + r")"
MODE = r"[A-Za-z0-9][A-Za-z0-9 _./:-]*"
# Candidate framing is followed by vendor structural validation, including
# balanced arbitrary annotations through the existing pure hostname parser.
PROMPT = r"(?:" + HOST + r"|\([^\r\n]+\)(?:[ \t]+\(" + MODE + r"\))?)[ \t]*#"


def is_exec_prompt(prompt):
    """EXEC presentation only; inline/outer mode labels cannot establish EXEC."""
    try:
        hostname = extract_edgeswitch_hostname(prompt)
    except ValueError:
        return False
    # The shared parser also accepts specific outer config modes. Exclude those
    # here: only a plain host or a single balanced host/annotation wrapper is EXEC.
    if re.fullmatch(HOST, hostname) is None or not prompt.endswith('#'):
        return False
    body = prompt[:-1].rstrip()
    if body.startswith('('):
        depth = 0
        for index, character in enumerate(body):
            depth += (character == '(') - (character == ')')
            if depth == 0 and index != len(body) - 1:
                return False
    return True


def is_execution_prompt(prompt):
    """Validate EXEC, separate outer modes, or inline firmware mode presentation."""
    if is_exec_prompt(prompt):
        return True
    outer = re.fullmatch(r"(.+)[ \t]+\(" + MODE + r"\)[ \t]*#", prompt)
    if outer and is_exec_prompt(outer[1] + ' #'):
        return True
    return re.fullmatch(r"\(" + WRAPPED_HOST + r"[ \t]+" + MODE + r"\)[ \t]*#", prompt) is not None


def verification_commands(function, inputs, target):
    if function == 'VLAN Database':
        return [f"show vlan {inputs['vlan_id']}"]
    commands = ['show running-config', 'show interfaces status all']
    if function != 'Interface Description':
        commands.append(f'show interfaces switchport {target}')
    if function == 'VLAN Port':
        vids = set(parse_vlan_list(inputs.get('tagged_vlans', ''))) | ({inputs['pvid']} if 'pvid' in inputs else set())
        commands += [f'show vlan {v}' for v in sorted(vids)]
    return commands
