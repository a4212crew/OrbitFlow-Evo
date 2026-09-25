"""Canonical join keys for known interface aliases; never infer VLAN identity."""

import re

from orbitflow.vendors.huawei.interfaces import _canonical_interface_name


def canonical_interface_name(platform: str, name: str) -> str:
    if platform == "huawei_vrp":
        return _canonical_interface_name(name.strip())
    key = name.strip().casefold()
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
