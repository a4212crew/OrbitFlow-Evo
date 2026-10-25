"""Streaming Excel consumer of reusable JSON compliance results."""

import json
from pathlib import Path

from orbitflow.excel_output import write_tables
from orbitflow.logging import sanitize_text
from orbitflow.compliance.vlan import safe_data
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from orbitflow.result_spool import ResultSpool


COMMON_COLUMNS = ("Input Position", "Device IP", "Family", "Device Name", "Policy", "Rule",
                  "Status", "Reason", "Expected", "Valid VLANs", "Missing VLANs")
EVIDENCE_COLUMNS = ("Configuration Findings", "Explanation", "Recommendation",
                    "Configuration Evidence", "Evidence Source", "Evidence Lines", "Configuration Health")
INTERFACE_COLUMNS = COMMON_COLUMNS + ("Interface", "Config Interface", "Interface Match", "Type",
                    "Description", "Admin Status", "Oper Status", "Shutdown", "Trigger Applicable",
                    "Configuration Owner") + EVIDENCE_COLUMNS
DATABASE_COLUMNS = COMMON_COLUMNS + EVIDENCE_COLUMNS
ERROR_COLUMNS = ("Input Position", "Device IP", "Stage", "Error Category")
DETAIL_COLUMNS = ("Input Position", "Finding", "Field", "Part", "JSON Fragment")
INLINE_LIMIT = 30000


def _cell(value):
    """Sanitize complete values before measuring or losslessly splitting them."""
    return ILLEGAL_CHARACTERS_RE.sub("", sanitize_text(value))


JSON_FIELDS = ("expected", "observed", "missing_vlans", "missing_objects", "evidence")


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _line_ranges(lines):
    ranges = []
    for line in sorted(set(lines)):
        if ranges and line == ranges[-1][1] + 1:
            ranges[-1][1] = line
        else:
            ranges.append([line, line])
    return ",".join(str(start) if start == end else f"{start}-{end}" for start, end in ranges)


def configuration_evidence(finding):
    """Format preserved excerpts only, retaining indentation and source identity."""
    sources = {}
    for item in finding.get("evidence", {}).get("sources", []):
        source = item["source_filename"]
        sources.setdefault(source, {})[(item["line"], item["excerpt"])] = None
    snippets, references = [], []
    for source, items in sorted(sources.items()):
        snippets.append("\n".join(excerpt for _, excerpt in sorted(items)))
        references.append(_line_ranges(line for line, _ in items))
    names = sorted(sources)
    return ("\n\n".join(snippets), "\n".join(names),
            "\n".join(f"{name}: {refs}" if len(names) > 1 else refs
                      for name, refs in zip(names, references)))


def export_compliance_spool(spool_path, path, *, cleanup=True, allow_partial=False):
    """Retry output without loading policy or contacting devices. Partial runs are opt-in.

    Complete sanitized cells over 30,000 characters are split in Details by
    input position, finding index, original column name and ordered Part.
    """
    spool = ResultSpool(spool_path)
    if spool.manifest["task"] != "vlan_compliance":
        raise ValueError("Not a VLAN compliance spool")

    def consume(run):
        def findings(interface_results, *, raw=False):
            for record in run.records():
                for index, finding in enumerate(record["payload"]["findings"], 1):
                    # Interface-rule collection failures have no audited interface;
                    # their device/stage failure is already carried by Run Errors.
                    is_interface = finding.get("interface") is not None
                    is_database = "interface_types" not in finding.get("expected", {})
                    if not (is_interface if interface_results else is_database):
                        continue
                    observed = finding.get("observed") or {}
                    codes = ", ".join(p["code"] for p in observed.get("configuration_findings", []))
                    excerpt, source, lines = configuration_evidence(finding)
                    values = [record["input_position"], finding["device"]["management_ip"],
                              finding["device"].get("family", ""), finding["device"]["hostname"],
                              finding["policy_id"], finding["rule_id"], finding["status"], finding["reason"],
                              _json(finding["expected"]),
                              _json(observed.get("valid_interface_vlans", observed.get("valid_database_vlans", []))),
                              _json(finding["missing_vlans"])]
                    if interface_results:
                        values += [finding["interface"], observed.get("config_interface_name", ""),
                                   observed.get("interface_match_status", ""), observed.get("interface_type", ""),
                                   observed.get("description", ""), observed.get("admin_status", "unavailable"),
                                   observed.get("oper_status", "unavailable"), observed.get("shutdown", ""),
                                   observed.get("trigger_applicable", ""), observed.get("configuration_owner", "")]
                    values += [codes, finding.get("explanation", ""), finding.get("recommendation", ""),
                               excerpt, source, lines, finding.get("configuration_health", "unable_to_assess")]
                    columns = INTERFACE_COLUMNS if interface_results else DATABASE_COLUMNS
                    values = [_cell(value) for value in values]
                    if raw:
                        yield record["input_position"], index, columns, values
                        continue
                    yield [value if len(str(value)) <= INLINE_LIMIT else f"See Details: input {record['input_position']}, finding {index}, {column}"
                           for column, value in zip(columns, values)]

        def errors(*, raw=False):
            for record in run.records():
                for index, error in enumerate(record["payload"]["errors"], 1):
                    values = [_cell(value) for value in (record["input_position"], error["management_ip"], error["stage"], error["error_category"])]
                    if raw:
                        yield record["input_position"], f"error {index}", ERROR_COLUMNS, values
                    else:
                        yield [value if len(value) <= INLINE_LIMIT else
                               f"See Details: input {record['input_position']}, error {index}, {column}"
                               for column, value in zip(ERROR_COLUMNS, values)]

        def details():
            for record in run.records():
                for index, finding in enumerate(record["payload"]["findings"], 1):
                    for field in JSON_FIELDS:
                        value = ILLEGAL_CHARACTERS_RE.sub("", _json(safe_data(finding[field])))
                        if field in {"observed", "evidence"} or len(value) > INLINE_LIMIT:
                            for offset in range(0, len(value), INLINE_LIMIT):
                                yield [record["input_position"], index, field, offset // INLINE_LIMIT + 1,
                                       value[offset:offset + INLINE_LIMIT]]

            def raw_rows():
                yield from findings(True, raw=True)
                yield from findings(False, raw=True)
                yield from errors(raw=True)

            for position, index, columns, values in raw_rows():
                for column, value in zip(columns, values):
                    if len(value) > INLINE_LIMIT:
                        for offset in range(0, len(value), INLINE_LIMIT):
                            yield [position, index, column, offset // INLINE_LIMIT + 1, value[offset:offset + INLINE_LIMIT]]

        write_tables(path, (("Interface Results", INTERFACE_COLUMNS, findings(True)),
                            ("Database Results", DATABASE_COLUMNS, findings(False)),
                            ("Run Errors", ERROR_COLUMNS, errors()),
                            ("Details", DETAIL_COLUMNS, details())), clean=str)
        return Path(path)

    return spool.consume(consume, cleanup=cleanup, allow_partial=allow_partial)
