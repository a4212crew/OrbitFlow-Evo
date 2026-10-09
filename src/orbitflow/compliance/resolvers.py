"""Family-specific relationship validation over preserved observation facts.

No CLI syntax parsing, transport, policy thresholds, or report formatting lives
here. Numeric facts are derived only from validated configured relationships.
"""

from dataclasses import replace

from orbitflow.vendors.interface_names import canonical_interface_name


def children(nodes, kind):
    return [node for node in nodes if node.kind == kind]


def last(nodes, kind, default=""):
    items = children(nodes, kind)
    return items[-1].value if items else default


def numeric(value):
    if isinstance(value, str):
        value = (int(value),) if value.isdigit() else ()
    return {v for v in value if type(v) is int and 2 <= v <= 4001}


def values(nodes, kind):
    return set().union(*(numeric(n.value) for n in children(nodes, kind)))


def evidence(nodes):
    result = []
    for node in nodes:
        result.append(dict(source_filename=node.source_filename, line=node.line, excerpt=node.excerpt))
        result.extend(evidence(node.children))
    return result


def parent_name(name):
    parent, dot, suffix = name.rpartition(".")
    return parent if dot and suffix.isdigit() else None


class AuditResolver:
    """Per-device resolver state; never shared across execution workers."""

    def __init__(self, context, state):
        self.context, self.state = context, state
        self.key = lambda name: canonical_interface_name(context.platform, name)
        self.routed = {self.key(p.interface_name) for p in state.interfaces if p.port_type == "routed"}
        self.review_roots = state.configuration
        # Review-only syntax markers must never alter established audit facts.
        def audit_nodes(nodes):
            return tuple(replace(n, children=audit_nodes(n.children)) for n in nodes
                         if not n.kind.startswith("methodology_switchport_")
                         and n.kind not in {"methodology_unknown", "methodology_evidence", "methodology_context", "tag_rewrite",
                                           "methodology_interface", "methodology_encapsulation",
                                           "methodology_member", "methodology_routed_attachment"})
        self.roots = audit_nodes(state.configuration)
        self.config, sources = {}, {}
        for node in self.roots:
            if node.kind in {"interface", "l2_interface"}:
                key = self.key(node.value)
                sources.setdefault(key, []).append(node)
                if key in self.config:
                    old = self.config[key]
                    node = replace(node, value=old.value, children=old.children + node.children)
                self.config[key] = node
        self.rows = {key: dict(config_interface_name=node.value, interface_type="routed",
                              description=last(node.children, "description"),
                              shutdown=last(node.children, "shutdown") == "shutdown",
                              valid_interface_vlans=[], tagged=[], untagged=[], native=[], pvid=[],
                              numeric_mappings=[], child_interfaces=[], forwarding_domains=[],
                              configuration_findings=[], evidence=evidence(sources[key]),
                              review=False, all_vlan=False, configuration_owner=node.value)
                     for key, node in self.config.items()}
        self.database = values(self.roots, "vlan")
        self.database_proof = set()
        self.prove([n for n in children(self.roots, "vlan") if numeric(n.value)])
        self.problems = []
        self.mappings = []

    def prove(self, nodes):
        """Select contributing statements; their original ancestors supply context."""
        self.database_proof.update((n.source_filename, n.line) for n in nodes)

    def database_evidence(self):
        def project(node):
            nested = [item for child in node.children for item in project(child)]
            if nested or (node.source_filename, node.line) in self.database_proof:
                return evidence((replace(node, children=()),)) + nested
            return []
        return [item for node in self.roots for item in project(node)]

    def problem(self, code, key=None, nodes=(), **details):
        item = dict(code=code, **details, evidence=evidence(nodes))
        (self.rows[key]["configuration_findings"] if key in self.rows else self.problems).append(item)

    def membership(self, key, tags=(), untagged=(), kind=None):
        row = self.rows[key]
        row.update(tagged=sorted(set(tags)), untagged=sorted(set(untagged)),
                   valid_interface_vlans=sorted(set(tags) | set(untagged)))
        if kind:
            row["interface_type"] = kind

    def consolidate(self, key, *, require_trunk=False, preserve_parent_type=False):
        parent = parent_name(key)
        if parent is None:
            return
        row = self.rows[key]
        if parent not in self.rows:
            self.problem("PARENT_INTERFACE_NOT_FOUND", key, (self.config[key],))
            row["review"] = True
            return
        target = self.rows[parent]
        if require_trunk and target["interface_type"] not in {"trunk", "hybrid"}:
            self.problem("PARENT_INTERFACE_NOT_TRUNK", key, (self.config[parent], self.config[key]))
            row["review"] = True
        else:
            target["valid_interface_vlans"] = sorted(set(target["valid_interface_vlans"]) | set(row["valid_interface_vlans"]))
            target["tagged"] = sorted(set(target["tagged"]) | set(row["tagged"]))
            if (row["valid_interface_vlans"] and not require_trunk
                    and not (preserve_parent_type and target["interface_type"] in {"trunk", "hybrid"})):
                target["interface_type"] = "evc"
        target["child_interfaces"].append(dict(interface_name=row["config_interface_name"],
                                              description=row["description"], shutdown=row["shutdown"],
                                              consolidated_subinterface=True,
                                              numeric_mappings=row["numeric_mappings"],
                                              valid_interface_vlans=row["valid_interface_vlans"]))
        target["numeric_mappings"].extend(row["numeric_mappings"])
        target["forwarding_domains"].extend(row["forwarding_domains"])
        target["configuration_findings"].extend(row["configuration_findings"])
        target["evidence"].extend(row["evidence"])
        target["review"] |= row["review"] and not target["valid_interface_vlans"]
        row["consolidated_into"] = parent

    def aggregates(self, edge=False):
        for key, node in self.config.items():
            group = last(node.children, "aggregate")
            if not group:
                continue
            name = "Port-channel" + group
            if edge:
                # EdgeSwitch's logical LAG slot is 3: addport 3/N refers
                # to interface lag N, not an interface literally named 3/N.
                # The documented alternative is addport lag N. Preserve
                # unsupported references as evidence, without guessing owners.
                name = "lag " + group[2:] if group.startswith("3/") else group
            owner = self.key(name) if not edge or name.startswith("lag ") else None
            row = self.rows[key]
            if owner not in self.rows:
                self.problem("AGGREGATE_NOT_FOUND", key, children(node.children, "aggregate"), aggregate=name)
                row["review"] = True
                continue
            aggregate = self.rows[owner]
            explicit = any(n.kind in {"mode", "allowed_add", "allowed_remove", "allowed_except", "unsupported_allowed", "allowed", "include", "exclude", "pvid", "tagged", "access", "native"}
                           for n in node.children)
            if explicit and any(row[field] != aggregate[field]
                                for field in ("interface_type", "valid_interface_vlans", "native", "pvid", "tagged")):
                self.problem("AGGREGATE_CONFIG_CONFLICT" if edge else "PORT_CHANNEL_CONFIG_CONFLICT",
                             key, (node, self.config[owner]), aggregate=aggregate["config_interface_name"])
            for field in ("interface_type", "valid_interface_vlans", "tagged", "untagged", "native", "pvid", "all_vlan", "review"):
                row[field] = aggregate[field]
            row["configuration_owner"] = aggregate["config_interface_name"]
            row["inherited_from"] = aggregate["config_interface_name"]
            row["evidence"].extend(aggregate["evidence"])

    def result(self):
        self.resolve()
        for key, row in self.rows.items():
            row["no_vlan_service_configuration"] = (
                self.config[key].kind != "l2_interface"
                and not any(n.kind not in {"description", "shutdown", "routed"}
                            for n in self.config[key].children)
                and not row["child_interfaces"] and not row.get("inherited_from")
                and not row["configuration_findings"])
        return dict(valid_database_vlans=sorted(self.database),
                    database_inventory=[dict(object_type=o.object_type, object_id=o.object_id,
                                             domain_id=o.domain_id, name=o.name) for o in self.state.objects],
                    numeric_mappings=self.mappings, configuration_findings=self.problems,
                    evidence=self.database_evidence(), interfaces=self.rows)

    def methodology_result(self):
        """Separate read-only projection; callers use a fresh per-device resolver."""
        from orbitflow.compliance.methodology import resolved_records
        # Reuse family resolution for review-only Huawei spellings and EVC members.
        # Ordinary result() never promotes these into compliance input facts.
        kinds = {"methodology_interface": "interface", "methodology_encapsulation": "encapsulation",
                 "methodology_member": "member"}
        def review_nodes(nodes):
            return tuple(replace(n, kind=kinds.get(n.kind, n.kind), children=review_nodes(n.children))
                         for n in nodes)
        projection = type(self)(self.context, replace(self.state, configuration=review_nodes(self.review_roots)))
        projection.result()
        return resolved_records(projection)


