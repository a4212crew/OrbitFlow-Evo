"""Compose normalized observations; never infer VLANs from service identifiers."""
from dataclasses import dataclass, replace
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


def xr_untagged_peer_vlan(configuration, platform, attachment, domain):
    """MAC-only association from exact configured AC/domain and one peer tag.

    This does not change the untagged AC's ingress classification or VLAN state.
    """
    key = lambda n: canonical_interface_name(platform, n)
    interfaces = {}
    bindings = {}
    for node in configuration or ():
        if node.kind in {'interface', 'l2_interface'}:
            interfaces.setdefault(key(node.value), []).append(node)
        if node.kind == 'l2vpn':
            for group in node.children:
                if group.kind != 'bridge_group':
                    continue
                for bd in group.children:
                    if bd.kind != 'bridge_domain':
                        continue
                    identity = f'{group.value}/{bd.value}'
                    for ac in bd.children:
                        if ac.kind == 'attachment':
                            bindings.setdefault(key(ac.value), set()).add(identity)
    own = interfaces.get(key(attachment), [])
    if (len(own) != 1 or own[0].kind != 'l2_interface'
            or bindings.get(key(attachment)) != {domain}
            or not any(f.kind == 'untagged' for f in own[0].children)
            or any(f.kind == 'encapsulation' for f in own[0].children)):
        return ()
    if any(domain in identities and name not in interfaces for name, identities in bindings.items()):
        return ()
    tags = set()
    for name, nodes in interfaces.items():
        if domain not in bindings.get(name, set()):
            continue
        if len(nodes) != 1 or nodes[0].kind != 'l2_interface' or bindings.get(name) != {domain}:
            return ()
        encaps = [f.value for f in nodes[0].children if f.kind == 'encapsulation']
        if len(encaps) > 1 or (encaps and any(f.kind == 'untagged' for f in nodes[0].children)):
            return ()
        if len(encaps) == 1 and isinstance(encaps[0], tuple):
            tags.update(v for v in encaps[0] if type(v) is int and 1 <= v <= 4094)
    return tuple(tags) if len(tags) == 1 else ()


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
    from orbitflow.compliance.resolvers import forwarding_classifications
    classifications = {key(p.interface_name): p for p in forwarding_classifications(context, vlans)
                       } if context.device_family in {'ME3600X', 'ASR920', 'EdgeSwitch'} else {}
    result = []
    for entry in snapshot.entries:
        resolution = resolve_attachment(entry.attachment, context.platform, interfaces, vlans)
        classification = classifications.get(key(resolution.physical))
        if classification and resolution.classification in {'physical', 'aggregate'}:
            semantic = classification.port_type
            resolution = replace(resolution, semantics=semantic,
                                 port_type='trunk' if semantic == 'evc' else semantic if semantic in {'access', 'trunk', 'hybrid'} else 'Unknown')
        domains = (entry.domain,) if entry.domain else ()
        candidates = () if bridges is None else bridges.for_destination(entry.attachment)
        if context.platform == 'cisco_xr':
            domains = (f'{candidates[0].group}/{candidates[0].name}',) if len(candidates) == 1 else ()
        tags = set()
        classic = context.device_family in {'C3750X', 'C3850', 'EdgeSwitch'}
        numeric_scope = ((classic and entry.scope != 'bridge-domain') or context.platform == 'huawei_vrp'
                         or (context.device_family in {'ME3600X', 'ASR920'} and entry.scope == 'vlan'
                             and not re.search(r'[+.][Ee]fp\d+$', entry.attachment)))
        if numeric_scope and entry.domain.isdecimal():
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
        if context.platform == 'cisco_xr' and len(candidates) == 1 and vlans is not None and not tags:
            tags.update(xr_untagged_peer_vlan(getattr(vlans, 'configuration', ()),
                                            context.platform, entry.attachment, domains[0]))
        result.append(EnrichedMac(entry, resolution, domains, tuple(sorted(tags)),
                                  'resolved' if tags else 'unknown VLAN mapping'))
    return tuple(result)
