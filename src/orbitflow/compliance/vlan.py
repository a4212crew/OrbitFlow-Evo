"""Common policy engine over family-validated saved-configuration audit facts."""

import re

from orbitflow.logging import sanitize_text
from orbitflow.vendors.interface_names import canonical_interface_name
from orbitflow.compliance.resolvers import resolver_for


def safe_data(value, clean=sanitize_text):
    """Project JSON-ready output through a scalar sanitizer (never stringify models)."""
    if isinstance(value, dict):
        return {key: safe_data(item, clean) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [safe_data(item, clean) for item in value]
    return clean(value) if isinstance(value, str) else value


def _summary(value):
    """Bound presentation only; exact comparison values remain in observed facts."""
    if isinstance(value, (list, tuple, set)):
        if all(isinstance(v, int) and not isinstance(v, bool) for v in value):
            ranges = []
            for v in sorted(set(value)):
                if ranges and v == ranges[-1][1] + 1:
                    ranges[-1][1] = v
                else:
                    ranges.append([v, v])
            text = ",".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges[:8])
            return f"{len(value)} VLANs ({text}{', ...' if len(ranges) > 8 else ''})"
        return f"{len(value)} values (see structured Details)"
    if isinstance(value, dict):
        return "structured values (see Details)"
    text = str(value)
    return text if len(text) <= 100 else text[:100] + "... (see Details)"


