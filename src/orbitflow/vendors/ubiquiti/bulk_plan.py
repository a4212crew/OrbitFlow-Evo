"""EdgeSwitch proposals with explicit participation/tagging removal semantics."""


def render(template, p, existing=None):
    if template.function == "VLAN Database":
        return ["vlan database", f"vlan {p['vlan_id']}", f"vlan name {p['vlan_id']} \"{p['name']}\"", "exit"]
    lines = ["configure", f"interface {p['interface']}"]
    if p.get("description"):
        lines += [f"description \"{p['description']}\""]
    if template.function == "VLAN Port":
        desired = set(p.get("vlans", []))
        remove = desired if p.get("action") == "Remove" else set()
        if p.get("action") == "Replace" and existing is not None:
            remove = set(existing.get("tagged_vlans", [])) - desired
            if p.get("replace_untagged") == "Yes":
                remove |= set(existing.get("referenced_vlans", [])) - desired - {p.get("pvid")}
        for vid in sorted(remove):
            lines += [f"no vlan tagging {vid}", f"vlan participation exclude {vid}"]
        if p.get("action") != "Remove":
            for vid in sorted(desired):
                lines += [f"vlan participation include {vid}"]
                if p.get("mode", "Tagged") == "Tagged":
                    lines += [f"vlan tagging {vid}"]
        if p.get("mode", "Tagged") == "Access" or "pvid" in p:
            vid = p["pvid"] if "pvid" in p else p["vlans"][0]
            # PVID does not establish membership; preserve other participants.
            included = desired if p.get("action") != "Remove" else set()
            current = set(existing.get("referenced_vlans", [])) if existing else set()
            if vid not in included and (vid not in current or vid in remove):
                lines += [f"vlan participation include {vid}"]
            lines += [f"vlan pvid {vid}"]
    return lines + ["exit", "exit"]
