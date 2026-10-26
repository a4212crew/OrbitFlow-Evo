"""Vendor-owned manual framing. Unsupported persistence paths fail before writes."""
import re
from orbitflow.capabilities.save import command_rejected
from orbitflow.vendors.configuration import PROFILES
from orbitflow.vendors.cisco import configuration_execution as cisco
from orbitflow.vendors.ubiquiti import configuration_execution as edge


def adapter(context):
    if context.platform in {'cisco_ios', 'cisco_xe'}:
        return cisco
    if context.platform == 'ubiquiti_edgeswitch':
        return edge
    # XR commit candidate ownership and VRP save questions are not implemented
    # by the shared save contract. Identification/backup support is insufficient.
    raise ValueError('Manual entry/save unsupported for identified platform')


def setup(cli, context, timeout):
    selected = adapter(context)
    profile = PROFILES[context.platform]
    cli.configure(paging_command=profile.paging, prompt_pattern=profile.prompt,
                  rejected=profile.rejected_setup, platform_name=context.platform,
                  setup_commands=profile.setup_commands, timeout=timeout)
    if not selected.is_exec_prompt(cli.prompt):
        raise ValueError('Privileged EXEC required')
    anchor = cli.prompt
    cli.execution_mode(anchor, context.platform)
    command = 'configure' if context.platform == 'ubiquiti_edgeswitch' else 'configure terminal'
    response = cli.run_command(command, timeout=timeout)
    if command_rejected(response) or not global_mode(cli.prompt, context.platform):
        raise ValueError('Global configuration mode not established')
    return anchor


def global_mode(prompt, platform):
    if platform == 'ubiquiti_edgeswitch':
        return bool(re.search(r'(?i)(?:\(config\)| config\))\s*#$', prompt))
    return bool(re.fullmatch(cisco.HOST + r'\(config\)#', prompt))


def finalize(cli, context, timeout):
    """Synchronize explicitly from unknown user submode; never close via exit."""
    selected = adapter(context)
    response = cli.run_command('end', timeout=timeout)
    if command_rejected(response) or not selected.is_exec_prompt(cli.prompt):
        raise ValueError('Save mode synchronization failed')
    return cli.prompt
