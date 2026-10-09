"""Syntax-preserving VLAN evidence shared by the existing observation adapters.

Recognized VLAN/interface statements and sanitized forwarding exceptions
enter the snapshot. No full config, credentials or arbitrary unknown CLI is retained. This is
observation, not relationship validation or compliance policy.
"""

import re

from orbitflow.logging import sanitize_text
from orbitflow.models import ConfigFact, TagRewrite
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
    ("bridge_domain", rf"bridge-domain ({_NAME})(?: split-horizon group [0-9]+)?", "text"),
    ("service_instance", r"service instance (\d+) ethernet", "text"),
    ("member", rf"member ({_NAME} service-instance \d+)", "text"),
    ("mode", r"switchport mode (\w+)", "text"),
    ("trunk_encapsulation", r"switchport trunk encapsulation (\w+)", "text"),
    ("allowed", rf"switchport trunk allowed vlan ({_LIST}|all|none)", "list"),
    ("allowed_add", r"switchport trunk allowed vlan add ([\d,\s-]+)", "list"),
    ("allowed_remove", r"switchport trunk allowed vlan remove ([\d,\s-]+)", "list"),
    ("allowed_except", r"switchport trunk allowed vlan except ([\d,\s-]+)", "list"),
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
               "bridge_domain", "vsi", "vlan_database", "vlan", "methodology_interface", "methodology_context"}
# Tolerant Huawei spellings are review-only: never widen compliance facts.
_VRP_REVIEW_ENCAPSULATION = re.compile(
    next(pattern for kind, pattern, _ in _VRP if kind == "encapsulation").replace(" ", r"\s+"),
    re.IGNORECASE)


def _tag_rewrite(line):
    """Strict Cisco rewrite grammar; unknown combinations use review capture.

    Recognition is deliberately independent of model/release support. Preserve
    replacement tags separately from ingress encapsulation and domain binding.
    """
    match = re.fullmatch(r"rewrite ingress tag (pop|push|translate) (.+?)( symmetric)?", line)
    if not match:
        return None
    operation, parameters, symmetric = match.groups()
    if operation == "pop":
        return (TagRewrite("ingress", operation, int(parameters), bool(symmetric), parameters)
                if parameters in {"1", "2"} else None)
    tags = parameters
    translation = ""
    count = 0
    if operation == "translate":
        variant = re.fullmatch(r"([12])-to-([12]) (.+)", parameters)
        if not variant:
            return None
        count, output_count = int(variant[1]), int(variant[2])
        translation, tags = parameters.split(" ", 1)
    tag_match = re.fullmatch(r"(dot1q|dot1ad) ([0-9]{1,4})(?: (second-dot1q|dot1q) ([0-9]{1,4}))?", tags)
    if not tag_match:
        return None
    outer, outer_id, inner, inner_id = tag_match.groups()
    if inner and (outer, inner) not in {("dot1q", "second-dot1q"), ("dot1ad", "dot1q")}:
        return None
    output_tags = ((outer, int(outer_id)),) + (((inner, int(inner_id)),) if inner else ())
    if any(not 1 <= value <= 4094 for _, value in output_tags):
        return None
    if operation == "translate" and len(output_tags) != output_count:
        return None
    return TagRewrite("ingress", operation, count or len(output_tags), bool(symmetric),
                      parameters, output_tags, translation)


def _safe_source(text, platform=None):
    # Description/evidence are the only arbitrary source strings retained.
    # Also cover CLI-style secret labels separated by whitespace, not just '='.
    text = sanitize_text(text)
    if any(ord(c) < 32 and c not in "\t\n\r" for c in text) or "\x7f" in text:
        return "[configuration evidence omitted: unsafe control characters]"
    match = _CREDENTIAL.search(text)
    if platform:
        vendor = re.search(rf"(?i)(?<![\w./:-]){_VENDOR_CREDENTIAL[platform]}(?![\w./:-])", text)
        if vendor and (not match or vendor.start() < match.start()):
            match = vendor
    return (text[:match.end()] + " [REDACTED]"
            if match and text[match.end():].lstrip(" \t:=") else text)


# Disclosure policy is independent of forwarding recognition. Credential command
# tokens are matched as tokens, not substrings of innocuous interface/domain IDs.
_CREDENTIAL = re.compile(
    r"(?i)(?<![\w./:-])(?:password|passwd|secret|token|credential[s]?|community|"
    r"key|key-string|key-chain|private-key|private_key|pkey|authentication-key|"
    r"authentication|authorization|auth|otp|username|user-name)(?![\w./-])")
