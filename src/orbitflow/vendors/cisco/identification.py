"""Deterministic Cisco identity parsing; no transport ownership lives here."""

from __future__ import annotations

import re


def parse_cisco_identity(version: str, inventory: str) -> dict[str, object] | None:
    if not re.search(r"Cisco (?:IOS|Internetwork Operating System|IOS XR)", version, re.I):
        return None
    xr = bool(re.search(r"IOS XR", version, re.I))
    xe = bool(re.search(r"IOS XE|IOS-XE", version, re.I))
    model_patterns = (
        (r"\bASR[- ]?920\b", r"\bASR-920(?:-[A-Z0-9]+)+\b", "ASR920", "asr920_evc", ("evc",)),
        (r"\bC3850\b|\bWS-C3850\b", r"\bWS-C3850(?:-[A-Z0-9]+)+\b", "C3850", "c3850_switching", ("classic_switchport",)),
        (r"\bC3750X\b|\bWS-C3750X\b", r"\bWS-C3750X(?:-[A-Z0-9]+)+\b", "C3750X", "c3750x_switching", ("classic_switchport",)),
        (r"\bME-?3600X\b", r"\bME-3600X(?:-[A-Z0-9]+)+\b", "ME3600X", "me3600x_evc", ("evc",)),
        (r"\bNCS[- ]?540\b|\bN540[A-Z0-9-]*\b", r"\bN540[A-Z0-9]*(?:-[A-Z0-9]+)+\b", "NCS540", "ncs540_l2", ("l2_subinterface",)),
    )
    combined = version + "\n" + inventory
    family = model = profile = "unknown"
    flags: tuple[str, ...] = ()
    for pattern, pid_pattern, family, profile, flags in model_patterns:
        match = re.search(pattern, combined, re.I)
        if match:
            # A normalized family drives capability selection, while the model
            # retains the most specific observed chassis PID.  Family-specific
            # matching avoids mistaking an inventory module PID for the chassis.
            pids = re.findall(pid_pattern, combined, re.I)
            model = max(pids, key=len) if pids else match.group(0).strip()
            break
    # ME3600X software is IOS, irrespective of EVC support.
    platform = (
        "cisco_xr" if xr or family == "NCS540" else
        "cisco_xe" if family in {"ASR920", "C3850"} or xe else
        "cisco_ios"
    )
    hostname = _first(version, r"(?mi)^([A-Za-z0-9_.-]+) uptime is ")
    serial = _first(inventory, r"(?mi)(?:SN:|Processor board ID)\s*([A-Za-z0-9-]+)")
    if not serial and platform == "cisco_xr":
        serial = _first(
            inventory,
            r"(?mi)^Serial Num\s+Rack Num[^\n]*\n(?:\s*-+\s*\n)?\s*([A-Za-z0-9-]+)\s+\d+\b",
        )
    if not serial:
        serial = _first(version, r"(?mi)^Processor board ID\s+([A-Za-z0-9-]+)")
    software = _first(version, r"(?i)(?:Cisco IOS XR Software, Version|Cisco IOS XE Software, Version|Version)\s+([^,\s]+)")
    uptime = _first(version, r"(?mi)^[A-Za-z0-9_.-]+ uptime is (.+)$")
    return dict(hostname=hostname, vendor="Cisco", platform=platform,
                device_family=family, hardware_model=model, capability_profile=profile,
                capability_flags=flags, serial_number=serial,
                software_version=software, uptime=uptime)


def _first(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""
