"""Closed v2 offline contract, deterministic checks and exact source binding."""

import hashlib
import ipaddress
import re

from .plans import IDENTITY_FIELDS, canonical, keys, label, require, safe_text
from .catalogue import VERSION, interface_name, parameters, render, select

POLICY = {"offline_only": True, "execution_authorized": False,
          "advanced_approval": "separate_authenticated_authority_required"}
WARNING = "Inventory is latest-known only; live identity, state and capability checks are required before future execution."


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(value):
    require(type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None, "invalid content digest")


def validate_identity(ident):
    keys(ident, IDENTITY_FIELDS)
    for key, value in ident.items():
        if key == "serial_number" and value == "":
            continue
        if key == "management_ip":
            try:
                require(str(ipaddress.ip_address(value)) == value, "noncanonical IP")
            except ValueError:
                require(False, "invalid management IP")
        else:
            label(value)


def manual_lines(value):
    require(type(value) is list and 0 < len(value) <= 100, "manual CLI lines required")
    for line in value:
        safe_text(line)
        require(not re.search(r"(?i)\b(username|community|radius|tacacs|crypto|key|certificate|banner|"
                              r"authentication|snmp|enable|boot|reload|write|save|commit|copy|delete|erase)\b", line),
                "sensitive or operational manual CLI forbidden")
    return value


def operation(raw, ident, flags):
    keys(raw, "row_id source_row interface action template_id template_version order depends_on parameters manual_cli")
    label(raw["row_id"])
    require(type(raw["source_row"]) is int and raw["source_row"] >= 2, "invalid source row")
    require(type(raw["order"]) is int and 0 < raw["order"] <= 100000, "explicit positive order required")
    interface_name(raw["interface"], ident["platform"])
    require(type(raw["depends_on"]) is list and len(set(raw["depends_on"])) == len(raw["depends_on"]),
            "invalid dependencies")
    for dependency in raw["depends_on"]:
        label(dependency)
    if raw["action"] == "manual CLI":
        require(raw["template_id"] == raw["template_version"] == "" and raw["parameters"] == {},
                "manual CLI cannot select a template")
        commands = manual_lines(raw["manual_cli"])
        return dict(raw, commands=commands, method="advanced", effects={"unknown": True},
                    preconditions=["Engineer must establish command scope and all effects."],
                    verification=["Engineer must define complete verification; unknown effects remain unresolved."])
    require(raw["manual_cli"] == [], "template/manual sources must be separate ordered rows")
    template = select(ident, flags, raw["action"], raw["template_id"], raw["template_version"])
    values = parameters(template, raw["parameters"])
    name = template.template_id
    if name.startswith("cisco.evc.") or name in ("cisco.access", "cisco.trunk.add", "cisco.trunk.replace"):
        require("." not in raw["interface"], "physical or aggregate interface required")
    if name == "huawei.dot1q":
        require("." in raw["interface"], "explicit existing or proposed subinterface identity required")
    effects = dict(values)
    effects["kind"] = name
    return dict(raw, parameters=values, commands=render(template, raw["interface"], values),
                method=template.method, effects=effects,
                preconditions=["Confirm exact interface identity and absence of incompatible existing services.",
                               "Confirm referenced VLANs and shared resources exist and have compatible ownership."],
                verification=["Confirm interface configuration equals the declared effects and unrelated services remain unchanged."])


