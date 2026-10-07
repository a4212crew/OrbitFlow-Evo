"""Common policy engine over family-validated saved-configuration audit facts."""

from orbitflow.logging import sanitize_text
from orbitflow.vendors.interface_names import canonical_interface_name
from orbitflow.compliance.resolvers import resolver_for, parent_name


def safe_data(value, clean=sanitize_text):
    """Project JSON-ready output through a scalar sanitizer (never stringify models)."""
    if isinstance(value, dict):
        return {key: safe_data(item, clean) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [safe_data(item, clean) for item in value]
    return clean(value) if isinstance(value, str) else value


def evaluate_vlan_compliance(context, interfaces, vlans, policy, *, management_ip="",
                             clean=sanitize_text):
    """Evaluate both rule families from one snapshot; no collection or mutation.

    Configuration problems are independent structured findings within each
    database/interface result. Missing evidence never becomes a fabricated fact.
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
        findings.append(dict(policy_id=policy.policy_id, rule_id=rule, device=device,
                             interface=interface, expected=expected, observed=observed,
                             missing_vlans=list(missing),
                             missing_objects=[str(v) for v in missing] if rule == policy.database_rule else [],
                             status=status, reason=reason, explanation=reason.replace("_", " "),
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

    key = lambda name: canonical_interface_name(context.platform, name)
    actual = {key(record.port_name): record for record in interfaces or ()}
    # Observed-only children may be shown as parent details, but never gain
    # forwarding facts or create a parent/interface from a service reference.
    for name, record in actual.items():
        if name in rows:
            continue
        parent = parent_name(name)
        problem = dict(code="INTERFACE_NOT_IN_CONFIG", interface_name=record.port_name, evidence=[])
        if parent in rows:
            rows[parent]["configuration_findings"].append(problem)
            rows[parent]["child_interfaces"].append(dict(interface_name=record.port_name,
                config_interface_name="not in config file", interface_match_status="not_in_config"))
            continue
        rows[name] = dict(config_interface_name="not in config file", interface_type="review",
                          description=record.port_description, shutdown=record.admin_status.lower() in {"down", "shutdown"},
                          valid_interface_vlans=[], configuration_findings=[problem], evidence=[], review=True,
                          child_interfaces=[], numeric_mappings=[], configuration_owner="")
    for name, row in sorted(rows.items()):
        if "consolidated_into" in row:
            # Retain identity matching for child details as well as parent rows.
            target = rows[row["consolidated_into"]]
            for child in target["child_interfaces"]:
                if child["interface_name"] == row["config_interface_name"]:
                    child.update(config_interface_name=row["config_interface_name"],
                                 interface_name=actual[name].port_name if name in actual else "not observed",
                                 interface_match_status="matched" if name in actual else "config_only")
            continue
        record = actual.get(name)
        config_only = record is None
        match = "not_in_config" if row["config_interface_name"] == "not in config file" else "config_only" if config_only else "matched"
        row.update(interface_name=record.port_name if record else "not observed", interface_match_status=match,
                   interface_collection_available=interfaces is not None)
        if match == "config_only":
            row["configuration_findings"].append(dict(code="CONFIG_ONLY_INTERFACE", evidence=[]))
        tags = set(row["valid_interface_vlans"])
        trigger = set(policy.match_all) <= tags and bool(set(policy.match_any) & tags)
        row["trigger_applicable"] = trigger and (row["interface_type"] in {"trunk", "evc", "hybrid"}
                                                   or row.get("audit_valid_tagged_subset", False))
        missing = []
        if row["review"]:
            status, reason = "unable_to_assess", "ambiguous_or_unavailable_interface_facts"
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
        emit(policy.interface_rule, interface_expected, row, status, reason,
             interface=record.port_name if record else row["config_interface_name"], missing=missing,
             source=row.pop("evidence"), recommendation=recommendation)
    if not rows:
        emit(policy.interface_rule, interface_expected, {"interface_count": 0}, "not_applicable", "no_configured_or_observed_interfaces")
    return safe_data(findings, clean)
