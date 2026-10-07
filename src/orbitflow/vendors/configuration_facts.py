"""Syntax-preserving VLAN evidence shared by the existing observation adapters.

Only recognized VLAN/interface statements enter the snapshot. No full config,
credentials, command output, or arbitrary unknown lines are retained. This is
observation, not relationship validation or compliance policy.
"""

import re

from orbitflow.logging import sanitize_text
from orbitflow.models import ConfigFact
from orbitflow.vendors.vlan_types import parse_vlan_list


_NAME = r"[\w./:-]+"
_LIST = r"[\d,\s-]+(?:to[\d,\s-]+)*"

# kind, expression, value conversion. Full matches prevent trailing secrets or
# unsupported modifiers from being mistaken for known safe syntax.
_COMMON = (
    ("description", r"description (.+)", "text"),
    ("shutdown", r"(shutdown|no shutdown|undo shutdown)", "text"),
)
_IOS = (
    ("vlan", rf"vlan ({_LIST})", "list"),
    ("bridge_domain", rf"bridge-domain ({_NAME})", "text"),
    ("service_instance", r"service instance (\d+) ethernet", "text"),
    ("member", rf"member ({_NAME} service-instance \d+)", "text"),
    ("mode", r"switchport mode (\w+)", "text"),
    ("trunk_encapsulation", r"switchport trunk encapsulation (\w+)", "text"),
    ("allowed", rf"switchport trunk allowed vlan ({_LIST}|all|none)", "list"),
    ("unsupported_allowed", r"switchport trunk allowed vlan ((?:add|remove|except) [\d,\s-]+)", "text"),
    ("access", r"switchport access vlan (\d+)", "list"),
    ("native", r"switchport trunk native vlan (\d+)", "list"),
    ("aggregate", r"channel-group (\d+)(?: mode \w+)?", "text"),
    ("encapsulation", rf"encapsulation dot1[qQ] ({_LIST})(?: second-dot1q \d+)?", "list"),
    ("inner_vlan", rf"encapsulation dot1[qQ] {_LIST} second-dot1q (\d+)", "list"),
    ("untagged", r"encapsulation (untagged)", "text"),
    ("routed", r"(no switchport)", "text"),
)
_XR = (
    ("l2vpn", r"(l2vpn)", "text"),
    ("bridge_group", rf"bridge group ({_NAME})", "text"),
    ("bridge_domain", rf"bridge-domain ({_NAME})", "text"),
    ("attachment", rf"(?:routed )?interface ({_NAME})", "text"),
    ("encapsulation", r"encapsulation dot1q (\d+)(?: second-dot1q \d+)?", "list"),
    ("inner_vlan", r"encapsulation dot1q \d+ second-dot1q (\d+)", "list"),
    ("untagged", r"encapsulation (untagged)", "text"),
)
_VRP = (
    ("vlan", rf"vlan(?: batch)? ({_LIST})", "list"),
    ("vsi", rf"vsi ({_NAME})(?: static)?", "text"),
    ("vsi_binding", rf"l2 binding vsi ({_NAME})", "text"),
    ("termination", rf"dot1q termination vid ({_LIST})", "list"),
    ("encapsulation", r"vlan-type dot1q (\d+)", "list"),
    ("control_vid", r"control-vid (\d+) dot1q-termination", "list"),
    ("mode", r"port link-type (\w+)", "text"),
    ("access", r"port default vlan (\d+)", "list"),
    ("trunk_pvid", r"port trunk pvid vlan (\d+)", "list"),
    ("hybrid_pvid", r"port hybrid pvid vlan (\d+)", "list"),
    ("allowed", rf"port trunk allow-pass vlan ({_LIST}|all)", "list"),
    ("tagged", rf"port hybrid tagged vlan ({_LIST}|all)", "list"),
    ("untagged_vlans", rf"port hybrid untagged vlan ({_LIST})", "list"),
    ("routed", r"(undo portswitch)", "text"),
)
_EDGE = (
    ("vlan_database", r"(vlan database)", "text"),
    ("vlan", rf"vlan ({_LIST})", "list"),
    ("pvid", r"vlan pvid (\d+)", "list"),
    ("include", rf"vlan participation include ({_LIST})", "list"),
    ("exclude", rf"vlan participation exclude ({_LIST})", "list"),
    ("tagged", rf"vlan tagging ({_LIST})(?: enable)?", "list"),
    ("untagged_vlans", rf"vlan tagging ({_LIST}) disable", "list"),
    ("aggregate", r"addport (\d+|lag \d+|\d+/\d+)", "text"),
)
_PATTERNS = {platform: tuple((kind, re.compile(pattern), conversion)
                            for kind, pattern, conversion in (*patterns, *_COMMON))
             for platform, patterns in (("cisco_ios", _IOS), ("cisco_xe", _IOS),
                                        ("cisco_xr", _XR), ("huawei_vrp", _VRP),
                                        ("ubiquiti_edgeswitch", _EDGE))}
