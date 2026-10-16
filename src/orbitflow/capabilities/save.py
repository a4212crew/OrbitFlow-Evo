"""Standalone explicit configuration save, borrowing a synchronized CLI."""
import re
import math
from orbitflow.logging import module_logger


def command_rejected(text):
    return bool(re.search(r"(?im)(?:%\s*(?:error|invalid|unknown|incomplete|ambiguous|authorization|access denied)|invalid input|unknown command|unrecognized command|\berror\b|\bfailed\b|\bdenied\b|couldn't configure pvid\.|Failed to set VLAN (?:participation|tagging)\.|^\s*\^)", text))


def save_configuration(session, context, *, cli, exec_prompt, timeout):
    """Return Saved/Unknown independently from explicit error evidence; no retries."""
    from orbitflow.vendors.configuration_facts import _safe_source
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('save timeout must be finite and positive')
    from orbitflow.capabilities.switchport import supported_context
    if not supported_context(context):
        raise ValueError('unsupported save family')
    cli.require_session(session)
    with module_logger('configuration', 'execution') as (logger, _):
        logger.info('Save start', extra={'management_ip': context.management_ip})
        result = cli.save_configuration(exec_prompt, context.platform, timeout=timeout)
        result['response'] = _safe_source(result['response'], context.platform)
        result['explicit_error'] = command_rejected(result['response'])
        logger.info('Save complete; status=' + result['status'], extra={'management_ip': context.management_ip})
        return result