def findings(operations):
    """Conservative conflicts. Ordering alone never authorizes overriding another row."""
    result = []
    by_id = {op["row_id"]: op for op in operations}
    def add(code, rows, level="blocked"):
        item = {"code": code, "rows": sorted(set(rows)), "level": level}
        if item not in result:
            result.append(item)
    orders = {}
    for op in operations:
        if op["order"] in orders:
            add("duplicate_device_order", [op["row_id"], orders[op["order"]]])
        orders[op["order"]] = op["row_id"]
        for dep in op["depends_on"]:
            if dep not in by_id or by_id[dep]["order"] >= op["order"]:
                add("missing_or_forward_dependency", [op["row_id"]])
        if op["action"] == "manual CLI":
            add("unknown_manual_effects_authenticated_review_required", [op["row_id"]], "review_required")
    for i, left in enumerate(operations):
        for right in operations[i + 1:]:
            same = left["interface"] == right["interface"]
            a, b = left["effects"], right["effects"]
            rows = [left["row_id"], right["row_id"]]
            if "unknown" in a or "unknown" in b:
                # Free CLI can leave interface context or mutate a shared device resource.
                add("manual_scope_or_template_collision_unresolved", rows, "review_required")
                manual = left if "unknown" in a else right
                other = right if manual is left else left
                if other["effects"].get("kind", "").startswith("cisco."):
                    from orbitflow.vendors.cisco.guided_plan import manual_conflicts
                    for code in manual_conflicts(manual["commands"], other["effects"], same):
                        add(code, rows)
                continue
            if not same:
                # Parent/child configuration could affect the child; require review.
                if left["interface"].split(".")[0] == right["interface"].split(".")[0]:
                    add("parent_child_interaction", rows, "review_required")
                continue
            ak, bk = a["kind"], b["kind"]
            if ak.startswith("cisco.evc.") and bk.startswith("cisco.evc."):
                if a["service_instance"] == b["service_instance"]:
                    add("duplicate_service_instance", rows)
                if a["outer_vlan"] == b["outer_vlan"] and (a.get("inner_vlan") == b.get("inner_vlan") or
                                                          "inner_vlan" not in a or "inner_vlan" not in b):
                    add("overlapping_encapsulation", rows)
            elif ak == bk == "cisco.trunk.add":
                if set(a["vlans"]) & set(b["vlans"]):
                    add("duplicate_vlan_add", rows)
            else:
                add("conflicting_interface_operations", rows)
            if "description" in a and "description" in b and a["description"] != b["description"]:
                add("conflicting_interface_description", rows)
    return result


RAW_FIELDS = "row_id source_row interface action template_id template_version order depends_on parameters manual_cli"


def build(change_id, batch_id, source, ident, flags, operations, input_errors):
    ordered = sorted(operations, key=lambda op: (op["order"], op["row_id"]))
    issues = findings(ordered)
    if input_errors:
        issues.append(dict(code="device_has_rejected_or_skipped_inputs", rows=sorted(input_errors), level="blocked"))
    status = "blocked" if any(f["level"] == "blocked" for f in issues) else (
        "review_required" if issues else "offline_validated")
    return dict(schema_version=2, change_id=change_id, batch_id=batch_id, source=source,
                identity=ident, capability_flags=sorted(flags), operations=ordered,
                input_errors=sorted(input_errors), findings=issues, status=status,
                warnings=[WARNING], execution_policy=dict(POLICY))


def validate(data):
    keys(data, "schema_version change_id batch_id source identity capability_flags operations input_errors findings status warnings execution_policy")
    require(type(data["schema_version"]) is int and data["schema_version"] == 2, "unsupported schema version")
    label(data["change_id"])
    label(data["batch_id"])
    validate_identity(data["identity"])
    source = data["source"]
    keys(source, "kind version catalogue_version request_digest prepared_digest completed_digest snapshot_digest")
    require(source["kind"] == "guided_workbook" and source["version"] == "1" and
            source["catalogue_version"] == VERSION, "unsupported source version")
    for key in ("request_digest", "prepared_digest", "completed_digest", "snapshot_digest"):
        sha(source[key])
    flags = data["capability_flags"]
    require(type(flags) is list and len(set(flags)) == len(flags), "invalid capability flags")
    for flag in flags:
        label(flag)
    ops = data["operations"]
    require(type(ops) is list and 0 < len(ops) <= 1000, "invalid operation count")
    require(len({op["row_id"] for op in ops}) == len(ops), "duplicate row identity")
    rebuilt = []
    for op in ops:
        keys(op, RAW_FIELDS + " commands method effects preconditions verification")
        normalized = operation({k: op[k] for k in RAW_FIELDS.split()}, data["identity"], flags)
        require(canonical(normalized) == canonical(op), "tampered operation or commands")
        rebuilt.append(normalized)
    require(type(data["input_errors"]) is list and len(set(data["input_errors"])) == len(data["input_errors"]),
            "invalid input failures")
    for row in data["input_errors"]:
        label(row)
    expected = build(data["change_id"], data["batch_id"], source, data["identity"], flags, rebuilt, data["input_errors"])
    require(canonical(expected) == canonical(data), "tampered validation or offline policy")
