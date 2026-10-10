"""Two-stage offline input jobs; no device sessions, execution or transport imports."""

from collections import Counter, defaultdict
import hashlib
import ipaddress
from pathlib import Path

from . import workbooks
from .catalogue import VERSION, candidates, number
from .guided_schema import build, digest, operation, sha, validate_identity
from .plans import ChangePlan, PlanError, canonical, decode, identity, keys, label, load_plan, require, safe_text, save_plan

REQUEST = ["row_id", "device", "interface", "action", "manual_cli_ref"]
GUIDED = REQUEST + ["inventory_id", "template_id", "template_version", "order", "depends_on", "decision", "reason"]
PARAMETERS = ["row_id", "template_id", "name", "type", "required", "default", "example", "value"]
MANUAL = ["reference", "order", "command"]


def failure_reason(exc):
    if isinstance(exc, PlanError):
        try:
            safe_text(str(exc))
            return str(exc)
        except PlanError:
            pass
    return "invalid or sensitive input"


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(canonical(value) + "\n")


def resolve(device, contexts):
    safe_text(device)
    matches = [c for c in contexts if device.casefold() in
               (c.device_id.casefold(), c.hostname.casefold(), c.management_ip.casefold())]
    require(len(matches) == 1, "unresolved or ambiguous inventory identity")
    context = matches[0]
    require(context.collection_status == "success", "inventory observation unavailable")
    def addresses(item):
        try:
            return {str(ipaddress.ip_address(ip)) for ip in (item.management_ip, *item.observed_management_ips)}
        except ValueError:
            raise PlanError("invalid inventory address") from None
    context_addresses = addresses(context)
    for other in contexts:
        if other is context:
            continue
        require(not (other.device_id == context.device_id or other.hostname.casefold() == context.hostname.casefold() or
                     context_addresses & addresses(other) or
                     context.serial_number and context.serial_number.casefold() == other.serial_number.casefold()),
                "ambiguous inventory identity")
    ident = identity(context)
    validate_identity(ident)
    flags = sorted(context.capability_flags)
    for flag in flags:
        label(flag)
    snapshot = dict(identity=ident, flags=flags, observed_at=context.last_successful_collection.isoformat(),
                    software_version=context.software_version)
    return ident, flags, digest(snapshot)


def fields(row, allowed):
    require(not row["_formula"], "formula or error cells forbidden")
    require(set(row) - {"_line", "_formula"} <= set(allowed), "unknown input columns")


