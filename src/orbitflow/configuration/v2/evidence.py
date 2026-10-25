"""Request-scoped projection of preserved typed facts, without CLI parsing."""
from orbitflow.vendors.interface_names import canonical_interface_name
from .catalogue import BY_ID, FAMILIES


def scoped_evidence(request, observation):
    t, p = BY_ID[request["template_id"]], request["inputs"]
    if t.family == "All":
        return []
    key = lambda name: canonical_interface_name(FAMILIES[t.family][0], name, normalize_aggregation=True)
    target = p.get("interface", "")
    logical = target + (f".{p['subinterface']}" if "subinterface" in p else "")
    names = {key(target), key(logical)} - {""}
    vids = set(p.get("vlans", []))
    if 'tagged_vlans' in p:
        from orbitflow.vendors.vlan_types import parse_vlan_list
        vids.update(parse_vlan_list(p['tagged_vlans']))
    vids.update(p[k] for k in ("vlan_id", "native_vlan", "pvid") if k in p)
    if t.family == "ME3600X" and t.function == "EVC":
        vids.add(p["bridge_domain"])
    port_only = t.family == 'EdgeSwitch' and t.function == 'VLAN Port'
    if port_only:
        vids.clear()
    for row in observation.get("audit", []):
        if key(row.get("config_interface_name", "")) in names:
            names.add(key(row.get("configuration_owner", "")))
    result = []
    def append(node):
        e = {k: node[k] for k in ("source_filename", "line", "excerpt")}
        if e not in result:
            result.append(e)
    def whole(node):
        append(node)
        for child in node.get("children", []):
            whole(child)
    def select(node, group=None):
        kind, value = node["kind"], node["value"]
        if kind == "bridge_group":
            group = value
        if kind in {"interface", "l2_interface"} and key(value) in names:
            append(node)
            for child in node.get("children", []):
                # Presentation only: all neighboring children remain in the
                # immutable observation and are evaluated by the planner.
                if (t.function == "EVC" and t.family in {"ME3600X", "ASR920"}
                        and child["kind"] == "service_instance"
                        and str(child["value"]) != str(p["service_instance_id"])):
                    continue
                whole(child)
            return True
        if kind == "vlan" and set(value if isinstance(value, list) else [int(value)] if str(value).isdigit() else []) & vids:
            whole(node)
            return True
        if kind == "vsi" and value == p.get("vsi"):
            whole(node)
            return True
        if t.function == "L2VPN" and kind == "bridge_domain" and (
                (value == p["bridge_domain"] and group == p["bridge_group"]) or any(
                    child["kind"] == "attachment" and key(child["value"]) in names
                    for child in node.get("children", []))):
            whole(node)
            return True
        if kind == "attachment" and key(value) in names:
            whole(node)
            return True
        if kind in {"member", "methodology_member"} and key(str(value).split(" service-instance ")[0]) in names and (t.function != "EVC" or str(value).split(" service-instance ")[-1] == str(p["service_instance_id"])):
            whole(node)
            return True
        start = len(result)
        for child in node.get("children", []):
            select(child, group)
        if len(result) > start:
            append(node)
            return True
        return False
    for node in observation.get("facts", []):
        select(node)
    # Lookup outputs remain in immutable observations for validation, not display.
    for vid in sorted(vids) if t.family not in {"ME3600X", "ASR920"} else ():
        for e in observation.get('vlan_lookups', {}).get(str(vid), {}).get('evidence', []):
            append(e)
    if t.function == 'EVC':
        detail = observation.get('service_details', {}).get(p['interface'] + ':' + str(p['service_instance_id']), {})
        for e in detail.get('evidence', []):
            append(e)
        if detail.get('status') in {'absent', 'error', 'unknown'}:
            status = 'does not exist (reliable lookup)' if detail['status'] == 'absent' else 'lookup unavailable; absence not established'
            append(dict(source_filename='Service lookup result', line=0,
                        excerpt=f"Interface {p['interface']}: service instance {p['service_instance_id']} {status}."))
        if detail.get('status') == 'present' and not any(n['kind'] == 'bridge_domain' for n in detail['facts']):
            append(dict(source_filename='Service lookup result', line=0,
                        excerpt=f"Interface {p['interface']}: service instance {p['service_instance_id']} present; forwarding evidence incomplete (bridge-domain unavailable)."))
    return sorted(result, key=lambda e: (e["source_filename"], e["line"]))
