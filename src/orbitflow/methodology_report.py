"""Streaming engineer-review workbook; consumes structured resolution only."""

import json
from pathlib import Path

from orbitflow.compliance_report import configuration_evidence, ERROR_COLUMNS
from orbitflow.excel_output import write_tables
from orbitflow.result_spool import ResultSpool


COLUMNS = ("Input Position", "Record", "Device ID", "Device IP", "Device Name", "Family",
           "Record Kind", "Interface", "Config Interface", "Interface Match", "Parent Interface",
           "Configuration Owner", "Service Instance", "Methodology", "Subtype", "Status", "Review Needed",
           "Mapping", "Configuration Findings", "Configuration Evidence", "Evidence Source", "Evidence Lines",
           "Configuration Facts Digest")


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
                    configuration_findings=[dict(code="METHODOLOGY_EVIDENCE_UNAVAILABLE")])]
                for index, row in enumerate(rows, 1):
                    yield envelope["input_position"], index, row

        def values(row):
            device = row.get("device", {})
            excerpt, source, lines = configuration_evidence(dict(evidence=dict(sources=row.get("evidence", []))))
            return [device.get(k, "") for k in ("device_id", "management_ip", "hostname", "family")] + [
                row.get(k, "") for k in ("record_kind", "interface_name", "config_interface_name", "interface_match_status",
                                        "parent_interface", "configuration_owner", "service_instance_id")] + [
                ", ".join(row.get("methodology", [])), row.get("subtype", ""), row.get("status", ""),
                str(row.get("review_needed", True)), json.dumps(row.get("mapping", {}), sort_keys=True),
                ", ".join(p["code"] for p in row.get("configuration_findings", [])), excerpt, source, lines,
                row.get("configuration_facts_digest", "")]

        def summary():
            for position, index, row in records():
                yield [position, index] + [v if len(v) <= 30000 else "See Details"
                                           for v in values(row)]

        def details():
            for position, index, row in records():
                serialized = json.dumps(row, sort_keys=True, ensure_ascii=True)
                for start in range(0, len(serialized), 30000):
                    yield [position, index, start // 30000 + 1, serialized[start:start + 30000]]

        def errors():
            for envelope in run.records():
                for error in envelope["payload"].get("errors", []):
                    yield [envelope["input_position"], error["management_ip"], error["stage"], error["error_category"]]

        write_tables(path, (("Methodology Resolution", COLUMNS, summary()),
                            ("Run Errors", ERROR_COLUMNS, errors()),
                            ("Details", ("Input Position", "Record", "Part", "JSON Fragment"), details())))
        return Path(path)
    return spool.consume(consume, cleanup=cleanup, allow_partial=allow_partial)