def prepare(request_path, contexts, output):
    contexts = tuple(contexts)
    tables = workbooks.read(request_path)
    require("Requests" in tables and set(tables) <= {"Requests", "Manual"}, "invalid request sheets")
    require(bool(tables["Requests"]), "request workbook is empty")
    output = Path(output)
    require(not output.exists() and not output.with_suffix(".json").exists(), "output already exists")
    counts = Counter(str(r.get("row_id", "")) for r in tables["Requests"] if r.get("row_id"))
    records, guided, params, choices = [], [], [], []
    manual, manual_errors = [], set()
    from .guided_schema import manual_lines
    for row in tables.get("Manual", []):
        reference = row.get("reference", "")
        try:
            label(reference)
            fields(row, MANUAL)
            order = number(row.get("order"), 100000)
            manual_lines([row.get("command")])
            manual.append([reference, order, row["command"]])
        except (PlanError, TypeError):
            # Never persist raw failed commands.
            manual_errors.add(reference if isinstance(reference, str) else "")
    for index, row in enumerate(tables["Requests"], 1):
        generated_id = f"row-{index:06d}"
        while generated_id in counts:
            generated_id += "-auto"
        record = dict(row_id=generated_id, source_row=row["_line"], device="", interface="", action="",
                      manual_cli_ref="", inventory_id="", identity=None, flags=[], snapshot_digest="", error="")
        try:
            fields(row, REQUEST + ["inventory_id"])
            supplied_id = row.get("row_id", "")
            if supplied_id:
                label(supplied_id)
                require(counts[supplied_id] == 1, "duplicate source row ID")
                record["row_id"] = supplied_id
            device = row.get("device") or row.get("inventory_id", "")
            safe_text(device)
            if row.get("device") and row.get("inventory_id"):
                require(resolve(row["device"], contexts)[0] == resolve(row["inventory_id"], contexts)[0],
                        "conflicting device identifiers")
            record["device"] = device
            ident, flags, snapshot = resolve(device, contexts)
            record.update(inventory_id=ident["inventory_id"], identity=ident, flags=flags, snapshot_digest=snapshot)
            for key in ("interface", "action"):
                safe_text(row.get(key, ""))
                record[key] = row[key]
            ref = row.get("manual_cli_ref", "")
            if ref:
                label(ref)
                record["manual_cli_ref"] = ref
            require(ref not in manual_errors, "manual input rejected")
            if record["action"] != "manual CLI":
                require(not ref, "manual CLI requires a separate ordered request row")
                available = candidates(ident, flags, record["action"])
                require(bool(available), "no compatible approved template")
            else:
                available = ()
                if not record["manual_cli_ref"]:
                    record["manual_cli_ref"] = "manual-" + digest(record["row_id"])[:16]
        except (PlanError, TypeError) as exc:
            record["error"] = failure_reason(exc)
            available = ()
        records.append(record)
        chosen = available[0] if len(available) == 1 else None
        reason = record["error"] or ("engineer template selection required" if len(available) > 1 else "")
        guided.append([record[k] for k in REQUEST] + [record["inventory_id"],
                      chosen.template_id if chosen else "", chosen.version if chosen else "", index, "", "include", reason])
        for template in available:
            choices.append([record["row_id"], template.template_id, template.version, template.method, template.action])
            for p in template.parameters:
                params.append([record["row_id"], template.template_id, p.name, p.kind, p.required, p.default, p.example, p.default])
    # Generated IDs must not collide with supplied IDs.
    collisions = Counter(r["row_id"] for r in records)
    require(all(count == 1 for count in collisions.values()), "generated and supplied row IDs collide")
    used_refs = {r["manual_cli_ref"] for r in records if r["manual_cli_ref"]}
    require(all(row[0] in used_refs for row in manual) and manual_errors <= used_refs,
            "unreferenced manual input; correct request workbook")
    for reference in sorted(used_refs - {row[0] for row in manual} - manual_errors):
        manual.append([reference, 1, ""])
    content = dict(schema_version=1, catalogue_version=VERSION, request_digest=file_digest(request_path), rows=records)
    envelope = dict(digest=digest(content), prepared=content)
    workbooks.write(output, {
        "Instructions": (["step", "instruction"], [
            [1, "Retain this workbook beside its generated JSON. Do not change row identity or source fields."],
            [2, "Choose a template from Choices when ambiguous. Fill Parameters value cells for the chosen template."],
            [3, "Set unique per-device order and comma-separated predecessor row IDs. Separate manual CLI into its own row."],
            [4, "Use decision include, skip or reject. All input outcomes remain in the manifest."],
            [5, "Manual commands are literal advanced review evidence. No workbook or local approval authorizes execution."]]),
        "Metadata": (["key", "value"], [["prepared_digest", envelope["digest"]]]),
        "Requests": (GUIDED, guided), "Parameters": (PARAMETERS, params),
        "Choices": (["row_id", "template_id", "version", "method", "action"], choices),
        "Manual": (MANUAL, manual),
    })
    save_json(output.with_suffix(".json"), envelope)
    return envelope


