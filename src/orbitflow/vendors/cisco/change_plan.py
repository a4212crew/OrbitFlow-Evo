"""Offline, allowlisted configuration rendering; no device execution support."""

PROFILES = {
    ("cisco_ios", "C3750X", "c3750x_switching"),
    ("cisco_xe", "C3850", "c3850_switching"),
}


def render_vlan(identity, vlan_id, vlan_name, *, already_correct=False):
    if (identity["platform"], identity["device_family"], identity["capability_profile"]) not in PROFILES:
        raise ValueError("unsupported configuration profile")
    if already_correct:
        return []
    return ["configure terminal", f"vlan {vlan_id}", f"name {vlan_name}", "end"]
