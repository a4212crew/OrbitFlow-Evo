"""EdgeSwitch proposals with explicit participation/tagging removal semantics."""


def render(template, p, existing=None):
    if template.function == "VLAN Database":
        return ["vlan database", f"vlan {p['vlan_id']}", f"vlan name {p['vlan_id']} \"{p['name']}\"", "exit"]
    lines = ["configure", f"interface {p['interface']}"]
    if p.get("description"):
        lines += [f"description \"{p['description']}\""]
    if template.function == "VLAN Port":
        desired = set(p["vlans"])
        remove = desired if p["action"] == "Remove" else set()
        if p["action"] == "Replace" and existing is not None:
            remove = set(existing.get("referenced_vlans", [])) - desired
        for vid in sorted(remove):
            lines += [f"no vlan tagging {vid}", f"vlan participation exclude {vid}"]
        if p["action"] != "Remove":
            for vid in sorted(desired):
                lines += [f"vlan participation include {vid}"]
                if p["mode"] == "Tagged":
                    lines += [f"vlan tagging {vid}"]
            if p["mode"] == "Access" or "pvid" in p:
                lines += [f"vlan pvid {p.get('pvid', p['vlans'][0])}"]
    return lines + ["exit", "exit"]
