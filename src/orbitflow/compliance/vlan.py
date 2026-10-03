"""Pure VLAN compliance rules. Only normalized capability fields are authoritative."""

from orbitflow.logging import sanitize_text
from orbitflow.vendors.interface_names import canonical_interface_name


def safe_data(value, clean=sanitize_text):
    """Project JSON-ready output through a scalar sanitizer (never stringify models)."""
    if isinstance(value, dict):
        return {key: safe_data(item, clean) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [safe_data(item, clean) for item in value]
    return clean(value) if isinstance(value, str) else value


def evaluate_vlan_compliance(context, interfaces, vlans, policy, *, management_ip="",
                             clean=sanitize_text):
    """Return findings; None means collection unavailable, an empty collection is valid.

    Domain requirements match exact domain_id on any policy-accepted object type.
    Trunk membership uses tagged_vlans only, never legacy/raw service fields.
    Unknown membership cannot establish that a trunk is out of scope.
    """
    device = {"device_id": context.device_id if context else "",
              "management_ip": context.management_ip if context else management_ip,
              "hostname": context.hostname if context else "",
              "platform": context.platform if context else ""}
    if context is not None and context.platform == "cisco_xr":
        from orbitflow.compliance.services import evaluate_services
        service_policy = next((rule for rule in policy.service_rules
                               if rule.platform == context.platform), None)
        return safe_data(evaluate_services(device, interfaces, vlans, policy.policy_id,
                                           service_policy), clean)
    database_expected = {"object_types": policy.object_types,
                         "required_domains": policy.required_domains}
    interface_expected = {"port_type": "trunk", "match_all": policy.match_all,
                          "match_any": policy.match_any, "required_vlans": policy.required_vlans}
    findings = []

    def finding(rule, expected, observed, *, interface=None, status, reason,
                missing_vlans=(), missing_objects=(), evidence=None):
        findings.append(dict(policy_id=policy.policy_id, rule_id=rule, device=device,
                             interface=interface, expected=expected, observed=observed,
                             missing_vlans=missing_vlans, missing_objects=missing_objects,
                             status=status, reason=reason, evidence=evidence or {}))

    if context is None or vlans is None:
        finding(policy.database_rule, database_expected, None,
                status="unable_to_assess", reason="vlan_collection_unavailable")
    else:
        objects = sorted(({"object_type": obj.object_type, "object_id": obj.object_id,
                           "domain_id": obj.domain_id} for obj in vlans.objects),
                         key=lambda obj: (obj["object_type"], obj["object_id"], obj["domain_id"]))
        domains = {obj["domain_id"] for obj in objects if obj["object_type"] in policy.object_types}
        missing = sorted(set(policy.required_domains) - domains)
        finding(policy.database_rule, database_expected, {"objects": objects},
                status="non_compliant" if missing else "compliant",
                reason="missing_objects" if missing else "required_objects_present",
                missing_objects=missing, evidence={"collection_time": vlans.collection_time.isoformat()})

    if context is None or interfaces is None:
        finding(policy.interface_rule, interface_expected, None,
                status="unable_to_assess", reason="interface_collection_unavailable")
    else:
        key = lambda name: canonical_interface_name(context.platform, name)
        profiles = {}
        for item in vlans.interfaces if vlans is not None else ():
            profiles.setdefault(key(item.interface_name), []).append(item)
        actual = {key(record.port_name): record for record in interfaces}
        if not actual:
            finding(policy.interface_rule, interface_expected, {"interface_count": 0},
                    status="not_applicable", reason="no_actual_interfaces")
        for name, record in sorted(actual.items()):
            matches = profiles.get(name, [])
            item = matches[0] if len(matches) == 1 else None
            observed = None if item is None else {"port_type": item.port_type,
                                                  "tagged_vlans": item.tagged_vlans}
            missing = []
            if item is None or item.port_type not in {"trunk", "access", "hybrid", "evc", "service", "routed"}:
                status, reason = "unable_to_assess", "forwarding_profile_unavailable_or_ambiguous"
            elif item.port_type != "trunk":
                status, reason = "not_applicable", "not_a_trunk"
            elif item.tagged_vlans == "ALL":
                status, reason = "compliant", "all_tagged_vlans_accepted"
            elif item.tagged_vlans == "NONE":
                status, reason = "not_applicable", "signature_not_matched"
            elif (not isinstance(item.tagged_vlans, tuple) or not item.tagged_vlans
                  or any(type(v) is not int or not 1 <= v <= 4094 for v in item.tagged_vlans)):
                status, reason = "unable_to_assess", "tagged_membership_unavailable"
            else:
                tags = set(item.tagged_vlans)
                if not set(policy.match_all) <= tags or not set(policy.match_any) & tags:
                    status, reason = "not_applicable", "signature_not_matched"
                else:
                    missing = sorted(set(policy.required_vlans) - tags)
                    status = "non_compliant" if missing else "compliant"
                    reason = "missing_vlans" if missing else "required_vlans_present"
            finding(policy.interface_rule, interface_expected, observed,
                    interface=record.port_name, status=status, reason=reason,
                    missing_vlans=missing, evidence={"interface_collection_time": record.collection_time.isoformat(),
                    "vlan_collection_time": vlans.collection_time.isoformat() if vlans else None})
    return safe_data(findings, clean)