def evaluate_vlan_compliance(context, interfaces, vlans, policy, *, management_ip="",
                             clean=sanitize_text):
    """Evaluate both rule families from one snapshot; no collection or mutation.

    Configuration problems are independent structured findings within each
    database/interface result. Confirmed physical aggregate children retain rows
    and health but skip required-VLAN policy; ME3600X pseudowire rows are excluded
    from this projection only. EdgeSwitch logical LAG display uses the actual
    saved heading while observed identity/state remain independently available.
    Child summaries bound VLAN ranges/counts and comparison values; exact details
    and source excerpts remain in observed findings/evidence for spool export.
    Missing evidence never becomes a fabricated fact.
    """
    device = dict(device_id=context.device_id if context else "",
                  management_ip=context.management_ip if context else management_ip,
                  hostname=context.hostname if context else "", platform=context.platform if context else "",
                  family=context.device_family if context else "")
    database_expected = dict(required_vlans=sorted(map(int, policy.required_domains)))
    interface_expected = dict(interface_types=["trunk", "evc", "hybrid"], match_all=policy.match_all,
                              match_any=policy.match_any, required_vlans=policy.required_vlans)
    findings = []

    def emit(rule, expected, observed, status, reason, *, interface=None, missing=(), source=(), recommendation=""):
        # Identity correlation is informational, not a configuration defect.
        problems = (observed or {}).get("configuration_findings", ())
        health = ("unable_to_assess" if observed is None else
                  "wrong_configuration" if any(p["code"] not in {"CONFIG_ONLY_INTERFACE", "INTERFACE_NOT_IN_CONFIG", "EXCLUDED_VLAN_TAGGING_INACTIVE"}
                                               for p in problems) else "healthy")
        findings.append(dict(policy_id=policy.policy_id, rule_id=rule, device=device,
                             interface=interface, expected=expected, observed=observed,
                             missing_vlans=list(missing),
                             missing_objects=[str(v) for v in missing] if rule == policy.database_rule else [],
                             status=status, configuration_health=health,
                             reason=reason, explanation=reason.replace("_", " "),
                             recommendation=recommendation, evidence=dict(sources=list(source))))

    resolver = resolver_for(context) if context else None
    unavailable = ("vlan_collection_unavailable" if vlans is None or context is None else
                   "unsupported_or_uncertain_family" if resolver is None else
                   "saved_configuration_evidence_unavailable" if vlans.configuration is None else "")
    if unavailable:
        for rule, expected in ((policy.database_rule, database_expected), (policy.interface_rule, interface_expected)):
            emit(rule, expected, None, "unable_to_assess", unavailable)
        return safe_data(findings, clean)

    facts = resolver(context, vlans).result()
    rows = facts.pop("interfaces")
    source = facts.pop("evidence")
    missing = sorted(set(map(int, policy.required_domains)) - set(facts["valid_database_vlans"]))
    facts["compliance_findings"] = ([dict(code="DATABASE_REQUIRED_VLAN_MISSING", vlans=missing)] if missing else [])
    emit(policy.database_rule, database_expected, facts, "non_compliant" if missing else "compliant",
         "missing_database_vlans" if missing else "required_database_vlans_present", missing=missing,
         source=source, recommendation="Provide the missing global VLANs or valid family-specific service mappings." if missing else "")

    key = lambda name: canonical_interface_name(context.platform, name, normalize_aggregation=True)
    actual = {key(record.port_name): record for record in interfaces or ()}

    def interface_state(record):
        return dict(admin_status=record.admin_status if record else "not observed",
                    oper_status=record.oper_status if record else "not observed")

    for name, row in sorted(rows.items()):
        if context.device_family == "ME3600X" and re.fullmatch(r"(?i)(?:pseudowire|pw-ether|pw-iw)\d+(?:\.\d+)?", row["config_interface_name"]):
            continue
        if "consolidated_into" in row:
            # Retain identity matching for child details as well as parent rows.
            target = rows[row["consolidated_into"]]
            for child in target["child_interfaces"]:
                if child["interface_name"] == row["config_interface_name"]:
                    child.update(config_interface_name=row["config_interface_name"],
                                 interface_name=actual[name].port_name if name in actual else "not observed",
                                 interface_match_status="matched" if name in actual else "config_only",
                                 **interface_state(actual.get(name)))
            continue
        record = actual.get(name)
        config_only = record is None
        match = "config_only" if config_only else "matched"
        row.update(interface_name=record.port_name if record else "not observed", interface_match_status=match,
                   interface_collection_available=interfaces is not None, **interface_state(record))
        if match == "config_only":
            row["configuration_findings"].append(dict(code="CONFIG_ONLY_INTERFACE", evidence=[]))
        tags = set(row["valid_interface_vlans"])
        trigger = set(policy.match_all) <= tags and bool(set(policy.match_any) & tags)
        row["trigger_applicable"] = trigger and (row["interface_type"] in {"trunk", "evc", "hybrid"}
                                                   or row.get("audit_valid_tagged_subset", False))
        missing = []
        if row.get("aggregation_child"):
            row["interface_type"] = "Child Port-Channel"
            row["trigger_applicable"] = False
            status, reason = "not_applicable", "physical_member_required_vlan_evaluation_owned_by_" + row["configuration_owner"]
        elif row["review"]:
            status, reason = "unable_to_assess", "ambiguous_or_unavailable_interface_facts"
        elif row.get("no_vlan_service_configuration"):
            status, reason = "not_applicable", "no_vlan_service_configuration"
        elif not row["trigger_applicable"]:
            status, reason = "not_applicable", "access_excluded" if row["interface_type"] == "access" else "signature_not_matched"
        else:
            missing = sorted(set(policy.required_vlans) - tags)
            status, reason = ("non_compliant", "missing_interface_vlans") if missing else ("compliant", "required_interface_vlans_present")
        row["compliance_findings"] = ([dict(code="INTERFACE_REQUIRED_VLAN_MISSING", vlans=missing)] if missing else [])
        recommendation = ""
        if missing:
            recommendation = ("Add missing global VLANs; this All VLAN trunk uses the device database."
                              if row.get("all_vlan") else "Review missing VLAN membership on " + row["configuration_owner"] + ".")
        elif row["configuration_findings"]:
            recommendation = "Review the reported configuration relationships and identity evidence."
        if (not missing and not any(p["code"] not in {"CONFIG_ONLY_INTERFACE", "INTERFACE_NOT_IN_CONFIG", "EXCLUDED_VLAN_TAGGING_INACTIVE"}
                                   for p in row["configuration_findings"])
                and any(p["code"] == "EXCLUDED_VLAN_TAGGING_INACTIVE" for p in row["configuration_findings"])):
            reason += ". Explicitly excluded VLAN tagging is inactive and does not establish forwarding membership"
            recommendation = "Retain participation controls; review residual tagging only if forwarding intent changes."
        actionable = [p for p in row["configuration_findings"] if p["code"] not in
                      {"CONFIG_ONLY_INTERFACE", "INTERFACE_NOT_IN_CONFIG", "EXCLUDED_VLAN_TAGGING_INACTIVE"}]
        if row.get("aggregation_child") and actionable:
            details = []
            for problem in actionable:
                detail = problem["code"]
                if problem.get("differences"):
                    detail += ": " + "; ".join(
                        f"{field}: member {_summary(values.get('member'))}, parent {_summary(values.get('aggregate'))}"
                        for field, values in sorted(problem["differences"].items()))
                if problem.get("fields"):
                    detail += ": further evidence needed for " + ", ".join(problem["fields"])
                if problem.get("vlans"):
                    detail += ": " + _summary(problem["vlans"])
                details.append(detail)
            reason += ". Independent configuration findings: " + "; ".join(details)
            recommendations = []
            for problem in actionable:
                code = problem["code"]
                if code in {"AGGREGATE_CONFIG_CONFLICT", "PORT_CHANNEL_CONFIG_CONFLICT"}:
                    recommendations.append("Compare the cited explicit member controls with " + row["configuration_owner"]
                                           + "; resolve the reported field mismatch using source evidence.")
                elif code in {"ALLOWED_VLAN_NOT_IN_DATABASE", "INTERFACE_VLAN_NOT_IN_DATABASE"}:
                    recommendations.append("Verify the child's explicit VLAN commands against the global VLAN database; "
                                           "correct the independently configured invalid VLANs.")
                else:
                    recommendations.append("Collect further evidence for " + code
                                           + " and validate the cited commands/bindings before remediation.")
            recommendation = " ".join(dict.fromkeys(recommendations))
            if context.device_family == "ME3600X":
                recommendation += " Keep parent-owned EVC services on the parent."
        display = record.port_name if record else row["config_interface_name"]
        if (context.platform == "ubiquiti_edgeswitch"
                and re.fullmatch(r"(?i)lag\s+\d+", row["config_interface_name"])):
            display = row["config_interface_name"]
        emit(policy.interface_rule, interface_expected, row, status, reason,
             interface=display, missing=missing,
             source=row.pop("evidence"), recommendation=recommendation)
        if row.get("aggregation_child"):
            findings[-1]["explanation"] = ("Required-VLAN evaluation owned by " + row["configuration_owner"]
                + "; physical member skipped." + (" Independent configuration findings: " + "; ".join(details) if actionable else ""))
            if any(p["code"] == "EXCLUDED_VLAN_TAGGING_INACTIVE" for p in row["configuration_findings"]):
                findings[-1]["explanation"] += " Explicitly excluded VLAN tagging is inactive and does not establish forwarding membership."
    if not rows:
        emit(policy.interface_rule, interface_expected, {"interface_count": 0}, "not_applicable", "no_configured_or_observed_interfaces")
    return safe_data(findings, clean)