class CatalystAuditResolver(AuditResolver):
    def conventional(self, key, *, validate_database=True):
        node, row = self.config[key], self.rows[key]
        lines = node.children
        mode = last(lines, "mode")
        row["native"] = sorted(numeric(last(lines, "native", ())))
        access = bool(children(lines, "access"))
        contradictory = access and (mode not in {"", "access"}
                                    or any(n.kind in {"routed", "allowed", "allowed_add", "allowed_remove", "allowed_except", "unsupported_allowed"} for n in lines))
        if self.context.device_family in {"C3750X", "ME3600X"} and mode == "access":
            contradictory |= any(n.kind in {"allowed", "allowed_add", "allowed_remove", "allowed_except", "unsupported_allowed"} for n in lines)
        if contradictory:
            self.problem("CONFLICTING_SWITCHPORT_INTENT", key, (node,))
            authoritative = (self.context.device_family in {"C3750X", "ME3600X"}
                             and mode in {"access", "trunk"} and not children(lines, "routed"))
            if not authoritative:
                if mode not in {"access", "trunk"}:
                    self.problem("UNRESOLVED_SWITCHPORT_MODE", key, (node,))
                row.update(interface_type="review", review=True)
                return
        if mode == "access" or (not mode and access):
            self.membership(key, untagged=numeric(last(lines, "access", ())), kind="access")
            return
        if mode != "trunk":
            has_switching = any(n.kind in {"mode", "allowed", "allowed_add", "allowed_remove", "allowed_except", "access", "native", "trunk_encapsulation", "unsupported_allowed"} for n in lines)
            inherited = bool(last(lines, "aggregate")) and not has_switching
            if not inherited and has_switching:
                self.problem("UNRESOLVED_SWITCHPORT_MODE", key, (node,))
                row.update(interface_type="review", review=True)
            return
        if children(lines, "unsupported_allowed"):
            self.problem("UNSUPPORTED_ALLOWED_VLAN_OPERATION", key, children(lines, "unsupported_allowed"))
            row.update(interface_type="review", review=True)
            return
        allowed = "ALL"
        operations = [n for n in lines if n.kind in {"allowed", "allowed_add", "allowed_remove", "allowed_except"}]
        for operation in operations:
            if operation.kind == "allowed":
                allowed = operation.value
            elif operation.kind == "allowed_except":
                allowed = tuple(sorted(self.database - numeric(operation.value)))
            else:
                if allowed == "ALL" and self.context.device_family == "C3750X" and last(lines, "trunk_encapsulation") != "dot1q":
                    self.problem("INVALID_ALL_VLAN_TRUNK", key, operations)
                    row.update(interface_type="review", review=True)
                    return
                current = self.database.copy() if allowed == "ALL" else numeric(allowed)
                operand = numeric(operation.value)
                allowed = tuple(sorted(current | operand if operation.kind == "allowed_add" else current - operand))
        row["configured_membership_vlans"] = allowed
        if allowed == "ALL":
            row["all_vlan"] = True
            if self.context.device_family == "C3750X" and last(lines, "trunk_encapsulation") != "dot1q":
                self.problem("INVALID_ALL_VLAN_TRUNK", key, (node,))
                row.update(interface_type="review", review=True)
                return
            tags = self.database
        else:
            tags = numeric(allowed)
            missing = tags - self.database if validate_database else set()
            if missing:
                self.problem("ALLOWED_VLAN_NOT_IN_DATABASE", key, operations, vlans=sorted(missing))
            if validate_database:
                tags &= self.database
        self.membership(key, tags, kind="trunk")

    def resolve(self):
        for key in self.config:
            self.conventional(key)
        self.aggregates()