def plan(completed, contexts, output, batch_id):
    label(batch_id)
    contexts = tuple(contexts)
    output = Path(output)
    require(not output.exists(), "batch output already exists")
    envelope = decode(Path(completed).with_suffix(".json").read_text(encoding="utf-8"))
    keys(envelope, "digest prepared")
    prepared = envelope["prepared"]
    keys(prepared, "schema_version catalogue_version request_digest rows")
    require(prepared["schema_version"] == 1 and prepared["catalogue_version"] == VERSION and
            digest(prepared) == envelope["digest"], "prepared artifact changed or unsupported")
    sha(prepared["request_digest"])
    require(type(prepared["rows"]) is list and 0 < len(prepared["rows"]) <= 20000, "invalid prepared rows")
    for original in prepared["rows"]:
        keys(original, "row_id source_row device interface action manual_cli_ref inventory_id identity flags snapshot_digest error")
        label(original["row_id"])
        require(type(original["source_row"]) is int and original["source_row"] >= 2, "invalid source row")
        for key in ("device", "interface", "action", "manual_cli_ref", "inventory_id", "error"):
            require(type(original[key]) is str, "invalid prepared field")
            if original[key]:
                safe_text(original[key])
    tables = workbooks.read(completed)
    require(set(tables) == {"Instructions", "Metadata", "Requests", "Parameters", "Choices", "Manual"},
            "guided workbook sheets changed")
    require(len(tables["Metadata"]) == 1 and tables["Metadata"][0].get("key") == "prepared_digest" and
            tables["Metadata"][0].get("value") == envelope["digest"], "prepared workbook binding mismatch")
    requests = defaultdict(list)
    for row in tables["Requests"]:
        requests[str(row.get("row_id", ""))].append(row)
    originals = {r["row_id"]: r for r in prepared["rows"]}
    require(len(originals) == len(prepared["rows"]), "duplicate prepared row ID")
    # Unexpected rows are visible global failures, and block every generated plan.
    extras = [("Requests", r["_line"]) for r in tables["Requests"] if str(r.get("row_id", "")) not in originals]
    extras += [("Parameters", p["_line"]) for p in tables["Parameters"] if str(p.get("row_id", "")) not in originals]
    refs = {r["manual_cli_ref"] for r in originals.values() if r["manual_cli_ref"]}
    extras += [("Manual", r["_line"]) for r in tables["Manual"] if r.get("reference") not in refs]
    results, operations, identities, sources, flags_by_device = [], defaultdict(list), {}, {}, {}
    errors = defaultdict(list)
    for row_id, original in originals.items():
        device_id = original["inventory_id"]
        result = dict(row_id=row_id, source_row=original["source_row"], inventory_id=device_id,
                      device=original["device"], interface=original["interface"], action=original["action"],
                      status="blocked", reason="", plan="", digest="")
        try:
            require(not original["error"], original["error"] or "rejected prepared input")
            require(len(requests[row_id]) == 1, "guided row missing or duplicated")
            row = requests[row_id][0]
            fields(row, GUIDED)
            require(all(row.get(k, "") == original[k] for k in REQUEST + ["inventory_id"]),
                    "prepared row identity or intent changed")
            require(row.get("decision") in ("include", "skip", "reject"), "invalid row decision")
            if row["decision"] != "include":
                result.update(status="skipped" if row["decision"] == "skip" else "rejected", reason="explicit engineer exclusion")
                errors[device_id].append(row_id)
                results.append(result)
                continue
            ident, flags, snapshot = resolve(device_id, contexts)
            require(ident == original["identity"] and snapshot == original["snapshot_digest"] and flags == original["flags"],
                    "inventory snapshot changed; prepare again")
            supplied = {}
            permitted = {(t.template_id, p.name) for t in candidates(ident, flags, row["action"]) for p in t.parameters}
            seen = set()
            for p in tables["Parameters"]:
                if p.get("row_id") != row_id:
                    continue
                fields(p, PARAMETERS)
                key = (p.get("template_id"), p.get("name"))
                require(key in permitted and key not in seen, "unknown or duplicate parameter row")
                seen.add(key)
                if p["template_id"] == row.get("template_id"):
                    supplied[p["name"]] = p.get("value", "")
                else:
                    require(p.get("value", "") == "", "values supplied for an unselected template")
            commands = []
            if row["action"] == "manual CLI":
                entries = [r for r in tables["Manual"] if r.get("reference") == row.get("manual_cli_ref")]
                orders = set()
                for entry in entries:
                    fields(entry, MANUAL)
                    order = number(entry.get("order"), 100000)
                    require(order not in orders, "duplicate manual line order")
                    orders.add(order)
                    commands.append((order, entry.get("command")))
            op = operation(dict(row_id=row_id, source_row=original["source_row"], interface=row["interface"],
                                action=row["action"], template_id=row.get("template_id", ""),
                                template_version=str(row.get("template_version", "")), order=number(row.get("order"), 100000),
                                depends_on=[d.strip() for d in str(row.get("depends_on", "")).split(",") if d.strip()],
                                parameters=supplied, manual_cli=[c for _, c in sorted(commands)]), ident, flags)
            require(len(operations[device_id]) < 1000, "per-device operation limit exceeded")
            operations[device_id].append(op)
            identities[device_id], flags_by_device[device_id] = ident, flags
            sources[device_id] = dict(kind="guided_workbook", version="1", catalogue_version=VERSION,
                                      request_digest=prepared["request_digest"], prepared_digest=envelope["digest"],
                                      completed_digest=file_digest(completed), snapshot_digest=snapshot)
            result.update(status="included", reason="")
        except (PlanError, TypeError, ValueError, KeyError) as exc:
            result["reason"] = failure_reason(exc)
            errors[device_id].append(row_id)
        results.append(result)
    extra_ids = []
    for sheet, line in extras:
        extra_id = f"unmapped-{sheet}-{line}"
        while extra_id in originals:
            extra_id += "-extra"
        extra_ids.append(extra_id)
        results.append(dict(row_id=extra_id, source_row=line, inventory_id="", status="blocked",
                            device="", interface="", action="", reason="unexpected " + sheet + " row", plan="", digest=""))
    output.mkdir(parents=True)
    members, plans = [], []
    for index, device_id in enumerate(sorted(operations), 1):
        failures = errors[device_id] + extra_ids
        item = ChangePlan(canonical(build(f"plan-{digest(batch_id)[:16]}-{index}", batch_id, sources[device_id], identities[device_id],
                                         flags_by_device[device_id], operations[device_id], failures)))
        filename = f"plan-{index:04d}.json"
        save_plan(item, output / filename)
        plans.append(item)
        members.append(dict(inventory_id=device_id, path=filename, digest=item.digest))
        for row in results:
            if row["inventory_id"] == device_id:
                row.update(plan=filename, digest=item.digest)
                if row["status"] == "included":
                    row["status"] = item.to_dict()["status"]
    manifest = dict(schema_version=2, batch_id=batch_id, request_digest=prepared["request_digest"],
                    prepared_digest=envelope["digest"], completed_digest=file_digest(completed),
                    members=members, results=results, execution_authorized=False)
    save_json(output / "manifest.json", dict(digest=digest(manifest), manifest=manifest))
    preview(output / f"configuration_preview_{batch_id}.xlsx", manifest, plans)
    return manifest


