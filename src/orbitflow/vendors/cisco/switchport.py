"""Pure IOS/IOS-XE switchport grammar and approved collection command."""
from orbitflow.vendors.switchport_types import SwitchportObservation, labeled, vlan, vlans


def command(interface):
    return f'show interfaces {interface} switchport'


def parse_switchport_output(text):
    fields = labeled(text)
    facts = dict(enabled={'Enabled': True, 'Disabled': False}.get(fields.get('Switchport')),
                 administrative_mode=fields.get('Administrative Mode'),
                 operational_mode=fields.get('Operational Mode'),
                 access_vlan=vlan(fields.get('Access Mode VLAN')),
                 native_vlan=vlan(fields.get('Trunking Native Mode VLAN')),
                 allowed_vlans=vlans(fields.get('Trunking VLANs Enabled')))
    return SwitchportObservation(fields, facts, text)
