"""Streaming Excel consumer of reusable JSON compliance results."""

import json
from pathlib import Path

from orbitflow.excel_output import write_tables
from orbitflow.result_spool import ResultSpool


FINDING_COLUMNS = ("Input Position", "Device IP", "Device Name", "Interface", "Policy", "Rule",
                   "Status", "Reason", "Expected", "Observed", "Missing VLANs", "Missing Objects", "Evidence")
ERROR_COLUMNS = ("Input Position", "Device IP", "Stage", "Error Category")
DETAIL_COLUMNS = ("Input Position", "Finding", "Field", "Part", "JSON Fragment")
JSON_FIELDS = ("expected", "observed", "missing_vlans", "missing_objects", "evidence")


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def export_compliance_spool(spool_path, path, *, cleanup=True, allow_partial=False):
    """Retry output without loading policy or contacting devices. Partial runs are opt-in."""
    spool = ResultSpool(spool_path)
    if spool.manifest["task"] != "vlan_compliance":
        raise ValueError("Not a VLAN compliance spool")

    def consume(run):
        def findings():
            for record in run.records():
                for index, finding in enumerate(record["payload"]["findings"], 1):
                    values = [_json(finding[field]) for field in JSON_FIELDS]
                    values = [value if len(value) <= 30000 else f"See Details: finding {index}, {field}"
                              for field, value in zip(JSON_FIELDS, values)]
                    yield [record["input_position"], finding["device"]["management_ip"],
                           finding["device"]["hostname"], finding["interface"] or "", finding["policy_id"],
                           finding["rule_id"], finding["status"], finding["reason"], *values]

        def errors():
            for record in run.records():
                for error in record["payload"]["errors"]:
                    yield [record["input_position"], error["management_ip"], error["stage"], error["error_category"]]

        def details():
            for record in run.records():
                for index, finding in enumerate(record["payload"]["findings"], 1):
                    for field in JSON_FIELDS:
                        value = _json(finding[field])
                        if len(value) > 30000:
                            for offset in range(0, len(value), 30000):
                                yield [record["input_position"], index, field, offset // 30000 + 1,
                                       value[offset:offset + 30000]]

        write_tables(path, (("Findings", FINDING_COLUMNS, findings()),
                            ("Run_Errors", ERROR_COLUMNS, errors()),
                            ("Details", DETAIL_COLUMNS, details())))
        return Path(path)

    return spool.consume(consume, cleanup=cleanup, allow_partial=allow_partial)
