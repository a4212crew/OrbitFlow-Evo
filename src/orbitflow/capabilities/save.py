"""Standalone explicit configuration save, borrowing a synchronized CLI."""
import re
import math
from time import monotonic
from orbitflow.logging import module_logger, capability_metadata


def command_rejected(text):
    from orbitflow.vendors.ubiquiti.switchport import command_rejected as edge_rejected
    return edge_rejected(text) or bool(re.search(r"(?im)(?:%\s*(?:error|invalid|unknown|incomplete|ambiguous|authorization|access denied)|invalid input|unknown command|unrecognized command|\berror\b|\bfailed\b|\bdenied\b|couldn't configure pvid\.|Failed to set VLAN (?:participation|tagging)\.|^\s*\^)", text))


def save_configuration(session, context, *, cli, exec_prompt, timeout, correlation=None, manual=False):
    """Return Saved/Unknown independently from explicit error evidence; no retries.

    Optional correlation selects run_id/row_id/digest for shared logs only.
    manual=True permits identified IOS/IOS-XE/EdgeSwitch platform framing beyond
    predefined family profiles; the default predefined family policy is unchanged.
    """
    from orbitflow.vendors.configuration_facts import _safe_source
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('save timeout must be finite and positive')
    from orbitflow.capabilities.switchport import supported_context
    from orbitflow.vendors.cisco.evc_execution import supported_context as supported_evc
    if not (supported_context(context) or supported_evc(context)
            or (manual is True and context.platform in {'cisco_ios', 'cisco_xe', 'ubiquiti_edgeswitch'})):
        raise ValueError('unsupported save family')
    cli.require_session(session)
    started = monotonic()
    metadata = capability_metadata(context, correlation, command='write memory', stage='save')
    with module_logger('configuration', 'execution') as (logger, _):
        logger.info('Save start', extra=metadata)
        try:
            result = cli.save_configuration(exec_prompt, context.platform, timeout=timeout)
            from orbitflow.vendors.manual_configuration import rejected as manual_rejected
            reject = manual_rejected if manual else command_rejected
            raw_error = reject(result['response']) if manual else False
            result['response'] = _safe_source(result['response'], context.platform)
            result['explicit_error'] = raw_error or reject(result['response'])
            logger.info('Save complete', extra=dict(metadata, outcome=result['status'],
                        error_category='CommandRejected' if result['explicit_error'] else '-',
                        elapsed_seconds=monotonic() - started))
            return result
        except Exception:
            logger.error('Save failed', exc_info=True, extra=dict(metadata, outcome='Failed',
                         elapsed_seconds=monotonic() - started, error_category='SaveCapabilityError'))
            raise
