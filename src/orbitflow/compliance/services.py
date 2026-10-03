"""Read-only parent service analysis over normalized capability identities."""

from dataclasses import asdict

from orbitflow.vendors.interface_names import canonical_interface_name


def evaluate_services(device, interfaces, vlans, policy_id, policy):
    findings = []

    def emit(rule, status, reason, *, interface=None, observed=None, missing=(), evidence=None):
        findings.append(dict(policy_id=policy_id, rule_id=rule, device=device,
                             interface=interface, expected=asdict(policy) if policy else {},
                             observed=observed, missing_objects=missing, missing_vlans=(),
                             status=status, reason=reason, evidence=evidence or {}))

    if policy is None:
        for rule in ("service-database", "service-parent"):
            emit(rule, "unable_to_assess", "service_policy_unavailable")
        return findings

    def matches(group, objects):
        return any(getattr(obj, selector.field) == selector.value
                   for obj in objects for selector in group)

    def assess(objects):
        missing = [[asdict(selector) for selector in group]
                   for group in policy.required if not matches(group, objects)]
        if missing:
            return "non_compliant", "missing_services", missing
        if not policy.baseline_complete:
            return "unable_to_assess", "service_baseline_incomplete", []
        return "compliant", "required_services_present", []

    objects = tuple(obj for obj in vlans.objects if obj.object_type == "bridge_domain") if vlans else ()

    def projection(items):
        return sorted(({"object_type": obj.object_type, "object_id": obj.object_id,
                        "domain_id": obj.domain_id} for obj in items),
                      key=lambda obj: (obj["object_id"], obj["domain_id"]))

    if vlans is None:
        emit(policy.database_rule, "unable_to_assess", "vlan_collection_unavailable")
    else:
        status, reason, missing = assess(objects)
        emit(policy.database_rule, status, reason, observed={"objects": projection(objects)},
             missing=missing, evidence={"collection_time": vlans.collection_time.isoformat()})

    if interfaces is None or vlans is None:
        emit(policy.interface_rule, "unable_to_assess", "interface_or_vlan_collection_unavailable")
        return findings

    key = lambda name: canonical_interface_name(device["platform"], name)
    actual = {key(record.port_name): record for record in interfaces}
    profiles = {}
    for profile in vlans.interfaces:
        profiles.setdefault(key(profile.interface_name), []).append(profile)
    groups = {}
    for name, record in sorted(actual.items()):
        parent, separator, suffix = name.rpartition(".")
        parent = parent if separator and suffix.isdigit() else name
        groups.setdefault(parent, []).append((name, record))
    if not groups:
        emit(policy.interface_rule, "not_applicable", "no_actual_interfaces")
    for parent, records in sorted(groups.items()):
        services, members, unresolved = set(), [], []
        invalid = parent not in actual
        for name, record in records:
            candidates = profiles.get(name, [])
            if len(candidates) != 1:
                invalid = True
                continue
            profile = candidates[0]
            if profile.port_type != "service":
                if profile.port_type not in {"access", "trunk", "hybrid", "evc", "routed"}:
                    invalid = True
                continue
            # A service subinterface is already a real normalized identity; only
            # its terminal unit suffix is removed for the analysis grouping key.
            if name == parent:
                invalid = True
                continue
            members.append({"interface": record.port_name, "bridge_domains": profile.bridge_domains,
                            "service_mappings": profile.service_mappings})
            if not profile.bridge_domains:
                invalid = True
            for domain in profile.bridge_domains:
                candidates = {obj for obj in objects if obj.domain_id == domain}
                if len(candidates) != 1:
                    unresolved.append(domain)
                    invalid = True
                else:
                    services.update(candidates)
        observed = {"objects": projection(services), "members": members}
        missing = []
        if invalid:
            status, reason = "unable_to_assess", "parent_or_service_identity_unavailable_or_ambiguous"
        elif not all(matches(group, services) for group in policy.signature):
            status, reason = "not_applicable", "signature_not_matched"
        else:
            status, reason, missing = assess(services)
        emit(policy.interface_rule, status, reason,
             interface=actual[parent].port_name if parent in actual else None,
             observed=observed, missing=missing,
             evidence={"parent_join_key": parent, "unresolved_domains": sorted(set(unresolved)),
                       "vlan_collection_time": vlans.collection_time.isoformat(),
                       "interface_collection_times": sorted({r.collection_time.isoformat() for _, r in records})})
    return findings
