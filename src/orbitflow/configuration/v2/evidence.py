"""Request-scoped projection of preserved typed facts, without CLI parsing."""
from orbitflow.vendors.interface_names import canonical_interface_name
from .catalogue import BY_ID, FAMILIES


def scoped_evidence(request, observation):
    t, p = BY_ID[request["template_id"]], request["inputs"]
    if t.family == "All":
        return []
    key = lambda name: canonical_interface_name(FAMILIES[t.family][0], name)
    target = p.get("interface", "")
    logical = target + (f".{p['subinterface']}" if "subinterface" in p else "")
    names = {key(target), key(logical)} - {""}
    vids = set(p.get("vlans", []))
    vids.update(p[k] for k in ("vlan_id", "native_vlan", "pvid") if k in p)
    if t.family == "ME3600X" and t.function == "EVC":
        vids.add(p["bridge_domain"])
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
                if t.function == "EVC" and child["kind"] == "service_instance":
                    if child["value"] == str(p["service_instance"]):
                        whole(child)
                else:
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
        if kind in {"member", "methodology_member"} and key(str(value).split(" service-instance ")[0]) in names and (t.function != "EVC" or str(value).split(" service-instance ")[-1] == str(p["service_instance"])):
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
    return sorted(result, key=lambda e: (e["source_filename"], e["line"]))