_VENDOR_CREDENTIAL = {
    "cisco_ios": r"(?:isakmp|pre-shared|radius-server|tacacs-server|snmp-server)",
    "cisco_xe": r"(?:isakmp|pre-shared|radius-server|tacacs-server|snmp-server)",
    "cisco_xr": r"(?:keychain|key-string|encrypted|cleartext|snmp-server)",
    "huawei_vrp": r"(?:cipher|irreversible-cipher|simple|local-user|snmp-agent)",
    "ubiquiti_edgeswitch": r"(?:encrypted|radius-server|tacacs-server|snmp-server)",
}


def _review_excerpt(raw, platform):
    """Disclose CLI-shaped forwarding text, never free-form/encoded payloads.

    Called only for relevant forwarding command heads in known containers.
    Unknown words do not imply unknown secrets: identifiers and new modifiers
    are preserved. Credential constructs, quoted expressions, shell/control
    characters and opaque operands fail closed with a source-located marker.
    This is disclosure permission only, never support for forwarding semantics.
    """
    reason = ""
    if _CREDENTIAL.search(raw) or re.search(
            rf"(?i)(?<![\w./:-]){_VENDOR_CREDENTIAL[platform]}(?![\w./:-])", raw):
        reason = "credential-bearing syntax"
    elif not re.fullmatch(r"[\w ./,:\t-]+", raw, flags=re.ASCII):
        reason = "unsafe characters or free-form payload"
    elif "://" in raw or any(
            (len(word) > 256 and not re.fullmatch(r"[\d,-]+", word))
            or re.fullmatch(r"[a-fA-F0-9]{32,}", word)
            or re.fullmatch(r"eyJ[\w-]+\.[\w-]+(?:\.[\w-]+)?", word)
            or (len(word) >= 24 and re.fullmatch(r"[A-Za-z0-9]+", word)
                and re.search(r"[A-Z]", word) and re.search(r"[a-z]", word)
                and re.search(r"[0-9]", word))
            for word in raw.split()):
        reason = "opaque operand"
    if reason:
        return f"[unsupported forwarding statement omitted: {reason}]"
    return raw


def _review_candidate(line, stack):
    # Limit unknown capture to forwarding contexts, never arbitrary global CLI.
    kinds = {item[1][0] for item in stack}
    if not kinds.intersection({"interface", "methodology_interface", "l2_interface", "service_instance", "bridge_domain", "vsi", "methodology_context"}):
        return False
    return bool(re.match(
        r"(?:switchport(?: (?:mode|access|trunk|voice|vlan))?|encapsulation|"
        r"service instance|bridge-domain|member|rewrite|"
        r"port (?:link-type|default|trunk|hybrid)|dot1q|qinq|l2 binding|"
        r"vlan (?:participation|tagging|pvid)|vlan-type)(?:\s|$)", line)) and not line.startswith(
            ("switchport nonegotiate", "switchport port-security", "switchport block", "switchport protected"))


