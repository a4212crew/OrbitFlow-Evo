"""Operator standards over review facts only; never compliance or live health.

All comparisons use preserved typed facts. The report merely displays this
projection; audit findings remain intact even when standards assign less severity.
"""

from dataclasses import replace
import re

from orbitflow.compliance.resolvers import children, evidence, last


def vlan_set(value):
    return {v for v in value if type(v) is int} if not isinstance(value, str) else set()


def edge_fields(lines):
    result = {}
    for node in lines:
        if node.kind in {"include", "exclude", "tagged", "untagged_vlans"}:
            field = "participation" if node.kind in {"include", "exclude"} else "tagging"
            current = result.setdefault(field, set())
            if node.kind in {"exclude", "untagged_vlans"}:
                current.difference_update(vlan_set(node.value))
            else:
                current.update(vlan_set(node.value))
        elif node.kind == "pvid":
            result["pvid"] = vlan_set(node.value)
    return {k: sorted(v) for k, v in result.items()}


def switch_fields(lines):
    result = {}
    for node in lines:
        if node.kind in {"mode", "native", "access"}:
            result[node.kind] = node.value if isinstance(node.value, str) else list(node.value)
        elif node.kind == "allowed":
            result["participation"] = node.value if isinstance(node.value, str) else sorted(node.value)
        elif node.kind in {"allowed_add", "allowed_remove", "allowed_except", "unsupported_allowed"}:
            # Without a finite explicit base, defaults/ALL require review.
            current = result.get("participation")
            if isinstance(current, list) and node.kind in {"allowed_add", "allowed_remove"}:
                operand = vlan_set(node.value)
                result["participation"] = sorted(set(current) | operand if node.kind == "allowed_add"
                                                  else set(current) - operand)
            else:
                result.pop("participation", None)
    # Compare forwarding intent, not inactive residual switchport settings.
    if result.get("mode") == "trunk":
        result.pop("access", None)
    elif result.get("mode") == "access":
        result.pop("participation", None)
        result.pop("native", None)
    return result


def lag_relationship(resolver, node, alternates):
    """Confirm membership from explicit references, never names/descriptions."""
    groups = {n.value for n in children(node.children, "aggregate")}
    if len(groups) != 1:
        return None
    group = next(iter(groups))
    edge = resolver.context.device_family == "EdgeSwitch"
    name = ("lag " + group[2:] if group.startswith("3/") else group) if edge else "Port-channel" + group
    if edge and not name.startswith("lag "):
        return None
    owner = resolver.config.get(resolver.key(name))
    if owner is None or resolver.key(owner.value) == resolver.key(node.value):
        return None
    fields = edge_fields if edge else switch_fields
    member_fields, owner_fields = fields(node.children), fields(owner.children)
    extra_proof = ()
    if edge and not member_fields and not owner_fields:
        member_alternate = alternates.get(resolver.key(node.value), ())
        owner_alternate = alternates.get(resolver.key(owner.value), ())
        member_fields, owner_fields = switch_fields(member_alternate), switch_fields(owner_alternate)
        extra_proof = (*member_alternate, *owner_alternate)
    # A completely unconfigured member inherits the aggregate in the supported
    # audit model. Partial member configuration does not establish per-field
    # inheritance, nor does an omitted command establish a default/empty value.
    forwarding_kinds = {"mode", "native", "access", "allowed", "allowed_add",
                        "allowed_remove", "allowed_except", "unsupported_allowed",
                        "include", "exclude", "tagged", "untagged_vlans", "pvid"}
    inherited = bool(owner_fields) and not member_fields and not any(
        n.kind in forwarding_kinds for n in (*node.children, *alternates.get(resolver.key(node.value), ())))
    diffs, unresolved = {}, {}
    for field in sorted(member_fields.keys() | owner_fields.keys()):
        if inherited:
            continue
        comparison = dict(member=member_fields.get(field), aggregate=owner_fields.get(field))
        if field not in member_fields or field not in owner_fields:
            missing = "member" if field not in member_fields else "aggregate"
            unresolved[field] = dict(**comparison, explanation=(
                f"The {missing} stanza omits {field}; its effective value is unknown. "
                "Partial configuration does not establish inheritance or a default."))
        elif member_fields[field] != owner_fields[field]:
            diffs[field] = comparison
    if not member_fields and not owner_fields:
        unresolved["configuration"] = dict(member=None, aggregate=None, explanation=(
            "Neither stanza establishes supported VLAN forwarding values; membership alone "
            "does not establish their effective configuration."))
    return dict(member=node.value, aggregate=owner.value, differences=diffs,
                unresolved_fields=unresolved, inherited_from=owner.value if inherited else "",
                member_configuration=member_fields, aggregate_configuration=owner_fields,
                evidence=evidence((node, owner, *extra_proof)))


