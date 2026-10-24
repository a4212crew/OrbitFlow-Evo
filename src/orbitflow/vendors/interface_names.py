"""Canonical join keys for known interface aliases; never infer VLAN identity."""

import re

from orbitflow.vendors.huawei.interfaces import _canonical_interface_name


def canonical_interface_name(platform: str, name: str, *, normalize_aggregation=False) -> str:
    """Return a device-local join key, preserving callers' source/display names.

    With normalize_aggregation=True, EdgeSwitch configuration ``lag N`` and
    observed logical port ``3/N`` identify the same aggregate; physical ``0/N``
    ports remain distinct. The default preserves legacy audit/planning keys.
    """
    if platform == "huawei_vrp":
        return _canonical_interface_name(name.strip())
    key = name.strip().casefold()
    if normalize_aggregation and platform == "ubiquiti_edgeswitch":
        match = re.fullmatch(r"(?:lag\s+|3/)(\d+)", key)
        if match:
            return "3/" + str(int(match[1]))
    if platform in {"cisco_ios", "cisco_xe", "cisco_xr"}:
        match = re.fullmatch(r"([a-z-]+)\s*(\d.*)", key)
        if match:
            prefix, suffix = match.groups()
            prefix = {
                "gi": "gigabitethernet", "gig": "gigabitethernet",
                "te": "tengige", "tengigabitethernet": "tengige",
                "fa": "fastethernet", "et": "ethernet", "eth": "ethernet",
                "po": "port-channel", "be": "bundle-ether",
                "lo": "loopback", "vl": "vlan", "tu": "tunnel",
                "hu": "hundredgige", "hundredgigabitethernet": "hundredgige",
                "fo": "fortygige", "fortygigabitethernet": "fortygige",
            }.get(prefix, prefix)
            return prefix + suffix
    return key
