"""Read-only switchport collection over a borrowed resolved session and CLI."""
import re
from orbitflow.logging import module_logger
from orbitflow.vendors.configuration import PROFILES
from orbitflow.vendors.cisco import switchport as cisco
from orbitflow.vendors.ubiquiti import switchport as edge


class SwitchportCapabilityError(Exception):
    """Unsupported, rejected or unrecognized switchport observation."""


def supported_context(context):
    return (context.device_family, context.platform, context.capability_profile) in {
        ('C3750X', 'cisco_ios', 'c3750x_switching'),
        ('C3850', 'cisco_xe', 'c3850_switching'),
        ('EdgeSwitch', 'ubiquiti_edgeswitch', ''),
        ('EdgeSwitch', 'ubiquiti_edgeswitch', 'edgeswitch'),
    }


class SwitchportService:
    def __init__(self, *, timeout=10.0):
        self.timeout = timeout

    def collect(self, session, context, interface, *, cli):
        """Borrow resources; return typed facts, original labels and sanitized evidence."""
        from orbitflow.vendors.configuration_facts import _safe_source
        from orbitflow.vendors.interface_names import canonical_interface_name
        if not supported_context(context):
            raise SwitchportCapabilityError('unsupported switchport family')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/ .-]*', interface):
            raise SwitchportCapabilityError('invalid interface')
        normalized_interface = canonical_interface_name(context.platform, interface)
        adapter = edge if context.platform == 'ubiquiti_edgeswitch' else cisco
        profile = PROFILES[context.platform]
        cli.require_session(session)
        with module_logger('switchport', 'switchport') as (logger, _):
            logger.info('Switchport collection start', extra={'management_ip': context.management_ip})
            try:
                cli.configure(paging_command=profile.paging, prompt_pattern=profile.prompt,
                              rejected=profile.rejected_setup, platform_name=context.platform,
                              setup_commands=profile.setup_commands, timeout=self.timeout)
                text = cli.run_command(adapter.command(interface), timeout=self.timeout)
                if profile.rejected(text):
                    raise SwitchportCapabilityError('switchport command rejected')
                result = adapter.parse_switchport_output(_safe_source(text, context.platform))
                required = ('pvid', 'tagged_vlans', 'untagged_vlans') if adapter is edge else ('enabled', 'administrative_mode', 'allowed_vlans')
                if not result.fields or all(result.facts[k] is None for k in required):
                    raise SwitchportCapabilityError('switchport facts unavailable')
                if adapter is cisco and result.fields.get('Name') and canonical_interface_name(context.platform, result.fields['Name']) != normalized_interface:
                    raise SwitchportCapabilityError('switchport target mismatch')
                logger.info('Switchport collection complete', extra={'management_ip': context.management_ip})
                return result
            except Exception:
                logger.error('Switchport collection failed', extra={'management_ip': context.management_ip,
                                                                  'error_category': 'SwitchportCapabilityError'})
                raise SwitchportCapabilityError('switchport collection failed') from None
