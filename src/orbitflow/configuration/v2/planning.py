"""Deterministic ordered planning and offline review, independent of adapters."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from orbitflow.configuration.plans import canonical, decode, keys, label, require, IDENTITY_FIELDS
from orbitflow.configuration.approvals import timestamp
from orbitflow.vendors.interface_names import canonical_interface_name
from orbitflow.vendors.cisco.bulk_plan import render as cisco
from orbitflow.vendors.cisco.bulk_plan import assess as assess_cisco
from orbitflow.vendors.huawei.bulk_plan import render as huawei
from orbitflow.vendors.huawei.bulk_plan import assess as assess_huawei
from orbitflow.vendors.ubiquiti.bulk_plan import render as edge
from orbitflow.vendors.configuration_facts import _safe_source
from orbitflow.compliance.vlan import safe_data
from .catalogue import BY_ID, BY_SHEET, FAMILIES, VERSION, safe, normalize_display_inputs

DECISIONS = ("Pending", "Approve", "Reject")
MAX_ROWS = 5000
MAX_CONTENT = 32 * 1024 * 1024


def request(template_id, inputs, *, sheet_order=0, row=3, row_id=None, source_inputs=None):
    require(template_id in BY_ID, "unknown template")
    inputs = BY_ID[template_id].validate(inputs)
    source_inputs = source_inputs if source_inputs is not None else dict(inputs)
    require(type(source_inputs) is dict and set(source_inputs) <= set(BY_ID[template_id].columns)
            and normalize_display_inputs(BY_ID[template_id], source_inputs) == inputs,
            "source input mismatch")
    require(type(sheet_order) is int and 0 <= sheet_order <= 22 and type(row) is int and 3 <= row <= 5002, "invalid position")
    row_id = row_id or hashlib.sha256(canonical([template_id, sheet_order, row, inputs]).encode()).hexdigest()[:24]
    label(row_id)
    return dict(template_id=template_id, inputs=inputs, source_inputs=source_inputs, sheet_order=sheet_order, row=row, row_id=row_id)


def _safe_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            safe(key)
            _safe_keys(item)
    elif isinstance(value, list):
        for item in value:
            _safe_keys(item)


def _row(r, observation, prior, decision, now, max_age):
    t, p = BY_ID[r["template_id"]], r["inputs"]
    out = dict(row_id=r["row_id"], decision=decision, commands=[], findings=[], dependencies=[],
               live_validation="not_live_validated", consistency="not_evaluated", impact="unknown",
               deployment_ready=False, execution_authorized=False, no_op=False)
    if t.family == "All":
        out["commands"] = p["commands"]  # literal text, including whitespace and newlines
        out["findings"] = ["MANUAL_EFFECTS_UNKNOWN"]
        return out
    findings, dependencies = out["findings"], out["dependencies"]
    warning_codes = set()
    unrelated_vlan_codes = {"TAGGED_VLAN_NOT_IN_MEMBERSHIP", "PVID_NOT_IN_MEMBERSHIP",
                            "INTERFACE_VLAN_NOT_IN_DATABASE", "ALLOWED_VLAN_NOT_IN_DATABASE"}
    def unrelated(items):
        return (t.function == "Interface Description" and bool(items)
                and all(i.get("code") in unrelated_vlan_codes for i in items))
    def retain_warning(items):
        for item in items:
            detail = "EXISTING_VLAN_WARNING: " + canonical(item)
            findings.append(detail)
            warning_codes.add(detail)
    obs = observation or {}
    ident = obs.get("identity", {})
    platform = FAMILIES[t.family][0]
    key = lambda n: canonical_interface_name(platform, n)
    valid = obs.get("status") == "live_read_only"
    if not valid:
        findings.append("EVIDENCE_UNAVAILABLE")
    else:
        out["live_validation"] = "live_read_only"
        expected_family = "C3850" if t.family == "C3850X" else t.family
        if (ident.get("management_ip") != p["management_ip"] or ident.get("platform") != platform
                or ident.get("device_family") != expected_family
                or (FAMILIES[t.family][1] and ident.get("capability_profile") != FAMILIES[t.family][1])):
            findings.append("IDENTITY_OR_CAPABILITY_MISMATCH")
        try:
            observed = datetime.fromisoformat(obs["observed_at"])
            age = (now - observed).total_seconds()
            if not 0 <= age <= max_age:
                findings.append("STALE_EVIDENCE")
        except (KeyError, TypeError, ValueError):
            findings.append("EVIDENCE_TIME_UNAVAILABLE")
        if not obs.get("evidence"):
            findings.append("CONFIGURATION_EVIDENCE_UNAVAILABLE")
    actual = [i for i in obs.get("interfaces", []) if key(i["port_name"]) == key(p.get("interface", ""))]
    declarations = [n for n in obs.get("facts", [])
                    if n["kind"] in {"interface", "l2_interface"}
                    and key(n["value"]) == key(p.get("interface", ""))]
    # Configuration declarations prove existence; service references never do.
    if not actual and len(declarations) == 1:
        descriptions = [n["value"] for n in declarations[0]["children"] if n["kind"] == "description"]
        actual = [dict(port_description=descriptions[-1] if descriptions else "")]
    existing = next((i for i in obs.get("vlans", []) if key(i["interface_name"]) == key(p.get("interface", ""))), None)
    if "interface" in p and len(actual) != 1:
        findings.append("INTERFACE_ABSENT_OR_AMBIGUOUS")
    audit = [i for i in obs.get("audit", []) if key(i["config_interface_name"]) == key(p.get("interface", ""))]
    if t.family == "EdgeSwitch" and existing and len(audit) == 1:
        existing = {**existing, "referenced_vlans": audit[0].get("configured_membership_vlans", []),
                    "tagged_vlans": audit[0].get("configured_tagged_vlans", [])}
    for item in audit:
        if key(item.get("configuration_owner", "")) != key(p["interface"]):
            findings.append("OWNERSHIP_REQUIRES_REVIEW")
        defects = item.get("configuration_findings", [])
        if unrelated(defects) and not item.get("review"):
            retain_warning(defects)
        elif defects or item.get("review"):
            findings.append("OBSERVED_CONSISTENCY_CONFLICT")
        if t.family == "ASR920" and any(m.get("global_bridge_domain") for m in item.get("numeric_mappings", [])):
            findings.append("ASR920_GLOBAL_BINDING_CONFLICT")
    for method in obs.get("methodologies", []):
        if key(method.get("config_interface_name", "")) == key(p.get("interface", "")) and method.get("review_needed"):
            if (unrelated(method.get("configuration_findings", []))
                    and method.get("subtype") in {"access", "trunk", "hybrid", "no_membership"}):
                retain_warning(method["configuration_findings"])
            else:
                findings.append("UNRESOLVED_CONFIGURATION")
    if obs.get("problems"):
        if unrelated(obs["problems"]):
            retain_warning(obs["problems"])
        else:
            findings.append("DEVICE_CONSISTENCY_CONFLICT")
    database = {int(o["object_id"]): o.get("name", "") for o in obs.get("objects", [])
                if o["object_type"] == "vlan" and str(o["object_id"]).isdigit()}
    needed = set()
    if t.function == "Access Port":
        needed.add(p["vlan_id"])
    elif t.function in {"Trunk Port", "VLAN Port"} and p.get("action") != "Remove":
        needed.update(p.get("vlans", []))
        needed.update(p[k] for k in ("native_vlan", "pvid") if k in p)
    elif t.family == "ME3600X" and t.function == "EVC":
        needed.add(p["bridge_domain"])
    if t.function == "VLAN Port" and "pvid" in p:
        needed.add(p["pvid"])
    for vid in sorted(needed - database.keys()):
        candidates = [(q, result) for q, result in prior if BY_ID[q["template_id"]].function == "VLAN Database"
                      and q["inputs"]["vlan_id"] == vid]
        if candidates:
            q, result = candidates[-1]
            dependencies.append(q["row_id"])
            if result["decision"] != "Approve" or not result["deployment_ready"]:
                findings.append("DEPENDENCY_NOT_APPROVED")
        else:
            findings.append("GLOBAL_VLAN_REQUIRED")
    if t.function == "Subinterface VSI" and not any(o["object_type"] == "vsi" and o["object_id"] == p["vsi"] for o in obs.get("objects", [])):
        findings.append("EXISTING_VSI_REQUIRED")
    if t.function == "VLAN Database":
        if database.get(p["vlan_id"]) == p["name"]:
            out["no_op"] = True
        elif p["vlan_id"] in database:
            findings.append("VLAN_RENAME_IMPACT")
    elif t.function == "Interface Description" and actual and actual[0]["port_description"] == p["description"]:
        out["no_op"] = True
    elif t.function == "Access Port" and existing:
        out["no_op"] = (existing["mode"] == "access" and existing["access_vlan"] == p["vlan_id"]
                        and (not p.get("description") or existing["description"] == p["description"]))
    elif t.function == "Trunk Port" and existing and existing.get("mode") == "trunk":
        allowed = existing.get("allowed_vlans")
        if isinstance(allowed, list):
            current, wanted = set(allowed), set(p["vlans"])
            same = wanted <= current if p["action"] == "Add" else not wanted & current if p["action"] == "Remove" else wanted == current
            out["no_op"] = same and ("native_vlan" not in p or existing.get("native_vlan") == p["native_vlan"]) and (not p.get("description") or existing.get("description") == p["description"])
    elif t.function == "VLAN Port" and existing:
        current, wanted = set(existing.get("referenced_vlans", [])), set(p.get("vlans", []))
        tagged = set(existing.get("tagged_vlans", []))
        if p.get("action") == "Remove":
            same = not wanted & (current | tagged)
        elif p.get("mode", "Tagged") == "Access":
            same = wanted <= current and not wanted & tagged and existing.get("pvid") == p["vlans"][0]
        else:
            same = wanted <= tagged if p.get("action") == "Add" else wanted == tagged if p.get("action") == "Replace" else True
            if p.get("replace_untagged") == "Yes":
                same &= current <= wanted | {p.get("pvid")}
        out["no_op"] = bool(same and ("pvid" not in p or (existing.get("pvid") == p["pvid"] and p["pvid"] in current)) and (not p.get("description") or existing.get("description") == p["description"]))
    elif t.function in {"EVC", "L2VPN", "Subinterface VSI"}:
        out["no_op"], conflicts = (assess_huawei if t.family == "NE05E" else assess_cisco)(t, p, obs)
        findings.extend(conflicts)
    if t.function in {"Access Port", "Trunk Port", "VLAN Port", "EVC", "L2VPN", "Subinterface VSI"} and not out["no_op"]:
        findings.append("SERVICE_IMPACT_REVIEW")
    if t.function == "VLAN Port" and existing is None:
        findings.append("MEMBERSHIP_STATE_UNKNOWN")
    if t.function == "Trunk Port" and p["action"] != "Replace" and existing is None:
        findings.append("MEMBERSHIP_STATE_UNKNOWN")
    if t.function == "VLAN Port" and p.get("mode") == "Access" and existing and p["vlans"][0] in existing.get("tagged_vlans", []):
        findings.append("ACCESS_TAGGING_CONFLICT")
    if t.function == "VLAN Port" and existing and p.get("action") == "Remove" and existing.get("pvid") in p["vlans"]:
        findings.append("PVID_REMOVAL_REQUIRES_REVIEW")
    if t.function == "VLAN Port" and existing:
        if p.get("mode") == "Access" and (existing.get("tagged_vlans") or existing.get("pvid") != p["vlans"][0]):
            findings.append("ACCESS_CONVERSION_IMPACT")
        final_pvid = p.get("pvid", p["vlans"][0] if p.get("mode") == "Access" else existing.get("pvid"))
        final_tagged = set(existing.get("tagged_vlans", []))
        requested = set(p.get("vlans", []))
        if p.get("action") == "Remove":
            final_tagged -= requested
        elif p.get("mode", "Tagged") == "Tagged":
            final_tagged = requested if p.get("action") == "Replace" else final_tagged | requested
        if final_pvid in final_tagged:
            findings.append("PVID_TAGGING_CONFLICT")
        if p.get("replace_untagged") == "Yes":
            findings.append("UNTAGGED_REPLACEMENT_IMPACT")
    if t.family == "NCS540" and t.function == "Interface Description":
        if len(declarations) != 1:
            findings.append("INTERFACE_DECLARATION_ABSENT_OR_AMBIGUOUS")
        else:
            existing = {**(existing or {}), "l2transport": declarations[0]["kind"] == "l2_interface"}
    renderer = huawei if t.family == "NE05E" else edge if t.family == "EdgeSwitch" else cisco
    out["commands"] = [] if out["no_op"] else renderer(t, p, existing)
    out["findings"] = sorted(set(findings))
    warnings = {"VLAN_RENAME_IMPACT", "SERVICE_IMPACT_REVIEW", "ACCESS_CONVERSION_IMPACT", "UNTAGGED_REPLACEMENT_IMPACT"}
    blockers = set(findings) - warnings - warning_codes
    out.update(consistency="unresolved" if blockers else "consistent", impact="none" if out["no_op"] else "review_required",
               deployment_ready=not blockers and decision == "Approve")
    return out


def _build(requests, observations, decisions, now, max_age):
    require(type(requests) is list and 0 < len(requests) <= MAX_ROWS, "invalid row count")
    require(type(observations) is dict and type(decisions) is dict, "invalid planning inputs")
    require(safe_data(observations, _safe_source) == observations, "unsafe observation content")
    _safe_keys(observations)
    live_ips = {r["inputs"]["management_ip"] for r in requests if BY_ID.get(r["template_id"]) and BY_ID[r["template_id"]].family != "All"}
    require(set(observations) <= live_ips, "unexpected observation target")
    for obs in observations.values():
        require(type(obs) is dict, "invalid observation")
        if obs.get("status") == "live_read_only":
            keys(obs, "identity observed_at interfaces vlans objects facts evidence audit problems methodologies status")
            keys(obs["identity"], IDENTITY_FIELDS)
            platform = obs["identity"]["platform"]
            require(platform in {v[0] for v in FAMILIES.values()}, "invalid observation platform")
            require(safe_data(obs, lambda text: _safe_source(text, platform)) == obs, "unsafe vendor observation content")
        else:
            keys(obs, "status")
            require(obs["status"] == "evidence_unavailable", "invalid observation status")
    require(type(max_age) is int and 1 <= max_age <= 86400, "invalid evidence age")
    rows, ids, positions = [], set(), set()
    for r in requests:
        keys(r, "template_id inputs source_inputs sheet_order row row_id")
        checked = request(**r)
        require(checked == r, "noncanonical request")
        require(r["row_id"] not in ids and (r["sheet_order"], r["row"]) not in positions, "duplicate row identity or position")
        ids.add(r["row_id"])
        positions.add((r["sheet_order"], r["row"]))
    require(set(decisions) <= ids and all(v in DECISIONS for v in decisions.values()), "invalid review decisions")
    ordered = sorted(requests, key=lambda r: (r["sheet_order"], r["row"]))
    require(ordered == requests, "requests not in workbook order")
    prior = {}
    for r in ordered:
        ip = r["inputs"]["management_ip"]
        previous = prior.setdefault(ip, [])
        result = _row(r, observations.get(ip), previous, decisions.get(r["row_id"], "Pending"), now, max_age)
        previous.append((r, result))
        rows.append(result)
    # Detect overlaps independently of decisions; never silently choose a winner.
    for group in prior.values():
        for index, (r, result) in enumerate(group):
            t, p = BY_ID[r["template_id"]], r["inputs"]
            for q, other in group[:index]:
                u, v = BY_ID[q["template_id"]], q["inputs"]
                platform = p.get("platform", FAMILIES.get(t.family, ("",))[0])
                same_interface = "interface" in p and "interface" in v and canonical_interface_name(platform, p["interface"]) == canonical_interface_name(platform, v["interface"])
                same_vlan = t.function == u.function == "VLAN Database" and p["vlan_id"] == v["vlan_id"]
                same_domain = "bridge_domain" in p and "bridge_domain" in v and p["bridge_domain"] == v["bridge_domain"] and p.get("bridge_group") == v.get("bridge_group")
                if same_interface or same_vlan or same_domain or t.family == "All" or u.family == "All":
                    for item in (result, other):
                        item["findings"] = sorted(set(item["findings"]) | {"ORDERED_RESOURCE_OVERLAP"})
                        item.update(deployment_ready=False, consistency="unresolved" if item["live_validation"] != "not_live_validated" else "not_evaluated")
    # A later overlap can invalidate an earlier prerequisite.
    by_id = {r["row_id"]: r for r in rows}
    for result in rows:
        if any(not by_id[d]["deployment_ready"] for d in result["dependencies"]):
            result["findings"] = sorted(set(result["findings"]) | {"DEPENDENCY_NOT_APPROVED"})
            result.update(deployment_ready=False, consistency="unresolved")
    identities = {}
    for ip, obs in observations.items():
        for field in ("inventory_id", "serial_number", "hostname"):
            value = obs.get("identity", {}).get(field)
            if value:
                identities.setdefault((field, value), set()).add(ip)
    collisions = set().union(*(ips for ips in identities.values() if len(ips) > 1))
    for r, result in zip(ordered, rows):
        if r["inputs"]["management_ip"] in collisions:
            result["findings"] = sorted(set(result["findings"]) | {"TARGET_IDENTITY_COLLISION"})
            result.update(deployment_ready=False, consistency="unresolved")
    return rows


@dataclass(frozen=True)
class BulkPlan:
    content: str

    def __post_init__(self):
        require(isinstance(self.content, str) and len(self.content.encode()) <= MAX_CONTENT, "plan size limit exceeded")
        d = decode(self.content)
        keys(d, "schema_version catalogue_version source layout input_errors evaluated_at max_evidence_age requests observations decisions results execution_authorized")
        require(d["schema_version"] == 2 and d["catalogue_version"] == VERSION and d["execution_authorized"] is False, "invalid v2 contract")
        safe(d["source"])
        require(type(d["layout"]) is list and len(d["layout"]) == len(BY_SHEET) + 1
                and set(d["layout"]) == {"Introduction", *BY_SHEET}, "invalid worksheet layout")
        require(type(d["input_errors"]) is list and len(d["input_errors"]) <= MAX_ROWS, "invalid input errors")
        for error in d["input_errors"]:
            keys(error, "sheet row reason")
            require(error["sheet"] in BY_SHEET and type(error["row"]) is int and error["row"] >= 3
                    and error["reason"] == "INVALID_INPUT_ROW", "invalid input error")
        now = datetime.fromisoformat(d["evaluated_at"])
        timestamp(now)
        require(d["results"] == _build(d["requests"], d["observations"], d["decisions"], now, d["max_evidence_age"]), "tampered planning result")
        object.__setattr__(self, "content", canonical(d))

    @property
    def digest(self):
        return hashlib.sha256(self.content.encode()).hexdigest()

    def to_dict(self):
        return decode(self.content)


def plan(requests, observations=None, *, decisions=None, source="api", now=None, max_evidence_age=3600,
         layout=None, input_errors=None):
    now = now or datetime.now(timezone.utc)
    layout = layout or getattr(requests, "layout", ["Introduction", *BY_SHEET])
    input_errors = input_errors if input_errors is not None else getattr(requests, "errors", [])
    requests = sorted(requests, key=lambda r: (r["sheet_order"], r["row"]))
    # Manual evidence is deliberately excluded, even in mixed runs.
    live_ips = {r["inputs"]["management_ip"] for r in requests if BY_ID[r["template_id"]].family != "All"}
    observations = {k: v for k, v in (observations or {}).items() if k in live_ips}
    decisions = {**{r["row_id"]: "Pending" for r in requests}, **(decisions or {})}
    return BulkPlan(canonical(dict(schema_version=2, catalogue_version=VERSION, source=source, layout=layout, input_errors=input_errors,
        evaluated_at=timestamp(now), max_evidence_age=max_evidence_age, requests=requests,
        observations=observations, decisions=decisions,
        results=_build(requests, observations, decisions, now, max_evidence_age), execution_authorized=False)))


@dataclass(frozen=True)
class DecisionEvaluation:
    """Unauthenticated decision intent bound to an unchanged source plan."""
    source_digest: str
    content: str

    @property
    def digest(self):
        """Matching source digest only; decision intent is not signed content."""
        return self.source_digest

    def to_dict(self):
        return decode(self.content)


def evaluate_decisions(original, decisions, *, expected_digest, now=None):
    original = BulkPlan(original.content)
    require(original.digest == expected_digest, "decision source digest mismatch")
    d = original.to_dict()
    now = now or datetime.now(timezone.utc)
    intent = {**d["decisions"], **decisions}
    results = _build(d["requests"], d["observations"], intent, now, d["max_evidence_age"])
    return DecisionEvaluation(original.digest, canonical(dict(
        source_digest=original.digest, decisions=intent, results=results,
        evaluated_at=timestamp(now), authenticated=False, execution_authorized=False)))


def save(plan, path):
    plan = BulkPlan(plan.content)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(canonical(dict(digest=plan.digest, plan=plan.to_dict())) + "\n")


def load(path):
    d = decode(Path(path).read_text(encoding="utf-8"))
    keys(d, "digest plan")
    result = BulkPlan(canonical(d["plan"]))
    require(result.digest == d["digest"], "plan digest mismatch")
    return result
