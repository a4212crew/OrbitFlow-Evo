"""Evidence-backed review projection of family AuditResolver results, not policy.

No template decisions, CLI parsing, execution or modification of compliance facts.
"""

from dataclasses import asdict, replace
import hashlib
import json
import re

from orbitflow.compliance.resolvers import children, evidence, last, parent_name, resolver_for
from orbitflow.compliance.vlan import safe_data
from orbitflow.logging import sanitize_text
from orbitflow.vendors.configuration_facts import _safe_source


def configured_values(nodes, kind):
    """Retain configured tags, including values outside the audit policy range."""
    return sorted({v for n in children(nodes, kind) for v in n.value
                   if type(v) is int})


def resolved_records(resolver):
    records = []
    family = resolver.context.device_family
    xr_references = {resolver.key(a.value) for root in children(resolver.roots, "l2vpn")
                     for group in children(root.children, "bridge_group")
                     for domain in children(group.children, "bridge_domain")
                     for a in children(domain.children, "attachment")}

    def emit(key, methods, subtype, *, mapping=None, proof=None, status="resolved", extra=()):
        row = resolver.rows[key]
        problems = list(row["configuration_findings"])
        problems.extend(dict(code=code, evidence=[]) for code in extra)
        if status == "resolved" and (row["review"] or problems):
            status = "review_needed"
        record = dict(record_kind="interface_service", config_interface_name=row["config_interface_name"],
                      parent_interface=parent_name(row["config_interface_name"]) or "",
                      configuration_owner=row["configuration_owner"], methodology=methods,
                      subtype=subtype, status=status, review_needed=status != "resolved",
                      service_instance_id=(mapping or {}).get("service_instance_id", ""),
                      mapping=mapping or {}, configuration_findings=problems,
                      evidence=proof if proof is not None else row["evidence"])
        records.append(record)
        return record

    for key, node in sorted(resolver.config.items()):
        row, lines = resolver.rows[key], node.children
        count = len(records)
        switching = {"mode", "access", "allowed", "allowed_add", "allowed_remove", "allowed_except",
                     "unsupported_allowed", "native", "trunk_pvid", "hybrid_pvid", "tagged", "untagged_vlans"}
        if family in {"C3750X", "C3850", "ME3600X", "NE05", "NE05E"} and (
                any(n.kind in switching for n in lines) or row.get("inherited_from")):
            mixed = bool(row["child_interfaces"]) or any(
                n.kind in {"service_instance", "termination", "vsi_binding"} for n in lines)
            # ME3600X may retain an empty conventional trunk alongside EVCs.
            # Keep service membership out of the M01 projection even here.
            empty_evc_trunk = (
                family == "ME3600X" and bool(children(lines, "service_instance"))
                and not row["child_interfaces"]
                and {n.value for n in children(lines, "mode")} == {"trunk"}
                and bool(children(lines, "allowed"))
                and all(n.value == "NONE" for n in children(lines, "allowed"))
                and not any(n.kind in {"access", "routed", "allowed_add", "allowed_remove",
                                       "allowed_except", "unsupported_allowed", "termination", "vsi_binding"}
                            for n in lines))
            membership = {k: row[k] for k in ("tagged", "untagged", "native", "pvid", "all_vlan")}
            if mixed:
                # The audit row may contain service memberships/consolidation;
                # don't label those as conventional switching membership.
                membership = {}
            membership["configured_switching"] = [asdict(n) for n in lines if n.kind in switching]
            emit(key, ["M06" if family in {"NE05", "NE05E"} else "M01"],
                 last(lines, "mode") or row["interface_type"],
                 mapping=membership, extra=("MIXED_INTERFACE_CONSTRUCTS",) if mixed and not empty_evc_trunk else ())
        if family in {"ASR920", "ME3600X"}:
            for mapping in row["numeric_mappings"]:
                local, global_ = mapping["inline_bridge_domain"], mapping["global_bridge_domain"]
                methods = (["M02"] if global_ else []) + (["M03"] if local else [])
                status = mapping["binding_status"]
                status = "resolved" if status == "valid" else status
                extra = []
                if local and global_:
                    extra.append("EQUIVALENT_LOCAL_GLOBAL_BINDING" if local == global_ else "MIXED_BINDING_CONFLICT")
                    if status == "resolved":
                        status = "mixed_equivalent"
                if mapping["encapsulation_type"] == "unknown" or mapping.get("classification_status") == "ambiguous":
                    status = "ambiguous"
                service_nodes = [n for n in lines if n.kind == "service_instance"
                                 and n.value == mapping["service_instance_id"]]
                service_lines = [c for n in service_nodes for c in n.children]
                detail = dict(mapping, outer_vlan=configured_values(service_lines, "encapsulation"),
                              inner_vlan=configured_values(service_lines, "inner_vlan"))
                emit(key, methods, "evc_global_and_local" if local and global_ else
                     "evc_global" if global_ else "evc_local" if local else "evc_unbound",
                     mapping=detail, proof=evidence((replace(node, children=()),)), status=status, extra=extra)
                records[-1]["evidence"] += mapping["evidence"]
                for domain in children(resolver.roots, "bridge_domain"):
                    if domain.value in global_:
                        records[-1]["evidence"] += evidence((replace(domain, children=()),))
        if family == "NCS540" and (node.kind == "l2_interface" or key in xr_references or children(lines, "encapsulation")):
            # Use this child's own mapping, never a parent's consolidated list.
            mapping = row["numeric_mappings"][0]
            outer, inner = configured_values(lines, "encapsulation"), configured_values(lines, "inner_vlan")
            is_pw = bool(re.match(r"(?i)(?:pw-ether|pw-iw|pseudowire)", node.value))
            is_l2 = node.kind == "l2_interface" and not is_pw and not re.match(r"(?i)(?:bvi|bdi)", node.value)
            record = emit(key, ["M04"] if is_l2 else [],
                 "pseudowire_attachment" if is_pw else "l2transport_attachment" if is_l2 else "routed_attachment",
                 mapping=dict(mapping,
                 outer_vlan=outer, inner_vlan=inner,
                 encapsulation_type="dot1q" if outer else "untagged" if children(lines, "untagged") else "unknown"),
                 proof=mapping["evidence"], status="resolved" if not row["configuration_findings"] else "review_needed")
            if not is_l2:
                record.update(record_kind="service_context", parent_interface="",
                              status="out_of_scope", review_needed=False)
            for root in children(resolver.roots, "l2vpn"):
                for group in children(root.children, "bridge_group"):
                    for domain in children(group.children, "bridge_domain"):
                        if any(resolver.key(a.value) == key for a in children(domain.children, "attachment")):
                            records[-1]["evidence"] += evidence(tuple(replace(n, children=()) for n in (root, group, domain)))
        if family in {"NE05", "NE05E"} and any(n.kind in {"termination", "vsi_binding", "control_vid"} for n in lines):
            mappings = [m for m in row["numeric_mappings"] if "vsi" in m]
            mapping = mappings[0] if mappings else {}
            bindings = sorted({n.value for n in children(lines, "vsi_binding")})
            emit(key, ["M07"], "termination_vsi" if children(lines, "termination") else "untagged_vsi",
                 mapping=dict(mapping, vsi_bindings=bindings, outer_vlan=configured_values(lines, "termination"),
                              inner_vlan=configured_values(lines, "inner_vlan")),
                 status="resolved" if mapping.get("binding_status") == "valid" else "unresolved")
        if family == "NE05E" and parent_name(node.value) and children(lines, "encapsulation"):
            # VRP encapsulation facts here are vlan-type dot1q, not termination.
            # Neither the audit row's default routed type nor a tag proves role.
            outer = configured_values(lines, "encapsulation")
            mixed = any(n.kind in switching | {"termination", "vsi_binding", "control_vid"} for n in lines)
            record = emit(key, ["M08"], "vlan_tagged_subinterface",
                          mapping=dict(outer_vlan=outer, inner_vlan=[],
                                       encapsulation_type="vlan-type-dot1q", role="not_determined"))
            for code, nodes in (
                    ("CONFLICTING_VLAN_TAGS", children(lines, "encapsulation") if len(outer) > 1 else []),
                    ("MIXED_INTERFACE_CONSTRUCTS", list(lines) if mixed else [])):
                if nodes:
                    record.update(status="review_needed", review_needed=True)
                    record["configuration_findings"].append(dict(code=code, evidence=evidence(nodes)))
        if family == "EdgeSwitch" and (any(n.kind in {"include", "exclude", "tagged", "pvid", "untagged_vlans"}
                                           for n in lines) or row.get("inherited_from")):
            emit(key, ["M05"], row["interface_type"], mapping={k: row.get(k, []) for k in
                 ("configured_membership_vlans", "configured_tagged_vlans", "configured_pvid", "tagged", "untagged")},
                 status="unresolved" if row["interface_type"] in {"routed", "no_membership"} else "resolved")
        if count == len(records) and any(n.kind not in {"description", "shutdown", "routed"} for n in lines) and not row["child_interfaces"]:
            if re.match(r"(?i)(?:pw-ether|pw-iw|pseudowire|bvi|bdi|loopback|mgmt)", node.value):
                continue
            emit(key, [], "unclassified", status="unresolved", extra=("NO_SUPPORTED_METHODOLOGY_EVIDENCE",))

    # Missing references are exceptions, never fabricated configured interfaces.
    for problem in resolver.problems:
        method = {"INVALID_BRIDGE_DOMAIN_MEMBER_REFERENCE": ["M02"],
                  "MISSING_BRIDGE_DOMAIN_INTERFACE_REFERENCE": ["M04"]}.get(problem["code"], [])
        records.append(dict(record_kind="reference_exception", config_interface_name="",
                            methodology=method, subtype="invalid_reference", status="invalid_reference",
                            review_needed=True, configuration_findings=[problem], evidence=problem["evidence"],
                            mapping={k: v for k, v in problem.items() if k not in {"code", "evidence"}}))

    def unknowns(nodes, interface="", service="", ancestors=()):
        for node in nodes:
            owner = node.value if node.kind in {"interface", "l2_interface"} else interface
            service_id = node.value if node.kind == "service_instance" else service
            if node.kind == "tag_rewrite":
                matching = [r for r in records if owner and resolver.key(r["config_interface_name"]) == resolver.key(owner)
                            and r.get("service_instance_id", "") == service_id]
                supported_scope = (
                    (family in {"ME3600X", "ASR920"} and bool(service_id)) or
                    (family == "NCS540" and not service_id and parent_name(owner)
                     and resolver.config.get(resolver.key(owner)) is not None
                     and resolver.config[resolver.key(owner)].kind == "l2_interface"))
                if not matching:
                    matching = [dict(record_kind="syntax_exception", config_interface_name=owner,
                                     service_instance_id=service_id, methodology=[], subtype="rewrite_context",
                                     status="review_needed", review_needed=True, mapping={},
                                     configuration_findings=[], evidence=evidence(ancestors))]
                    records.extend(matching)
                for record in matching:
                    profiles = record.setdefault("mapping", {}).setdefault("rewrite_profiles", [])
                    profile = dict(asdict(node.value), config_interface_name=owner,
                                   service_instance_id=service_id, evidence=evidence((node,)),
                                   syntax_status="recognized", platform_support="not_assessed")
                    conflicting = any(any(p[k] != profile[k] for k in
                                          ("direction", "operation", "parameters", "symmetric")) for p in profiles)
                    profiles.append(profile)
                    record["evidence"] += evidence((node,))
                    in_scope = supported_scope and (record["subtype"].startswith("evc_")
                                                     or record["subtype"] == "l2transport_attachment")
                    code = "REWRITE_SCOPE_UNSUPPORTED" if not in_scope else "CONFLICTING_TAG_REWRITES" if conflicting else ""
                    if code:
                        record.update(status="review_needed", review_needed=True)
                        record["configuration_findings"].append(dict(code=code, evidence=[e for p in profiles for e in p["evidence"]]))
            if node.kind == "methodology_unknown":
                matching = [r for r in records if owner and resolver.key(r["config_interface_name"]) == resolver.key(owner)
                            and (not service_id or r.get("service_instance_id") == service_id)]
                for record in matching:
                    record.update(status="review_needed", review_needed=True)
                    record["configuration_findings"].append(dict(code="UNSUPPORTED_FORWARDING_SYNTAX", evidence=evidence((node,))))
                    record["evidence"] += evidence((node,))
                if not matching:
                    records.append(dict(record_kind="syntax_exception", config_interface_name=owner, service_instance_id=service_id, methodology=[],
                                        subtype="unknown", status="unresolved", review_needed=True,
                                        configuration_findings=[dict(code="UNSUPPORTED_FORWARDING_SYNTAX", evidence=evidence((node,)))], evidence=evidence((*ancestors, node))))
            unknowns(node.children, owner, service_id, (*ancestors, replace(node, children=())))
    unknowns(resolver.review_roots)
    return records