class EVCAuditResolver(CatalystAuditResolver):
    def resolve(self):
        asr = self.context.device_family == "ASR920"
        bridges = children(self.roots, "bridge_domain")
        bindings = {}
        for bd in bridges:
            for member in children(bd.children, "member"):
                interface, _, sid = member.value.split()
                key = self.key(interface)
                bindings.setdefault((key, sid), []).append((bd.value, member))
                if key not in self.config or sid not in {n.value for n in children(self.config[key].children, "service_instance")}:
                    self.problem("INVALID_BRIDGE_DOMAIN_MEMBER_REFERENCE", nodes=(bd, member),
                                 interface=interface, service_instance_id=sid, bridge_domain=bd.value)
            if not asr and children(bd.children, "member") and numeric(bd.value) - self.database:
                self.problem("BRIDGE_DOMAIN_MISSING_GLOBAL_VLAN", nodes=(bd,), vlans=sorted(numeric(bd.value) - self.database))
        if asr:
            self.database_proof.clear()
            self.prove([bd for bd in bridges if numeric(bd.value)])
            self.database = set().union(*(numeric(bd.value) for bd in bridges))
        for key, node in self.config.items():
            services = {}
            for service in children(node.children, "service_instance"):
                if service.value in services:
                    service = replace(service, children=services[service.value].children + service.children)
                services[service.value] = service
            if not services:
                if not asr:
                    self.conventional(key, validate_database=False)
                continue
            tagged, untagged, untagged_count = set(), set(), 0
            for sid, service in services.items():
                inline = {n.value for n in children(service.children, "bridge_domain")}
                global_bindings = bindings.get((key, sid), [])
                global_ids = {b for b, _ in global_bindings}
                resolved = inline | global_ids
                if asr:
                    self.database.update(set().union(*(numeric(v) for v in inline)))
                    self.prove([n for n in children(service.children, "bridge_domain") if numeric(n.value)])
                status = "valid" if len(resolved) == 1 else "conflict" if resolved else "unresolved"
                nodes = (service, *(n for _, n in global_bindings))
                if status != "valid":
                    self.problem("CONFLICTING_BRIDGE_DOMAIN_BINDING" if resolved else "UNRESOLVED_SERVICE_INSTANCE",
                                 key, nodes, service_instance_id=sid)
                is_untagged = bool(children(service.children, "untagged"))
                outer = values(service.children, "encapsulation")
                untagged_count += is_untagged
                audit = set().union(*(numeric(v) for v in resolved)) if status == "valid" else set()
                if asr and audit:
                    self.prove(children(service.children, "encapsulation") + children(service.children, "untagged")
                               + [n for _, n in global_bindings])
                if not is_untagged and not outer:
                    self.problem("UNCLEAR_EVC_CLASSIFICATION", key, (service,), service_instance_id=sid)
                    audit = set()
                (untagged if is_untagged else tagged).update(audit)
                mapping = dict(interface_name=node.value, service_instance_id=sid,
                               description=last(service.children, "description"),
                               encapsulation_type="untagged" if is_untagged else "dot1q" if outer else "unknown",
                               outer_vlan=sorted(outer), inner_vlan=sorted(values(service.children, "inner_vlan")),
                               inline_bridge_domain=sorted(inline), global_bridge_domain=sorted(global_ids),
                               resolved_bridge_domain=sorted(resolved) if status == "valid" else [],
                               binding_status=status, tagging_role="untagged" if is_untagged else "tagged",
                               audit_vlan=sorted(audit), evidence=evidence(nodes))
                self.rows[key]["numeric_mappings"].append(mapping)
                self.rows[key]["forwarding_domains"].extend(sorted(resolved))
                self.mappings.append(mapping)
            if untagged_count > 1:
                self.problem("MULTIPLE_UNTAGGED_SERVICE_INSTANCES", key, tuple(services.values()))
                untagged = set()
                kind = "review"
                for mapping in self.rows[key]["numeric_mappings"]:
                    if mapping["tagging_role"] == "untagged":
                        mapping["audit_vlan"] = []
                        mapping["classification_status"] = "ambiguous"
            else:
                kind = "hybrid" if untagged and tagged else "access" if untagged else "evc" if tagged else "review"
            self.membership(key, tagged, untagged, kind)
            # Valid tagged mappings remain independently auditable.
            self.rows[key]["review"] = kind == "review" and not tagged
            if kind == "review" and tagged:
                self.rows[key]["audit_valid_tagged_subset"] = True


