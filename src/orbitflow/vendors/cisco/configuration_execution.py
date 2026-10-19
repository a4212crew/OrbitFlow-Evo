"""Approved Catalyst execution modes and read-only verification commands."""
import re

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
