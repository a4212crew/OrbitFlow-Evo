"""Compose normalized observations; never infer VLANs from service identifiers."""
from dataclasses import dataclass
import re
from orbitflow.capabilities.mac import resolve_attachment
from orbitflow.vendors.interface_names import canonical_interface_name


def exact_efp_vlans(configuration, platform, parent, service_id, domain):
    """Resolve typed saved facts for one EFP; never use its numeric ID as VLAN."""
    key = lambda n: canonical_interface_name(platform, n)
    owners = [f for f in (configuration or ()) if f.kind == 'interface' and key(f.value) == key(parent)]
    if len(owners) != 1:
        return ()
    services = [s for s in owners[0].children if s.kind == 'service_instance' and s.value == service_id]
    if len(services) != 1:
        return ()
    bindings = {str(f.value) for f in services[0].children if f.kind == 'bridge_domain'}
    # Global BD member facts are separately scoped and exact.
    def visit(facts):
        for fact in facts:
            if fact.kind == 'bridge_domain':
                for member in fact.children:
                    if member.kind == 'member':
                        port, sep, sid = str(member.value).partition(' service-instance ')
                        if sep and key(port) == key(parent) and sid == service_id:
                            bindings.add(str(fact.value))
            visit(fact.children)
    visit(configuration or ())
    if bindings != {domain}:
        return ()
    encapsulations = [f.value for f in services[0].children if f.kind == 'encapsulation']
    if len(encapsulations) != 1 or not isinstance(encapsulations[0], tuple):
        return ()
    return encapsulations[0]


@dataclass(frozen=True)
class EnrichedMac:
    entry: object
    resolution: object
    domains: tuple[str, ...]
    vlans: tuple[int, ...]
    mapping: str


def lookup_vlan(observations, vlan):
    """Pure exact normalized VLAN lookup; unknown relationships never match."""
    if type(vlan) is not int or not 1 <= vlan <= 4094:
        raise ValueError('VLAN must be 1-4094')
    return tuple(item for item in observations if vlan in item.vlans)


def enrich(snapshot, context, interfaces=(), vlans=None, bridges=None):
    """Preserve every observation and unknown mapping; return immutable detail."""
    key = lambda n: canonical_interface_name(context.platform, n)
    profiles = () if vlans is None else vlans.interfaces
    result = []
    for entry in snapshot.entries:
        resolution = resolve_attachment(entry.attachment, context.platform, interfaces, vlans)
        domains = (entry.domain,) if entry.domain else ()
        candidates = () if bridges is None else bridges.for_destination(entry.attachment)
        if context.platform == 'cisco_xr':
            domains = (f'{candidates[0].group}/{candidates[0].name}',) if len(candidates) == 1 else ()
        tags = set()
        classic = context.device_family in {'C3750X', 'C3850', 'EdgeSwitch'}
        if (classic or context.platform == 'huawei_vrp') and entry.domain.isdecimal():
            if 1 <= int(entry.domain) <= 4094:
                tags.add(int(entry.domain))
        # A concrete service attachment limits lookup to its own profile; a remote
        # bridge attachment may use all exact AC profiles of its unique domain.
        parent = re.split(r'(?:[+.][Ee]fp\d+|\.\d+)$', entry.attachment)[0]
        efp = re.search(r'[+.][Ee]fp(\d+)$', entry.attachment)
        if efp and vlans is not None:
            tags.update(exact_efp_vlans(vlans.configuration, context.platform, parent, efp[1], entry.domain))
        for profile in profiles:
            details = profile.service_details or (profile,)
            for detail in details:
                if efp:
                    continue  # Aggregate profiles do not retain exact EFP identity.
                if context.platform == 'cisco_xr':
                    allowed = (len(candidates) == 1 and getattr(detail, 'service_binding_name', '') == domains[0]
                               and getattr(detail, 'service_binding_type', '') == 'bridge-domain') and any(key(a.interface) == key(detail.interface_name) for a in candidates[0].attachments)
                    if not entry.attachment.startswith('(') and not re.match(r'(?i)(?:BD id:|BVI?\d)', entry.attachment):
                        allowed = allowed and key(detail.interface_name) == key(entry.attachment)
                else:
                    allowed = key(detail.interface_name) == key(entry.attachment)
                if not allowed:
                    continue
                for mapping in detail.service_mappings:
                    source, sep, destination = mapping.partition(' -> ')
                    if sep and destination in ((candidates[0].name,) if context.platform == 'cisco_xr' and len(candidates) == 1 else domains) and source.isdecimal() and 1 <= int(source) <= 4094:
                        tags.add(int(source))
        result.append(EnrichedMac(entry, resolution, domains, tuple(sorted(tags)),
                                  'resolved' if tags else 'unknown VLAN mapping'))
    return tuple(result)
