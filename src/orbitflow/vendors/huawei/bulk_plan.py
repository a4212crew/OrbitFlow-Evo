"""NE05E deterministic proposals; no VSI creation, save or device I/O."""
from orbitflow.vendors.interface_names import canonical_interface_name


def assess(template, p, observation):
    if template.function != "Subinterface VSI":
        return False, []
    name = canonical_interface_name("huawei_vrp", p["interface"] + f".{p['subinterface']}")
    nodes = [n for n in observation.get("facts", []) if n["kind"] == "interface"
             and canonical_interface_name("huawei_vrp", n["value"]) == name]
    if len(nodes) != 1:
        return False, ["AMBIGUOUS_SUBINTERFACE"] if nodes else []
    fields = nodes[0]["children"]
    values = lambda kind: [n["value"] for n in fields if n["kind"] == kind]
    kind = "termination" if p["encapsulation"] == "dot1q termination" else "encapsulation"
    conflicts = []
    if values("encapsulation" if kind == "termination" else "termination"):
        conflicts.append("SUBINTERFACE_ENCAPSULATION_CONVERSION")
    if values("vsi_binding") and values("vsi_binding") != [p["vsi"]]:
        conflicts.append("VSI_BINDING_CHANGE")
    matches = values(kind) == [[p["vlan_id"]]] and values("vsi_binding") == [p["vsi"]]
    matches &= not p.get("description") or values("description") == [p["description"]]
    matches &= "control_vid" not in p or values("control_vid") == [[p["control_vid"]]]
    return bool(matches), conflicts


def render(template, p, existing=None):
    if template.function == "VLAN Database":
        return ["system-view", f"vlan {p['vlan_id']}", f"description {p['name']}", "quit", "quit"]
    name = p["interface"]
    if template.function == "Subinterface VSI":
        name += f".{p['subinterface']}"
    lines = ["system-view", f"interface {name}"]
    if p.get("description"):
        lines += [f"description {p['description']}"]
    if template.function == "Subinterface VSI":
        if "control_vid" in p:
            lines += [f"control-vid {p['control_vid']} dot1q-termination"]
        lines += [(f"dot1q termination vid {p['vlan_id']}" if p["encapsulation"] == "dot1q termination"
                   else f"vlan-type dot1q {p['vlan_id']}"), f"l2 binding vsi {p['vsi']}"]
    return lines + ["quit", "quit"]