_CONTAINERS = {"interface", "l2_interface", "service_instance", "l2vpn", "bridge_group",
               "bridge_domain", "vsi", "vlan_database", "vlan"}


def _safe_source(text):
    # Description/evidence are the only arbitrary source strings retained.
    # Also cover CLI-style secret labels separated by whitespace, not just '='.
    return re.sub(r"(?i)\b(password|passwd|secret|token|otp|private_key|authorization)\b[\s:=]+.*",
                  r"\1 [REDACTED]", sanitize_text(text))


def observe_configuration(output, platform, *, source_filename="running-config"):
    """Preserve known statements with one-based lines and actual source excerpts.

    The optional filename is the caller's inspected saved file, not a fabricated
    backup path. Online collection uses the explicit source label running-config.
    Repeated interface stanzas stay ordered here and are consolidated by audit.
    """
    roots, stack = [], []
    banner_end = None
    for number, raw in enumerate(output.splitlines(), 1):
        line = raw.strip()
        if banner_end is not None:
            if banner_end in line:
                banner_end = None
            continue
        if line.startswith("banner "):
            delimiter = line.split(maxsplit=2)[-1]
            delimiter = delimiter[:2] if delimiter.startswith("^") else delimiter[:1]
            if delimiter and line.count(delimiter) < 2:
                banner_end = delimiter
            continue
        indent = len(raw) - len(raw.lstrip())
        if not line or line == "#" or line == "!":
            if line in {"#", "!"}:
                while stack and stack[-1][0] >= indent:
                    stack.pop()
            continue
        if line in {"exit", "end", "return"}:
            if stack:
                stack.pop()
            continue
        if platform != "ubiquiti_edgeswitch":
            while stack and stack[-1][0] >= indent:
                stack.pop()
        entries = []
        interface = re.fullmatch(rf"interface ({_NAME}|lag \d+)(?: (l2transport))?", line)
        # XR interface statements nested under L2VPN are references only.
        if interface and not any(n[1][0] == "l2vpn" for n in stack):
            entries.append(("l2_interface" if interface[2] else "interface", interface[1]))
        else:
            for kind, pattern, conversion in _PATTERNS[platform]:
                match = pattern.fullmatch(line)
                if match:
                    value = match[1]
                    if conversion == "list":
                        value = value.upper() if value in {"all", "none"} else parse_vlan_list(value, range_word="to")
                    entries.append((kind, value))
        for kind, value in entries:
            node = [kind, value, number, _safe_source(raw), []]
            (stack[-1][1][4] if stack else roots).append(node)
            if kind in _CONTAINERS and (platform != "ubiquiti_edgeswitch" or kind in {"interface", "vlan_database"}):
                stack.append((indent, node))

    def freeze(node):
        kind, value, number, excerpt, children = node
        return ConfigFact(kind, _safe_source(value) if isinstance(value, str) else value,
                          sanitize_text(source_filename), number, excerpt,
                          tuple(freeze(child) for child in children))
    return tuple(freeze(node) for node in roots)