def preview(path, manifest, plans):
    rows, commands, issues, checks = [], [], [], []
    for plan in plans:
        p = plan.to_dict()
        for op in p["operations"]:
            rows.append([p["identity"]["inventory_id"], op["row_id"], op["interface"], op["order"],
                         op["action"], op["template_id"], op["template_version"], op["method"], p["status"], plan.digest])
            for n, command in enumerate(op["commands"], 1):
                commands.append([p["identity"]["inventory_id"], op["row_id"], op["order"], n,
                                 "manual" if op["action"] == "manual CLI" else "template", command])
            checks.append([op["row_id"], "\n".join(op["preconditions"]), "\n".join(op["verification"])])
        for finding in p["findings"]:
            issues.append([p["identity"]["inventory_id"], ",".join(finding["rows"]), finding["level"], finding["code"]])
        for warning in p["warnings"]:
            issues.append([p["identity"]["inventory_id"], "", "warning", warning])
    headers = ["row_id", "source_row", "device", "inventory_id", "interface", "action", "status", "reason", "plan", "digest"]
    workbooks.write(path, {
        "Summary": (["item", "value"], [["Batch", manifest["batch_id"]], ["Manifest digest", digest(manifest)],
                    ["Input outcomes", len(manifest["results"])], ["Device plans", len(plans)],
                    ["Execution", "Forbidden. Offline review only. Advanced CLI needs separate authenticated elevated approval."]]),
        "Inputs": (headers, [[r[k] for k in headers] for r in manifest["results"]]),
        "Operations": (["device", "row_id", "interface", "order", "action", "template", "version", "method", "status", "digest"], rows),
        "CLI Preview": (["device", "row_id", "operation_order", "line", "source", "command"], commands),
        "Findings": (["device", "rows", "level", "reason"], issues),
        "Checks": (["row_id", "preconditions", "verification"], checks),
    })