def observe_configuration(output, platform, *, source_filename="running-config"):
    """Preserve known statements with one-based lines and actual source excerpts.

    The optional filename is the caller's inspected saved file, not a fabricated
    backup path. Online collection uses the explicit source label running-config.
    Repeated interface stanzas stay ordered here and are consolidated by audit.
    """
    roots, stack = [], []
    banner_end = None
    for number, raw in enumerate(output.split("\n"), 1):
        raw = raw.removesuffix("\r")  # CRLF, without treating control payloads as new CLI lines.
        original_raw = raw
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
        if platform.startswith("cisco_") and re.fullmatch(rf"pseudowire-class {_NAME}", line):
            entries.append(("methodology_context", "pseudowire_class"))
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
                        try:
                            if kind.startswith("allowed") and platform in {"cisco_ios", "cisco_xe"}:
                                if value not in {"all", "none"} and not re.fullmatch(
                                        r"[0-9]+(?:\s*-\s*[0-9]+)?(?:(?:\s*,\s*|\s+)[0-9]+(?:\s*-\s*[0-9]+)?)*", value):
                                    raise ValueError("invalid allowed list")
                            value = value.upper() if value in {"all", "none"} else parse_vlan_list(value, range_word="to")
                        except ValueError:
                            if platform not in {"cisco_ios", "cisco_xe"} or not kind.startswith("allowed"):
                                raise
                            kind, value = "unsupported_allowed", "invalid_allowed_operation"
                    entries.append((kind, value))
        # Preserve additional relationship syntax for methodology review only.
        # Existing compliance facts and their evidence projection stay unchanged.
        if (platform in {"cisco_ios", "cisco_xe"} and not entries and stack
                and stack[-1][1][0] == "bridge_domain"
                and not any(n[1][0] in {"interface", "l2_interface", "service_instance"} for n in stack)):
            member = re.fullmatch(rf"member ({_NAME} service-instance \d+) split-horizon group [0-9]+", line)
            if member:
                entries.append(("methodology_member", member[1]))
        if platform == "cisco_xr" and any(kind == "attachment" for kind, _ in entries):
            if line.startswith("routed interface "):
                entries.append(("methodology_routed_attachment", entries[0][1]))
        if (platform in {"cisco_ios", "cisco_xe"}
                and re.match(r"switchport trunk allowed vlan(?:\s|$)", line) and not entries):
            # Unknown tails can contain secrets. Retain a safe marker and line
            # reference, never arbitrary unrecognized command text.
            entries.append(("unsupported_allowed", "invalid_allowed_operation"))
            raw = " " * indent + "switchport trunk allowed vlan [unrecognized operation omitted]"
        if not entries and platform == "huawei_vrp":
            review_interface = re.fullmatch(rf"interface\s+({_NAME})", line, re.IGNORECASE)
            review_encapsulation = _VRP_REVIEW_ENCAPSULATION.fullmatch(line)
            if review_interface:
                entries.append(("methodology_interface", review_interface[1]))
            elif review_encapsulation:
                try:
                    tags = parse_vlan_list(review_encapsulation[1])
                except ValueError:
                    pass  # Preserve existing malformed-variant review behavior.
                else:
                    entries.append(("methodology_encapsulation", tags))
        if not entries and line == "switchport" and platform in {"cisco_ios", "cisco_xe", "ubiquiti_edgeswitch"}:
            entries.append(("methodology_switchport_enabled", "enabled"))
        if not entries and platform == "ubiquiti_edgeswitch":
            # Known alternative syntax is review-only, never audit membership.
            for kind, pattern, conversion in _PATTERNS["cisco_ios"]:
                if kind not in {"mode", "access", "allowed", "allowed_add", "allowed_remove",
                                "allowed_except", "native", "trunk_encapsulation"}:
                    continue
                match = pattern.fullmatch(line)
                if not match:
                    continue
                value = match[1]
                if kind == "mode" and value not in {"access", "trunk"}:
                    continue
                if kind == "trunk_encapsulation" and value != "dot1q":
                    continue
                if conversion == "list":
                    try:
                        value = value.upper() if value in {"all", "none"} else parse_vlan_list(value)
                    except ValueError:
                        continue
                entries.append(("methodology_switchport_" + kind, value))
        if not entries and platform in {"cisco_ios", "cisco_xe", "cisco_xr"} and stack:
            rewrite = _tag_rewrite(line)
            if rewrite is not None:
                entries.append(("tag_rewrite", rewrite))
        review_line = " ".join(line.lower().split()) if platform == "huawei_vrp" else line
        # Additional supporting statements have no effect on existing resolution
        # or standards decisions. Retain them as evidence, not validated facts.
        supporting = {
            "cisco_ios": r"split-horizon|xconnect|neighbor|pw-class|pseudowire",
            "cisco_xe": r"split-horizon|xconnect|neighbor|pw-class|pseudowire",
            "cisco_xr": r"split-horizon|neighbor|pw-class|pseudowire|vfi",
            "huawei_vrp": r"vsi-id|pwsignal|peer|static-vc|mpls l2vc",
            "ubiquiti_edgeswitch": r"vlan protocol|vlan association",
        }
        pseudowire_encapsulation = (
            platform.startswith("cisco_") and line == "encapsulation mpls" and stack
            and (stack[-1][1][:2] == ["methodology_context", "pseudowire_class"]
                 or (stack[-1][1][0] in {"interface", "l2_interface"}
                     and re.match(r"(?i)(?:pseudowire|pw-ether|pw-iw)", stack[-1][1][1]))))
        if (not entries and stack and (pseudowire_encapsulation or
                re.match(rf"(?:{supporting[platform]})(?:\s|$)", review_line))):
            entries.append(("methodology_evidence", "supporting_forwarding_source"))
            raw = _review_excerpt(raw, platform)
        if not entries and _review_candidate(review_line, stack):
            # Review-only nodes are stripped before audit resolution.
            entries.append(("methodology_unknown", "unsupported_forwarding_syntax"))
            raw = _review_excerpt(raw, platform)
        for kind, value in entries:
            node = [kind, value, number, _safe_source(raw, platform), []]
            (stack[-1][1][4] if stack else roots).append(node)
            if kind in _CONTAINERS and (platform != "ubiquiti_edgeswitch" or kind in {"interface", "vlan_database"}):
                stack.append((indent, node))
        if raw != original_raw and any(kind == "unsupported_allowed" for kind, _ in entries):
            # Preserve the audit's existing safe marker while exposing the actual
            # safe command in review only. This must not introduce new findings.
            node = ["methodology_evidence", "unsupported_allowed_source", number,
                    _review_excerpt(original_raw, platform), []]
            (stack[-1][1][4] if stack else roots).append(node)

    def freeze(node):
        kind, value, number, excerpt, children = node
        return ConfigFact(kind, _safe_source(value, platform) if isinstance(value, str) else value,
                          sanitize_text(source_filename), number, excerpt,
                          tuple(freeze(child) for child in children))
    return tuple(freeze(node) for node in roots)
