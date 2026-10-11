"""Pure configuration proposals. These commands are never executed here."""
from orbitflow.vendors.interface_names import canonical_interface_name


def assess(template, p, observation):
    """Compare typed vendor facts, preserving service scope and XR attachment identity."""
    if template.function not in {"EVC", "L2VPN"}:
        return False, []
    key = lambda n: canonical_interface_name(observation.get("identity", {}).get("platform", ""), n)
    name = p["interface"] + (f".{p['subinterface']}" if template.function == "L2VPN" else "")
    roots = observation.get("facts", [])
    conflicts = []
    if template.function == "L2VPN":
        for sibling in roots:
            if (sibling["kind"] in {"interface", "l2_interface"} and key(sibling["value"]).startswith(key(p["interface"]) + ".")
                    and key(sibling["value"]) != key(name)
                    and any(n["kind"] == "encapsulation" and n["value"] == [p["outer_vlan"]] for n in sibling["children"])):
                conflicts.append("INGRESS_TAG_OVERLAP")
    interfaces = [n for n in roots if n["kind"] in {"interface", "l2_interface"} and key(n["value"]) == key(name)]
    if len(interfaces) != 1:
        return False, conflicts + (["AMBIGUOUS_SERVICE_INTERFACE"] if interfaces else [])
    parent = interfaces[0]
    if template.function == "EVC":
        for sibling in parent["children"]:
            if sibling["kind"] != "service_instance" or sibling["value"] == str(p["service_instance"]):
                continue
            tag_kind = "untagged" if p["encapsulation"] == "untagged" else "encapsulation"
            tag_value = "untagged" if tag_kind == "untagged" else [p["outer_vlan"]]
            if any(n["kind"] == tag_kind and n["value"] == tag_value for n in sibling["children"]):
                conflicts.append("INGRESS_TAG_OVERLAP")
        services = [n for n in parent["children"] if n["kind"] == "service_instance" and n["value"] == str(p["service_instance"])]
        if len(services) != 1:
            return False, conflicts + (["AMBIGUOUS_SERVICE_INSTANCE"] if services else [])
        node = services[0]
    else:
        if parent["kind"] != "l2_interface":
            return False, ["ROUTED_SUBINTERFACE_CONVERSION"]
        node = parent
    def values(kind):
        return [n["value"] for n in node["children"] if n["kind"] == kind]
    untagged = p.get("encapsulation") == "untagged"
    tags_match = (values("untagged") == ["untagged"] if untagged else values("encapsulation") == [[p["outer_vlan"]]])
    tags_match &= values("inner_vlan") == ([[p["inner_vlan"]]] if "inner_vlan" in p else [])
    desc_match = not p.get("description") or any(n["kind"] == "description" and n["value"] == p["description"] for n in parent["children"])
    if template.function == "EVC":
        rewrites = values("tag_rewrite")
        rewrite_match = "pop_tags" not in p or (len(rewrites) == 1 and rewrites[0].get("operation") == "pop"
                         and rewrites[0].get("tag_count") == p["pop_tags"] and rewrites[0].get("symmetric") is True)
        # Omitting rewrite preserves it; a changed tag stack needs explicit review.
        blockers = ["PRESERVED_REWRITE_REQUIRES_REVIEW"] if rewrites and not tags_match and "pop_tags" not in p else []
        return bool(tags_match and desc_match and rewrite_match and values("bridge_domain") == [str(p["bridge_domain"])]), conflicts + blockers
    attachments = []
    for root in roots:
        if root["kind"] != "l2vpn":
            continue
        for group in root["children"]:
            if group["kind"] != "bridge_group":
                continue
            for domain in group["children"]:
                if domain["kind"] == "bridge_domain":
                    attachments += [(group["value"], domain["value"]) for n in domain["children"]
                                    if n["kind"] == "attachment" and key(n["value"]) == key(name)]
    expected = [(p["bridge_group"], p["bridge_domain"])]
    return bool(tags_match and desc_match and attachments == expected), conflicts + (["L2VPN_ATTACHMENT_CONFLICT"] if attachments and attachments != expected else [])


def render(template, p, existing=None):
    function = template.function
    lines = ["configure terminal"]
    if function == "VLAN Database":
        return lines + [f"vlan {p['vlan_id']}", f"name {p['name']}", "end"]
    name = p["interface"]
    if function == "L2VPN":
        name += f".{p['subinterface']}"
    lines.append(f"interface {name}" + (" l2transport" if function == "L2VPN" else ""))
    if p.get("description"):
        lines.append(f"description {p['description']}")
    if function == "Access Port":
        lines += ["switchport", "switchport mode access", f"switchport access vlan {p['vlan_id']}"]
    elif function == "Trunk Port":
        if not existing or existing.get("mode") != "trunk":
            lines += ["switchport"]
            if template.family == "C3750X":
                lines += ["switchport trunk encapsulation dot1q"]
            lines += ["switchport mode trunk"]
        action = "" if p["action"] == "Replace" else p["action"].lower() + " "
        lines += ["switchport trunk allowed vlan " + action + ",".join(map(str, sorted(p["vlans"])))]
        if "native_vlan" in p:
            lines += [f"switchport trunk native vlan {p['native_vlan']}"]
    elif function == "EVC":
        lines += [f"service instance {p['service_instance']} ethernet"]
        if p["encapsulation"] == "untagged":
            lines += ["encapsulation untagged"]
        else:
            lines += [f"encapsulation dot1q {p['outer_vlan']}" +
                      (f" second-dot1q {p['inner_vlan']}" if "inner_vlan" in p else "")]
        if "pop_tags" in p:
            lines += [f"rewrite ingress tag pop {p['pop_tags']} symmetric"]
        lines += [f"bridge-domain {p['bridge_domain']}"]
    elif function == "L2VPN":
        lines += [f"encapsulation dot1q {p['outer_vlan']}" +
                  (f" second-dot1q {p['inner_vlan']}" if "inner_vlan" in p else ""), "exit",
                  "l2vpn", f"bridge group {p['bridge_group']}", f"bridge-domain {p['bridge_domain']}",
                  f"interface {name}"]
    return lines + ["end"]
