"""Approved EdgeSwitch execution modes and verification command selection."""
from orbitflow.vendors.vlan_types import parse_vlan_list


def expected_mode(command, previous, exec_prompt):
    base = exec_prompt[:-1].rstrip()
    if command == 'configure':
        return {base + ' (Config)#'}
    if command == 'vlan database':
        return {base + ' (Vlan)#'}
    if command.startswith('interface '):
        return {base + ' (Interface ' + command[len('interface '):] + ')#'}
    if command == 'exit':
        return {base + ' (Config)#'} if ' (Interface ' in previous else {exec_prompt}
    return {previous}


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
