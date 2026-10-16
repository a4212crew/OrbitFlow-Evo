"""Approved Catalyst execution modes and read-only verification commands."""


def expected_mode(command, previous, exec_prompt):
    base = exec_prompt[:-1]
    if command == 'configure terminal':
        return {base + '(config)#'}
    if command.startswith('interface '):
        return {base + '(config-if)#'}
    if command.startswith('vlan '):
        return {base + '(config-vlan)#', base + '(config-vl)#'}
    return {exec_prompt} if command == 'end' else {previous}


def verification_commands(function, inputs, target):
    if function == 'VLAN Database':
        return [f"show vlan id {inputs['vlan_id']}"]
    commands = ['show running-config', 'show interfaces description']
    if function != 'Interface Description':
        commands.append(f'show interfaces {target} switchport')
    if function == 'Access Port':
        commands.append(f"show vlan id {inputs['vlan_id']}")
    return commands
