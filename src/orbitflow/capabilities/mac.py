"""Independent read-only MAC snapshots and exact attachment resolution."""
from dataclasses import dataclass, replace
import re

from orbitflow.vendors.interface_names import canonical_interface_name


def normalize_mac(value):
    """Convert dotted, colon or hyphen notation; reject mixed/partial forms."""
    if not isinstance(value, str) or not re.fullmatch(
        r'(?:[0-9a-fA-F]{4}(?:\.[0-9a-fA-F]{4}){2}|[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}|[0-9a-fA-F]{4}(?:-[0-9a-fA-F]{4}){2})', value
    ):
        raise ValueError('Invalid MAC address')
    compact = re.sub(r'[.:-]', '', value).lower()
    return ':'.join(compact[i:i+2] for i in range(0, 12, 2))


@dataclass(frozen=True)
class MacEntry:
    mac: str
    domain: str
    attachment: str
    original_type: str
    kind: str
    scope: str = ''
    ifindex: str = ''


@dataclass(frozen=True)
class MacSnapshot:
    entries: tuple[MacEntry, ...]
    total: int
    scoped_totals: tuple[tuple[str, int], ...] = ()
    source: str = ''

    def lookup(self, *, mac=None, interface=None, domain=None, platform='', include_children=False):
        """Local exact filters; supplied table totals never affect selection counts."""
        mac = normalize_mac(mac) if mac is not None else None
        key = lambda n: canonical_interface_name(platform, n)
        def interface_matches(name):
            if interface is None:
                return True
            if key(name) == key(interface):
                return True
            return include_children and key(re.split(r'(?:[+.][Ee]fp\d+|\.\d+)$', name)[0]) == key(interface)
        entries = tuple(e for e in self.entries if
                        (mac is None or e.mac == mac) and
                        (domain is None or e.domain == str(domain)) and
                        interface_matches(e.attachment))
        return MacSnapshot(entries, len(entries), source=self.source)


def parse_mac_table(output, platform):
    """Dispatch pure vendor parsers; completed recognized empty tables succeed."""
    from orbitflow.vendors.mac_tables import parse_table
    return parse_table(output, platform)


class MacService:
    """No inventory discovery or enrichment dependencies; caller owns session."""
    def __init__(self, *, timeout=30, xr_location='0/RP0/CPU0'):
        if not re.fullmatch(r'\d+/(?:RP\d+|\d+)/CPU\d+', xr_location):
            raise ValueError('Invalid XR location')
        self.timeout, self.xr_location = timeout, xr_location

    def collect(self, session, context, *, cli=None):
        from orbitflow.vendors.mac_tables import operational_cli
        commands = {'cisco_ios': 'show mac address-table', 'cisco_xe': 'show mac address-table',
                    'cisco_xr': 'show l2vpn forwarding bridge-domain mac-address location ' + self.xr_location,
                    'huawei_vrp': 'display mac-address', 'ubiquiti_edgeswitch': 'show mac-addr-table all'}
        if context.platform not in commands:
            raise ValueError('Unsupported MAC platform')
        with operational_cli(session, context.platform, cli=cli, timeout=self.timeout) as shell:
            return replace(parse_mac_table(shell.run_command(commands[context.platform], timeout=self.timeout), context.platform), source=commands[context.platform])


@dataclass(frozen=True)
class AttachmentResolution:
    attachment: str
    physical: str = ''
    classification: str = 'unresolved'
    port_type: str = 'Unknown'
    semantics: str = ''


def display_interface(platform, name):
    """Presentation only; canonical join keys remain unchanged."""
    key = canonical_interface_name(platform, name)
    prefixes = {'gigabitethernet': 'GigabitEthernet', 'fastethernet': 'FastEthernet',
                'tengige': 'TenGigE' if platform == 'cisco_xr' else 'TenGigabitEthernet',
                'port-channel': 'Port-channel', 'bundle-ether': 'Bundle-Ether',
                'hundredgige': 'HundredGigE' if platform == 'cisco_xr' else 'HundredGigabitEthernet'}
    for prefix, full in prefixes.items():
        if key.startswith(prefix):
            return full + key[len(prefix):]
    return name


def resolve_attachment(attachment, platform, interfaces, vlans=None):
    """Resolve real observed/configured parents; never follow aggregate members."""
    key = lambda n: canonical_interface_name(platform, n)
    parent = re.split(r'(?:[+.][Ee]fp\d+|\.\d+)$', attachment)[0]
    if platform == 'ubiquiti_edgeswitch':
        lag = re.fullmatch(r'3/(\d+)', parent)
        if lag:
            parent = 'lag ' + lag[1]
        if parent == '5/1':
            return AttachmentResolution(attachment, classification='nonphysical')
    observed = [i for i in interfaces if key(i.port_name) == key(parent)]
    names = [i.port_name for i in observed]
    if platform == 'ubiquiti_edgeswitch' and re.fullmatch(r'3/\d+', attachment):
        # The MAC table itself observes the logical slot; no member selection.
        names = [parent]
    if not names and vlans is not None:
        names = [f.value for f in (getattr(vlans, 'configuration', None) or ())
                 if f.kind in {'interface', 'l2_interface'} and isinstance(f.value, str)
                 and key(f.value) == key(parent)]
    folded = key(parent)
    if attachment.upper() == 'CPU':
        return AttachmentResolution(attachment, classification='cpu')
    if attachment.startswith('(') or re.fullmatch(r'(?i)(?:pw|pseudowire)\d+(?:/\d+)*', attachment):
        return AttachmentResolution(attachment, classification='remote')
    if re.match(r'(?i)(?:vl|bv|bd|loopback|vlanif)', parent):
        return AttachmentResolution(attachment, classification='nonphysical')
    if platform == 'ubiquiti_edgeswitch' and not (parent.startswith('0/') or re.fullmatch(r'lag \d+', parent)):
        return AttachmentResolution(attachment)
    if len(names) != 1:
        return AttachmentResolution(attachment)
    aggregate = folded.startswith(('port-channel', 'bundle-ether', 'lag', 'eth-trunk'))
    ethernet = bool(re.match(r'(?:gigabitethernet|tengige|fastethernet|ethernet|hundredgige|fortygige|xgigabitethernet|(?:10|40|100)ge)\d', folded))
    if not aggregate and not ethernet and not (platform == 'ubiquiti_edgeswitch' and re.fullmatch(r'0/\d+', parent)):
        return AttachmentResolution(attachment, classification='nonphysical')
    profiles = [] if vlans is None else [p for p in vlans.interfaces if key(p.interface_name) == key(parent)]
    modes = {p.port_type for p in profiles if p.port_type}
    semantic = next(iter(modes)) if len(modes) == 1 else ''
    return AttachmentResolution(attachment, display_interface(platform, names[0]),
                                'aggregate' if aggregate else 'physical',
                                semantic if semantic in {'access', 'trunk', 'hybrid'} else 'Unknown', semantic)
