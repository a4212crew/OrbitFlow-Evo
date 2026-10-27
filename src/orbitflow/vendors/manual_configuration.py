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


def setup(cli, context, timeout, *, setup_stage=None, prepare=True):
    """Enter global mode from verified EXEC; prepare=False reuses shell setup.

    The default preserves existing standalone setup behavior. Only grouped manual
    rows skip repeated paging/profile preparation on their exact live shell.
    """
    stage = setup_stage or (lambda _stage: None)
    selected = adapter(context)
    profile = PROFILES[context.platform]
    if prepare:
        stage('initial prompt/session preparation')
        cli.configure(paging_command=profile.paging, prompt_pattern=profile.prompt,
                      rejected=profile.rejected_setup, platform_name=context.platform,
                      setup_commands=profile.setup_commands, timeout=timeout)
    stage('privilege')
    if not selected.is_exec_prompt(cli.prompt):
        raise ValueError('Privileged EXEC required')
    anchor = cli.prompt
    cli.execution_mode(anchor, context.platform)
    command = 'configure' if context.platform == 'ubiquiti_edgeswitch' else 'configure terminal'
    stage('config entry')
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
    response = cli.synchronize_manual('end', timeout=timeout)
    if rejected(response) or not selected.is_exec_prompt(cli.prompt):
        raise ValueError('Save mode synchronization failed')
    return cli.prompt


def rejected(text):
    """Classify anchored diagnostics, never words inside literal echoes/prompts.

    Capture remains prompt-free; accumulating normalized receive text preserves
    diagnostics split across chunks. Raw transcript framing is not removed.
    """
    from orbitflow.vendors.ubiquiti.switchport import command_rejected as edge_rejected
    return edge_rejected(text) or bool(re.search(
        r"(?im)^\s*(?:%\s*(?:error|invalid|unknown|unrecognized|incomplete|ambiguous|authorization|access denied|failed|denied)"
        r"|(?:command )?authorization failed|access denied|(?:error|failed|denied)(?:\s|:|$)|invalid input|unknown command|unrecognized command"
        r"|couldn't configure pvid\.|Failed to set VLAN (?:participation|tagging)\.|\^)", text))
