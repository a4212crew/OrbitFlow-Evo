"""Independent IOS-XR operational bridge-domain attachment snapshots."""
from dataclasses import dataclass
import re
from orbitflow.vendors.interface_names import canonical_interface_name


@dataclass(frozen=True)
class BridgeAttachment:
    interface: str = ''
    neighbor: str = ''
    pw_id: str = ''
    state: str = ''
    backup: bool = False
    static_count: int | None = None
    bvi_count: int | None = None


@dataclass(frozen=True)
class BridgeDomain:
    group: str
    name: str
    internal_id: str
    state: str
    attachments: tuple[BridgeAttachment, ...]
    counts: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class BridgeSnapshot:
    domains: tuple[BridgeDomain, ...]

    def lookup(self, *, interface=None, neighbor=None, pw_id=None, internal_id=None):
        """Return all exact candidates, exposing ambiguity rather than choosing one."""
        if interface is None and internal_id is None and (neighbor is None or pw_id is None):
            raise ValueError('Exact bridge lookup key required')
        key = lambda s: canonical_interface_name('cisco_xr', re.sub(r'(?i)^BV(?=\d)', 'BVI', s))
        return tuple(d for d in self.domains if
                     (internal_id is None or d.internal_id == str(internal_id)) and
                     (interface is None or any(key(a.interface) == key(interface) for a in d.attachments)) and
                     (neighbor is None or any(a.neighbor == neighbor and a.pw_id == str(pw_id) for a in d.attachments)))

    def for_destination(self, destination):
        remote = re.fullmatch(r'\(([^, ]+),\s*(\d+)\)', destination)
        routed = re.fullmatch(r'BD id:\s*(\d+)', destination)
        if remote:
            return self.lookup(neighbor=remote[1], pw_id=remote[2])
        if routed:
            return self.lookup(internal_id=routed[1])
        return self.lookup(interface=destination)


def parse_bridge_domains(output):
    """Parse supplied summary output without treating service references as ports."""
    if re.search(r'(?i)invalid input|error:|--more--|unknown command', output):
        raise ValueError('Bridge collection failed or incomplete')
    domains, header, attachments, counts, section = [], None, [], [], ''
    def finish():
        if header:
            domains.append(BridgeDomain(*header, tuple(attachments), tuple(counts)))
    for raw in output.splitlines():
        line = raw.strip()
        match = re.match(r'Bridge group: (.*?), bridge-domain: (.*?), id: (\d+), state: (\S+)', line)
        if match:
            finish()
            header = (match[1], match[2], match[3], match[4].rstrip(','))
            attachments, counts = [], []
            section = ''
            continue
        if header is None:
            continue
        if line.startswith('List of '):
            section = line
            continue
        if not line:
            continue
        count = re.search(r'(Static|BVI) MAC addresses:\s*(\d+)', line)
        pw = re.match(r'Neighbor (\S+) pw-id (\d+), state: (\w+)', line)
        ac = re.match(r'(\S+), state: (\w+)', line)
        if pw:
            attachments.append(BridgeAttachment(neighbor=pw[1], pw_id=pw[2], state=pw[3], backup=bool(re.search(r'\bbackup\b', line)), static_count=int(count[2]) if count and count[1] == 'Static' else None))
        elif ac:
            attachments.append(BridgeAttachment(interface=ac[1], state=ac[2], static_count=int(count[2]) if count and count[1] == 'Static' else None,
                                                bvi_count=int(count[2]) if count and count[1] == 'BVI' else None))
        elif line.startswith('Number of'):
            counts.extend((k.strip(), int(v)) for k, v in re.findall(r'([^:,]+):\s*(\d+)', line))
        elif section and ('state:' in line or re.match(r'(?:Neighbor|BV|Te|Gi|Hu|BE|Bundle|TenGigE|GigabitEthernet)', line)):
            raise ValueError('Malformed bridge attachment')
    finish()
    if not domains:
        raise ValueError('Unrecognized bridge-domain output')
    return BridgeSnapshot(tuple(domains))


class BridgeDomainService:
    """Collect independently, borrowing the caller's session and optional CLI."""
    def collect(self, session, context, *, cli=None):
        if context.platform != 'cisco_xr':
            raise ValueError('Operational bridge domains require IOS-XR')
        from orbitflow.vendors.mac_tables import operational_cli
        with operational_cli(session, context.platform, cli=cli) as shell:
            return parse_bridge_domains(shell.run_command('show l2vpn bridge-domain', timeout=30))