def load_manifest(path):
    path = Path(path)
    envelope = decode(path.read_text(encoding="utf-8"))
    keys(envelope, "digest manifest")
    data = envelope["manifest"]
    keys(data, "schema_version batch_id request_digest prepared_digest completed_digest members results execution_authorized")
    require(data["schema_version"] == 2 and data["execution_authorized"] is False and digest(data) == envelope["digest"],
            "invalid batch manifest")
    label(data["batch_id"])
    for key in ("request_digest", "prepared_digest", "completed_digest"):
        sha(data[key])
    require(type(data["members"]) is list and type(data["results"]) is list, "invalid manifest collections")
    seen = set()
    devices = set()
    contents = []
    for member in data["members"]:
        keys(member, "inventory_id path digest")
        label(member["path"])
        require(member["path"] not in seen and member["path"].endswith(".json"), "duplicate batch member")
        require(member["inventory_id"] not in devices, "duplicate batch device")
        seen.add(member["path"])
        devices.add(member["inventory_id"])
        plan = load_plan(path.parent / member["path"])
        content = plan.to_dict()
        require(content["schema_version"] == 2 and content["batch_id"] == data["batch_id"] and
                content["identity"]["inventory_id"] == member["inventory_id"] and plan.digest == member["digest"] and
                all(content["source"][k] == data[k] for k in ("request_digest", "prepared_digest", "completed_digest")),
                "batch membership mismatch")
        contents.append((member, content))
    result_ids = set()
    for row in data["results"]:
        keys(row, "row_id source_row device inventory_id interface action status reason plan digest")
        label(row["row_id"])
        require(row["row_id"] not in result_ids, "duplicate input outcome")
        result_ids.add(row["row_id"])
        require(type(row["source_row"]) is int and row["source_row"] >= 2, "invalid result provenance")
        require(row["status"] in ("blocked", "rejected", "skipped", "review_required", "offline_validated"),
                "invalid input outcome")
        if row["inventory_id"]:
            label(row["inventory_id"])
        for field in ("device", "interface", "action"):
            require(type(row[field]) is str, "invalid input identity")
            if row[field]:
                safe_text(row[field])
        if row["reason"]:
            safe_text(row["reason"])
        if row["plan"]:
            require(any(m["path"] == row["plan"] and m["digest"] == row["digest"] and
                        m["inventory_id"] == row["inventory_id"] for m in data["members"]), "batch result binding mismatch")
        else:
            require(row["digest"] == "" and row["status"] in ("blocked", "rejected", "skipped"),
                    "missing plan for included outcome")
    results = {r["row_id"]: r for r in data["results"]}
    for member, content in contents:
        operation_ids = {op["row_id"] for op in content["operations"]}
        for op in content["operations"]:
            row = results.get(op["row_id"])
            require(row is not None and row["plan"] == member["path"] and row["source_row"] == op["source_row"] and
                    row["status"] == content["status"] and row["interface"] == op["interface"] and
                    row["action"] == op["action"], "operation missing from batch outcomes")
        for row_id in content["input_errors"]:
            require(row_id in results and results[row_id]["status"] in ("blocked", "rejected", "skipped") and
                    row_id not in operation_ids, "missing input failure outcome")
        bound = {r["row_id"] for r in data["results"] if r["plan"] == member["path"]}
        require(bound <= operation_ids | set(content["input_errors"]), "unaccounted batch input outcome")
    return data
