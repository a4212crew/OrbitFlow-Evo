"""Syntax-preserving VLAN evidence shared by the existing observation adapters.

Recognized VLAN/interface statements and bounded sanitized forwarding exceptions
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
               "bridge_domain", "vsi", "vlan_database", "vlan", "methodology_interface"}
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


def _safe_source(text):
    # Description/evidence are the only arbitrary source strings retained.
    # Also cover CLI-style secret labels separated by whitespace, not just '='.
    return re.sub(r"(?i)\b(password|passwd|secret|token|otp|private_key|authorization)\b[\s:=]+.*",
                  r"\1 [REDACTED]", sanitize_text(text))


# Disclosure vocabulary only: these words do not establish supported semantics.
# Unknown operands may be arbitrary secrets, even without credential labels.
_REVIEW_WORDS = frozenset("""switchport encapsulation dot1q second-dot1q untagged
 default priority-tagged exact any all none vlan vlans bridge-domain member
 service instance ethernet rewrite ingress tag pop push translate symmetric
 split-horizon group port link-type trunk hybrid access allow-pass tagged
 qinq termination vid pe-vid ce-vid l2 binding vsi vlan-type participation
 tagging pvid include exclude enable disable allowed add remove except
 native tunnel protocol ieee dot1ad egress 1-to-1 1-to-2 2-to-1 2-to-2""".split())
_REVIEW_OMITTED = "[unsupported forwarding statement omitted: unsafe or oversized evidence]"


def _review_excerpt(raw):
    """Bounded, fail-closed disclosure; never retain unknown free-form values."""
    if len(raw) > 512 or any(ord(c) < 32 and c != "\t" for c in raw):
        return _REVIEW_OMITTED
    words = raw.split()
    if len(words) > 64:
        return _REVIEW_OMITTED
    if re.search(r"(?i)password|passwd|secret|token|credential|community|key|auth|otp", raw):
        return _REVIEW_OMITTED
    def disclose(match):
        value = match[0]
        return value if value in _REVIEW_WORDS or re.fullmatch(r"[0-9]{1,4}(?:[,-][0-9]{1,4})*", value) else "[REDACTED]"
    return re.sub(r"\S+", disclose, raw)


def _review_candidate(line, stack):
    # Limit unknown capture to forwarding contexts, never arbitrary global CLI.
    kinds = {item[1][0] for item in stack}
    if not kinds.intersection({"interface", "methodology_interface", "l2_interface", "service_instance", "bridge_domain", "vsi"}):
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
    review_count = 0
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
        if not entries and platform in {"cisco_ios", "cisco_xe", "cisco_xr"} and stack:
            rewrite = _tag_rewrite(line)
            if rewrite is not None:
                entries.append(("tag_rewrite", rewrite))
        review_line = " ".join(line.lower().split()) if platform == "huawei_vrp" else line
        if not entries and _review_candidate(review_line, stack):
            # Review-only nodes are stripped before audit resolution.
            review_count += 1
            if review_count <= 256:
                entries.append(("methodology_unknown", "unsupported_forwarding_syntax"))
                raw = _review_excerpt(raw)
            elif review_count == 257:
                entries.append(("methodology_unknown", "review_evidence_limit"))
                raw = "[further unsupported forwarding evidence omitted: storage limit]"
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