def evc_standard(node, mappings):
    lines = node.children
    prerequisites = ({n.value for n in children(lines, "mode")} == {"trunk"}
                     and bool(children(lines, "allowed"))
                     and all(n.value == "NONE" for n in children(lines, "allowed"))
                     and not any(n.kind in {"access", "routed", "allowed_add", "allowed_remove",
                                            "allowed_except", "unsupported_allowed", "native"} for n in lines))
    if not prerequisites:
        return "ME3600X_EVC_PREREQUISITES_MISSING"
    seen = []
    for mapping in mappings:
        if mapping["binding_status"] != "valid" or mapping["encapsulation_type"] == "unknown":
            return "ME3600X_EVC_SERVICE_UNRESOLVED"
        outer, inner = set(mapping["outer_vlan"]), set(mapping["inner_vlan"])
        untagged = mapping["encapsulation_type"] == "untagged"
        for previous_outer, previous_inner, previous_untagged in seen:
            if (untagged and previous_untagged) or (
                    outer & previous_outer and (not inner or not previous_inner or inner & previous_inner)):
                return "ME3600X_EVC_SERVICE_OVERLAP"
        seen.append((outer, inner, untagged))
    return "ME3600X_STANDARD_EVC_TRUNK"


def classify_records(resolver, records):
    family = resolver.context.device_family
    evc_codes, relationships = {}, {}
    alternates = {}
    xr_bindings = {}
    for root in children(resolver.review_roots, "l2vpn"):
        for group in children(root.children, "bridge_group"):
            for domain in children(group.children, "bridge_domain"):
                routed = {(n.source_filename, n.line) for n in
                          children(domain.children, "methodology_routed_attachment")}
                for attachment in children(domain.children, "attachment"):
                    xr_bindings.setdefault(resolver.key(attachment.value), []).append(
                        ((group.value, domain.value),
                         (attachment.source_filename, attachment.line) in routed))
    for root in resolver.review_roots:
        if root.kind == "interface":
            alternates.setdefault(resolver.key(root.value), []).extend(
                replace(n, kind=n.kind.removeprefix("methodology_switchport_"))
                for n in root.children if n.kind.startswith("methodology_switchport_"))
    for record in records:
        key = resolver.key(record.get("config_interface_name", ""))
        node = resolver.config.get(key)
        lines = node.children if node else ()
        findings = []

        def finding(code, classification, severity, proof=(), **details):
            findings.append(dict(code=code, configuration_classification=classification,
                                 severity=severity, evidence=list(proof), **details))

        ignored = set()
        if record["subtype"] == "pseudowire_attachment":
            # Real configured interface identity is retained. PW forwarding and
            # attachment validation are outside M01-M08, not missing L2 intent.
            ignored.update({"NON_L2TRANSPORT_BRIDGE_DOMAIN_ATTACHMENT", "UNBOUND_L2TRANSPORT_SUBINTERFACE",
                            "CONFLICTING_BRIDGE_DOMAIN_ATTACHMENTS", "L2TRANSPORT_WITHOUT_ENCAPSULATION",
                            "UNTAGGED_BRIDGE_DOMAIN_MAPPING_UNRESOLVED", "PARENT_INTERFACE_NOT_FOUND"})
            finding("PSEUDOWIRE_SERVICE_CONTEXT", "not_applicable", "none", record["evidence"])
        if family == "NCS540" and node and record["subtype"] != "pseudowire_attachment":
            bindings = xr_bindings.get(key, [])
            single = len({domain for domain, _ in bindings}) == 1
            if (single and all(routed for _, routed in bindings)
                    and re.fullmatch(r"BVI\d+", node.value, re.IGNORECASE)
                    and node.kind == "interface"):
                ignored.add("NON_L2TRANSPORT_BRIDGE_DOMAIN_ATTACHMENT")
                finding("VALID_ROUTED_BVI_ATTACHMENT", "standard_configuration", "none", record["evidence"])
            if (single and all(not routed for _, routed in bindings) and node.kind == "l2_interface"
                    and children(lines, "untagged") and not children(lines, "encapsulation")):
                ignored.add("UNTAGGED_BRIDGE_DOMAIN_MAPPING_UNRESOLVED")
                finding("VALID_UNTAGGED_BRIDGE_DOMAIN_ATTACHMENT", "standard_configuration", "none", record["evidence"])
            if bindings and any(routed for _, routed in bindings) and not (
                    re.fullmatch(r"BVI\d+", node.value, re.IGNORECASE) and node.kind == "interface"
                    and all(routed for _, routed in bindings)):
                finding("INVALID_ROUTED_BRIDGE_DOMAIN_ATTACHMENT", "review_needed", "warning", record["evidence"])
        if record["subtype"].startswith("evc_"):
            mapping = record["mapping"]
            if mapping["binding_status"] == "valid" and not all(
                    v.isdecimal() for v in mapping["resolved_bridge_domain"]):
                finding("INVALID_EVC_BRIDGE_DOMAIN", "review_needed", "warning", record["evidence"])
        if family == "EdgeSwitch" and node:
            excluded = set()
            for fact in lines:
                if fact.kind == "exclude":
                    excluded.update(vlan_set(fact.value))
                elif fact.kind == "include":
                    excluded.difference_update(vlan_set(fact.value))
            for problem in record.get("configuration_findings", []):
                if (problem["code"] == "TAGGED_VLAN_NOT_IN_MEMBERSHIP"
                        and set(problem.get("vlans", ())) <= excluded):
                    ignored.add(problem["code"])
                    finding("EXCLUDED_VLAN_TAGGING_INACTIVE", "standard_configuration", "informational",
                            problem["evidence"], vlans=problem["vlans"])
            alternate = record.get("mapping", {}).get("configured_switchport", [])
            if alternate:
                modes = {n["value"] for n in alternate if n["kind"] == "methodology_switchport_mode"}
                native_modes = {n.value for n in children(lines, "mode")}
                native_vlan = any(n.kind in {"include", "exclude", "tagged", "pvid", "untagged_vlans"} for n in lines)
                complete = modes in ({"access"}, {"trunk"}) and not native_modes and not native_vlan
                finding("EDGESWITCH_SWITCHPORT_STYLE" if complete else "EDGESWITCH_MIXED_OR_INCOMPLETE_SWITCHPORT",
                        "working_non_standard" if complete else "review_needed",
                        "warning", record["evidence"])

        if family in {"C3750X", "C3850", "ME3600X"} and node:
            modes = {n.value for n in children(lines, "mode")}
            mode = last(lines, "mode")
            residual = ((mode == "trunk" and children(lines, "access")) or
                        (mode == "access" and any(n.kind in {"allowed", "allowed_add", "allowed_remove",
                                                             "allowed_except", "native"} for n in lines)))
            if residual and len(modes) == 1 and not children(lines, "routed") and not children(lines, "service_instance"):
                ignored.add("CONFLICTING_SWITCHPORT_INTENT")
                finding("RESIDUAL_SWITCHPORT_SETTINGS", "working_non_standard", "warning", evidence((node,)))
            if len(modes) > 1 or (modes and children(lines, "routed")):
                finding("AMBIGUOUS_SWITCHPORT_INTENT", "review_needed", "warning", evidence((node,)))
            if children(lines, "unsupported_allowed"):
                finding("UNSUPPORTED_ALLOWED_VLAN_OPERATION", "review_needed", "warning",
                        evidence(children(lines, "unsupported_allowed")))
            if family == "ME3600X" and children(lines, "service_instance"):
                if key not in evc_codes:
                    evc_codes[key] = evc_standard(node, resolver.rows[key]["numeric_mappings"])
                code = evc_codes[key]
                # Every service record carries the prerequisite context too.
                record["evidence"] += evidence(tuple(n for n in lines if n.kind in {"mode", "allowed"}))
                finding(code, "standard_configuration" if code == "ME3600X_STANDARD_EVC_TRUNK" else "review_needed",
                        "none" if code == "ME3600X_STANDARD_EVC_TRUNK" else "warning",
                        evidence((node,)) if code == "ME3600X_EVC_SERVICE_OVERLAP" else record["evidence"])

        if key not in relationships:
            relationships[key] = lag_relationship(resolver, node, alternates) if node else None
        relationship = relationships[key]
        if node and children(lines, "aggregate") and relationship is None:
            finding("LAG_RELATIONSHIP_UNRESOLVED", "review_needed", "warning", evidence((node,)))
        if relationship:
            record.setdefault("mapping", {})["lag_relationship"] = relationship
            if relationship["differences"]:
                finding("LAG_MEMBER_CONFIGURATION_MISMATCH", "wrong_configuration", "error",
                        relationship["evidence"], relationship=relationship)
                ignored.update({"AGGREGATE_CONFIG_CONFLICT", "PORT_CHANNEL_CONFIG_CONFLICT"})
            if relationship["unresolved_fields"]:
                finding("LAG_MEMBER_CONFIGURATION_UNRESOLVED", "review_needed", "warning",
                        relationship["evidence"], relationship=relationship)

        for problem in record.get("configuration_findings", []):
            code = problem["code"]
            if code in ignored:
                continue
            if code == "ALLOWED_VLAN_NOT_IN_DATABASE":
                finding(code, "standard_configuration", "informational", problem.get("evidence", ()),
                        vlans=problem.get("vlans", []))
            else:
                finding(code, "review_needed", "warning", problem.get("evidence", ()))

        if not findings:
            if record["subtype"] == "no_l2_service" or record["status"] == "out_of_scope":
                finding("NO_RELEVANT_L2_SERVICE", "not_applicable", "none")
            elif record["status"] == "resolved":
                finding("STANDARD_METHODOLOGY", "standard_configuration", "none")
            else:
                finding("UNRESOLVED_METHODOLOGY", "review_needed", "warning")
        ranking = {"wrong_configuration": 4, "review_needed": 3, "working_non_standard": 2,
                   "standard_configuration": 1, "not_applicable": 0}
        severity = {"none": 0, "informational": 1, "warning": 2, "error": 3, "critical": 4}
        primary = max(findings, key=lambda f: (ranking[f["configuration_classification"]], severity[f["severity"]]))
        record.update(configuration_classification=primary["configuration_classification"],
                      finding_severity=primary["severity"], standard_finding=primary["code"],
                      standard_findings=findings, engineering_review_decision="not_reviewed")
        review = any(f["configuration_classification"] in {"review_needed", "wrong_configuration"} for f in findings)
        record["review_needed"] = review
        if not review:
            record["status"] = "not_applicable" if primary["configuration_classification"] == "not_applicable" else "resolved"
        elif record["status"] in {"resolved", "not_applicable"}:
            record["status"] = "review_needed"
