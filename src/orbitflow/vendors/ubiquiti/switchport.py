"""Pure EdgeSwitch observations; membership and tagging remain independent."""
import re
from orbitflow.vendors.switchport_types import SwitchportObservation, labeled, vlan, vlans


def command(interface):
    return f'show interfaces switchport {interface}'


def parse_switchport_output(text):
    fields = labeled(text)
    protection = fields.get('Protected Port')
    match = re.fullmatch(r'(True|False)(?:\s+in Group\s+(\d+):?)?', protection or '', re.I)
    facts = dict(pvid=vlan(fields.get('General Mode PVID')),
                 untagged_vlans=vlans(fields.get('General Mode Untagged VLANs')),
                 tagged_vlans=vlans(fields.get('General Mode Tagged VLANs')),
                 forbidden_vlans=vlans(fields.get('General Mode Forbidden VLANs')),
                 name=fields.get('Name'),
                 protection=dict(enabled=match[1].lower() == 'true' if match else None,
                                 group=int(match[2]) if match and match[2] is not None else None,
                                 raw=protection))
    return SwitchportObservation(fields, facts, text)


def command_rejected(text):
    """Recognize observed EdgeSwitch diagnostic lines without interpreting suggestions."""
    return bool(re.search(r"(?im)^\s*(?:Command not found(?:\s*/\s*Incomplete command\. Use \? to list commands\.)?|Incomplete command\. Use \? to list commands\.|Value is out of range\. The valid range is 1 to 4093\.)\s*$", text))
