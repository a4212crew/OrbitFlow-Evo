"""Streaming engineer-review workbook; consumes structured resolution only."""

import json
from itertools import chain, islice
from pathlib import Path

from orbitflow.compliance_report import configuration_evidence, ERROR_COLUMNS
from orbitflow.excel_output import write_tables
from orbitflow.result_spool import ResultSpool


COLUMNS = ("Input Position", "Record", "Device ID", "Device IP", "Device Name", "Family",
           "Record Kind", "Config Interface", "Interface Match", "Parent Interface",
           "Configuration Owner", "Methodology", "Subtype", "Status", "Review Needed",
           "Configuration Classification", "Finding Severity", "Standard Finding", "Engineering Review Decision",
           "Mapping", "Configuration Findings", "Configuration Evidence", "Evidence Lines",
           "Configuration Facts Digest")

CELL_FRAGMENT = 30000
SHEET_ROWS = 1048576  # Includes the header; continuation sheets repeat it.


def _json_fragments(row):
    """Avoid constructing a second whole serialized record during export."""
    pending = ""
    for token in json.JSONEncoder(sort_keys=True, ensure_ascii=True).iterencode(row):
        for start in range(0, len(token), CELL_FRAGMENT):
            pending += token[start:start + CELL_FRAGMENT]
            if len(pending) >= CELL_FRAGMENT:
                yield pending[:CELL_FRAGMENT]
                pending = pending[CELL_FRAGMENT:]
    if pending:
        yield pending


def _paged_tables(tables):
    """Excel has a finite row count; never silently write beyond that limit."""
    for title, columns, rows in tables:
        rows = iter(rows)
        first = next(rows, None)
        part = 1
        while True:
            name = title if part == 1 else f"{title} {part}"
            yield name, columns, (() if first is None else chain((first,), islice(rows, SHEET_ROWS - 2)))
            first = next(rows, None)
            if first is None:
                break
            part += 1


def export_methodology_spool(spool_path, path, *, cleanup=False, allow_partial=False):
    """Recover independently without network access; keep spool by default for compliance."""
    spool = ResultSpool(spool_path)
    if spool.manifest["task"] != "vlan_compliance":
        raise ValueError("Not a VLAN compliance spool")

    def consume(run):
        def records():
            for envelope in run.records():
                payload = envelope["payload"]
                rows = payload.get("methodologies") or [dict(
                    device=dict(management_ip=envelope.get("target", "")), record_kind="target_exception",
                    status="unable_to_assess", review_needed=True,
                    configuration_findings=[dict(code=("METHODOLOGY_RESOLUTION_FAILED"
                        if payload.get("methodology_errors") else "METHODOLOGY_EVIDENCE_UNAVAILABLE"))])]
                for index, row in enumerate(rows, 1):
                    # Legacy spools have no standards assessment or durable decision.
                    row = dict(row)
                    row.setdefault("configuration_classification", "review_needed")
                    row.setdefault("finding_severity", "warning")
                    row.setdefault("standard_finding", "STANDARDS_ASSESSMENT_UNAVAILABLE")
                    row.setdefault("engineering_review_decision", "not_reviewed")
                    yield envelope["input_position"], index, row

        def values(row):
            device = row.get("device", {})
            excerpt, source, lines = configuration_evidence(dict(evidence=dict(sources=row.get("evidence", []))))
            return [device.get(k, "") for k in ("device_id", "management_ip", "hostname", "family")] + [
                row.get(k, "") for k in ("record_kind", "config_interface_name", "interface_match_status",
                                        "parent_interface", "configuration_owner")] + [
                ", ".join(row.get("methodology", [])), row.get("subtype", ""), row.get("status", ""),
                str(row.get("review_needed", True)), row["configuration_classification"], row["finding_severity"],
                row["standard_finding"], row["engineering_review_decision"], json.dumps(row.get("mapping", {}), sort_keys=True),
                ", ".join(p["code"] for p in row.get("configuration_findings", [])), excerpt, lines,
                row.get("configuration_facts_digest", "")]

        def summary():
            for position, index, row in records():
                yield [position, index] + [v if len(v) <= CELL_FRAGMENT else
                                           f"See Details / Evidence Details: Input Position {position}, Record {index}; all numbered parts"
                                           for v in values(row)]

        def details():
            for position, index, row in records():
                for part, fragment in enumerate(_json_fragments(row), 1):
                    yield [position, index, part, fragment]

        def evidence_details():
            for position, index, row in records():
                # Source order and one-based locations survive independently of
                # JSON escaping. Duplicates in finding proofs need not be copied.
                sources = {(item["source_filename"], item["line"], item["excerpt"])
                           for item in row.get("evidence", [])}
                for source, line, excerpt in sorted(sources):
                    for start in range(0, max(1, len(excerpt)), CELL_FRAGMENT):
                        yield [position, index, source, line, start // CELL_FRAGMENT + 1,
                               excerpt[start:start + CELL_FRAGMENT]]

        def errors():
            for envelope in run.records():
                for key in ("errors", "methodology_errors"):
                    for error in envelope["payload"].get(key, []):
                        yield [envelope["input_position"], error["management_ip"], error["stage"], error["error_category"]]

        write_tables(path, _paged_tables((("Methodology Resolution", COLUMNS, summary()),
                            ("Run Errors", ERROR_COLUMNS, errors()),
                            ("Details", ("Input Position", "Record", "Part", "JSON Fragment"), details()),
                            ("Evidence Details", ("Input Position", "Record", "Source Filename", "Line", "Part", "Configuration Evidence"),
                             evidence_details()))))
        return Path(path)
    return spool.consume(consume, cleanup=cleanup, allow_partial=allow_partial)