class HuaweiAuditResolver(AuditResolver):
    def resolve(self):
        vsis = {node.value: node for node in children(self.roots, "vsi")}
        for key, node in self.config.items():
            lines, row = node.children, self.rows[key]
            mode = last(lines, "mode")
            pvid = values(lines, "trunk_pvid") | values(lines, "hybrid_pvid")
            row["pvid"] = sorted(pvid)
            if children(lines, "access"):
                self.membership(key, untagged=values(lines, "access"), kind="access")
            elif mode in {"trunk", "hybrid"} or children(lines, "allowed") or children(lines, "tagged"):
                tags = self.database.copy() if last(lines, "allowed") == "ALL" or last(lines, "tagged") == "ALL" else values(lines, "allowed") | values(lines, "tagged")
                self.membership(key, tags, values(lines, "untagged_vlans"), "hybrid" if mode == "hybrid" else "trunk")
            vsi = last(lines, "vsi_binding")
            bindings = {n.value for n in children(lines, "vsi_binding")}
            termination = values(lines, "termination")
            if vsi:
                valid = vsi in vsis and len(bindings) == 1
                if len(bindings) > 1:
                    self.problem("CONFLICTING_VSI_BINDING", key, children(lines, "vsi_binding"))
                for missing_vsi in sorted(bindings - vsis.keys()):
                    self.problem("VSI_REFERENCE_NOT_FOUND", key, children(lines, "vsi_binding"), vsi=missing_vsi)
                if not valid and termination:
                    self.problem("L2_TERMINATION_WITHOUT_VALID_VSI", key, (node,))
                if parent_name(key) and not termination:
                    self.problem("L2_SUBINTERFACE_WITHOUT_TERMINATION", key, (node,))
                    valid = False
                tags = termination if valid else set()
                self.database.update(tags)
                if tags:
                    self.prove(children(lines, "termination") + children(lines, "vsi_binding") + [vsis[vsi]])
                self.membership(key, tags, kind="service" if parent_name(key) else "access")
                row["forwarding_domains"] = [vsi]
                row["numeric_mappings"].append(dict(termination_vlan=sorted(termination),
                                                   control_vid=sorted(values(lines, "control_vid")),
                                                   vsi=vsi, binding_status="valid" if valid else "invalid_reference",
                                                   audit_vlan=sorted(tags), untagged=not termination and not parent_name(key),
                                                   evidence=evidence((node, *((vsis[vsi],) if valid else ())))))
                self.mappings.extend(row["numeric_mappings"])
            elif termination or values(lines, "encapsulation") or values(lines, "control_vid"):
                # Retain routed/control detail without making an L2 mapping.
                row["numeric_mappings"].append(dict(termination_vlan=sorted(termination),
                    encapsulation=sorted(values(lines, "encapsulation")),
                    control_vid=sorted(values(lines, "control_vid")), vsi="",
                    binding_status="routed_detail", audit_vlan=[], evidence=evidence((node,))))
                self.mappings.extend(row["numeric_mappings"])
            # Unbound dot1q is routed detail, never inferred L2 membership.
        for key in self.config:
            if parent_name(key):
                bound = bool(last(self.config[key].children, "vsi_binding"))
                parent = self.rows.get(parent_name(key), {})
                # NE05E L2 termination is a child service, independent of a
                # conventional parent trunk declaration. Explicit access intent
                # still conflicts with tagged child forwarding.
                require_trunk = bound and (self.context.device_family != "NE05E"
                                            or parent.get("interface_type") == "access")
                self.consolidate(key, require_trunk=require_trunk, preserve_parent_type=True)