def resolve_methodologies(context, interfaces, vlans, *, management_ip="", clean=sanitize_text):
    """Public single-device review API using the same family resolver and snapshot."""
    device = dict(device_id=context.device_id if context else "", hostname=context.hostname if context else "",
                  management_ip=context.management_ip if context else management_ip,
                  platform=context.platform if context else "", family=context.device_family if context else "")
    factory = resolver_for(context) if context else None
    if not factory or vlans is None or vlans.configuration is None:
        records = [dict(record_kind="target_exception", methodology=[], subtype="unavailable",
                        status="unable_to_assess", review_needed=True, evidence=[],
                        configuration_findings=[dict(code="UNSUPPORTED_FAMILY_OR_UNAVAILABLE_EVIDENCE")])]
    else:
        resolver = factory(context, vlans)
        records = resolver.methodology_result()
        actual = {resolver.key(i.port_name): i.port_name for i in interfaces or ()}
        for record in records:
            name = record.get("config_interface_name", "")
            record["interface_name"] = actual.get(resolver.key(name), "not observed") if name else ""
            record["interface_match_status"] = ("matched" if resolver.key(name) in actual else "config_only") if name else ""
        if not records:
            records = [dict(record_kind="target_exception", methodology=[], subtype="empty_snapshot",
                            status="unresolved", review_needed=True, evidence=[], configuration_findings=[])]
    for record in records:
        record["device"] = device
    sanitize = lambda value: clean(_safe_source(value))
    # Digest of the sanitized fact projection, explicitly not a raw backup hash.
    snapshot = safe_data([asdict(n) for n in vlans.configuration], sanitize) if vlans and vlans.configuration is not None else None
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest() if snapshot is not None else ""
    for record in records:
        record["configuration_facts_digest"] = digest
    return safe_data(records, sanitize)