class XRAuditResolver(AuditResolver):
    def resolve(self):
        self.database = set()
        self.database_proof.clear()
        attachments = {}
        for l2vpn in children(self.roots, "l2vpn"):
            for group in children(l2vpn.children, "bridge_group"):
                for bd in children(group.children, "bridge_domain"):
                    identity = (group.value, bd.value)
                    for attachment in children(bd.children, "attachment"):
                        key = self.key(attachment.value)
                        attachments.setdefault(key, []).append((identity, attachment))
                        if key not in self.config:
                            self.problem("MISSING_BRIDGE_DOMAIN_INTERFACE_REFERENCE", nodes=(attachment,),
                                         interface=attachment.value, bridge_domain=identity)
        for key, node in self.config.items():
            bindings = attachments.get(key, [])
            domains = sorted({identity for identity, _ in bindings})
            row = self.rows[key]
            row["forwarding_domains"] = domains
            valid = node.kind == "l2_interface"
            nodes = (node, *(n for _, n in bindings))
            if bindings and not valid:
                self.problem("NON_L2TRANSPORT_BRIDGE_DOMAIN_ATTACHMENT", key, nodes)
            if valid and not bindings:
                self.problem("UNBOUND_L2TRANSPORT_SUBINTERFACE", key, (node,))
            if len(domains) > 1:
                self.problem("CONFLICTING_BRIDGE_DOMAIN_ATTACHMENTS", key, nodes, bridge_domains=domains)
            tags = values(node.children, "encapsulation")
            if valid and not tags:
                if children(node.children, "untagged"):
                    if bindings:
                        self.problem("UNTAGGED_BRIDGE_DOMAIN_MAPPING_UNRESOLVED", key, nodes)
                else:
                    self.problem("L2TRANSPORT_WITHOUT_ENCAPSULATION", key, nodes)
            mapped = tags if valid and len(domains) == 1 and parent_name(key) else set()
            self.database.update(mapped)
            if mapped:
                self.prove(children(node.children, "encapsulation") + [n for _, n in bindings])
            self.membership(key, mapped, kind="service" if valid else "routed")
            row["numeric_mappings"] = [dict(bridge_domains=domains, encapsulation=sorted(tags),
                                             audit_vlan=sorted(mapped), evidence=evidence(nodes))]
            self.mappings.extend(row["numeric_mappings"])
        for key in self.config:
            if parent_name(key):
                self.consolidate(key)


class EdgeSwitchAuditResolver(AuditResolver):
    def resolve(self):
        self.database = set().union(*(values(n.children, "vlan") for n in children(self.roots, "vlan_database")))
        self.database_proof.clear()
        for node in children(self.roots, "vlan_database"):
            self.prove([n for n in children(node.children, "vlan") if numeric(n.value)])
        for key, node in self.config.items():
            members, tagged = set(), set()
            row = self.rows[key]
            for fact in node.children:
                if fact.kind == "include":
                    members.update(numeric(fact.value))
                elif fact.kind == "exclude":
                    members.difference_update(numeric(fact.value))
                elif fact.kind == "tagged":
                    tagged.update(numeric(fact.value))
                elif fact.kind == "untagged_vlans":
                    tagged.difference_update(numeric(fact.value))
            pvid = numeric(last(node.children, "pvid", ()))
            valid = members & self.database
            for code, invalid in (("INTERFACE_VLAN_NOT_IN_DATABASE", members - self.database),
                                  ("TAGGED_VLAN_NOT_IN_MEMBERSHIP", tagged - valid),
                                  ("PVID_NOT_IN_MEMBERSHIP", pvid - valid)):
                if invalid:
                    self.problem(code, key, (node,), vlans=sorted(invalid))
            valid_tags = tagged & valid
            untagged = (pvid & valid) - tagged
            row.update(configured_membership_vlans=sorted(members), configured_tagged_vlans=sorted(tagged),
                       configured_pvid=sorted(pvid), pvid=sorted(pvid))
            kind = "hybrid" if untagged and valid_tags else "access" if untagged else "trunk" if valid_tags else "no_membership"
            if not any(n.kind in {"include", "exclude", "tagged", "untagged_vlans", "pvid"} for n in node.children):
                kind = "routed"
            self.membership(key, valid_tags, untagged if kind != "review" else (), kind)
            row["review"] = kind == "review"
        self.aggregates(edge=True)


def resolver_for(context):
    """Explicit family dispatch. An OS label cannot stand in for Cisco hardware."""
    if context.platform in {"cisco_ios", "cisco_xe"}:
        return {"C3750X": CatalystAuditResolver, "C3850": CatalystAuditResolver,
                "ME3600X": EVCAuditResolver, "ASR920": EVCAuditResolver}.get(context.device_family)
    if context.platform == "cisco_xr" and context.device_family == "NCS540":
        return XRAuditResolver
    if context.platform == "huawei_vrp" and context.device_family in {"NE05", "NE05E"}:
        return HuaweiAuditResolver
    if context.platform == "ubiquiti_edgeswitch" and context.device_family == "EdgeSwitch":
        return EdgeSwitchAuditResolver
    return None
