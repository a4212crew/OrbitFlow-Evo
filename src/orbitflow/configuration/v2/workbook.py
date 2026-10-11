"""Thin XLSX adapter. Only the decision cells may change during decision consumption."""
from pathlib import Path
import hashlib
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from openpyxl.comments import Comment

from orbitflow.configuration.plans import require, PlanError
from .catalogue import CATALOGUE, BY_ID, BY_SHEET, normalize_display_inputs
from .planning import request, evaluate_decisions, MAX_ROWS
from .evidence import scoped_evidence

EXTRA = ("Row ID", "Existing Evidence", "Proposed CLI", "Live Validation", "Consistency",
         "Dependencies", "Observed At", "Findings", "No-op", "Engineer Decision")


class WorkbookRequests(list):
    """Adapter metadata survives normal planning without retaining unsafe rows."""
    def __init__(self, layout):
        super().__init__()
        self.layout = layout
        self.errors = []
        self.source_digest = ""


def literal(cell, value):
    text = str(value) if value is not None else ""
    require(len(text) <= 32767, "Excel cell exceeds limit; use JSON evidence")
    cell.value = text
    cell.data_type = "s"
    cell.alignment = Alignment(vertical="top", wrap_text=True)


def _base():
    book = Workbook()
    intro = book.active
    intro.title = "Introduction"
    intro.append(["OrbitFlow bulk configuration planning v2"])
    intro.append(["Order per device: worksheets left-to-right, then rows top-to-bottom. Review never authorizes device execution."])
    intro.append(["Predefined templates collect live read-only evidence. Manual CLI never connects; impact remains unknown."])
    intro.append(["Fill rows from row 3. Required fields are marked in header comments. Do not enter credentials. Blank optional descriptions preserve existing text."])
    intro.column_dimensions["A"].width = 115
    for t in CATALOGUE:
        intro.append([t.sheet])
        intro.cell(intro.max_row, 1).hyperlink = f"#'{t.sheet}'!A1"
        sheet = book.create_sheet(t.sheet)
        sheet.append(["Back to Introduction"])
        sheet["A1"].hyperlink = "#'Introduction'!A1"
        sheet.append(t.columns)
        sheet.freeze_panes = "B3"
        for index, col in enumerate(t.columns, 1):
            cell = sheet.cell(2, index)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="17365D")
            cell.comment = Comment(("Required" if col in ("management_ip", *t.required) else "Optional") +
                                   ("; comma-separated VLAN IDs or ranges, e.g. 445,545,2400-2444" if col == "vlans" else ""), "OrbitFlow")
            examples = {"management_ip": "192.0.2.10", "vlan_id": "445", "name": "Customer",
                        "description": "Customer Site Alpha", "service_instance": "10 (1-4000)",
                        "bridge_domain": "445; independent of ingress tag", "outer_vlan": "445",
                        "inner_vlan": "545 (QinQ only)", "pop_tags": "Legacy Pop1/Pop2; use rewrite instead",
                        "rewrite": "None removes rewrite; Pop1/Pop2 symmetric; ASR920 Push on untagged only",
                        "push_vlan": "Required only for Push",
                        "replace_untagged": "No preserves unrelated untagged membership; Yes explicitly replaces it",
                        "pvid": "Independent PVID; for PVID-only leave action, mode and vlans blank",
                        "subinterface": "10", "vsi": "existing-VSI", "bridge_group": "CUSTOMER",
                        "scope": "Affected resource metadata only; no CLI wrapper. Literal commands must include required hierarchy", "commands": "Literal multiline CLI; no credentials",
                        "interface": "Existing physical/aggregate interface; descriptions also permit existing subinterfaces"}
            if col in examples:
                cell.comment.text += "; " + examples[col]
            sheet.column_dimensions[get_column_letter(index)].width = 25 if col != "commands" else 65
            choices = {"action": "Add,Remove,Replace", "mode": "Access,Tagged" if t.family == "EdgeSwitch" else "configuration,interface,service",
                       "encapsulation": "dot1q,QinQ,untagged" if t.function in {"EVC", "L2VPN"} else "dot1q termination,vlan-type dot1q",
                       "rewrite": "None,Pop1,Pop2,Push", "replace_untagged": "No,Yes",
                       "platform": "cisco_ios,cisco_xe,cisco_xr,huawei_vrp,ubiquiti_edgeswitch"}
            if col in choices:
                dv = DataValidation(type="list", formula1='"' + choices[col] + '"')
                dv.errorTitle, dv.error, dv.showErrorMessage = "Invalid choice", "Select a listed value", True
                sheet.add_data_validation(dv)
                dv.add(f"{get_column_letter(index)}3:{get_column_letter(index)}5002")
    return book


def create_input(path):
    require(not Path(path).exists(), "output already exists")
    with Path(path).open("xb") as stream:
        _base().save(stream)


def read_input(path):
    book = load_workbook(path, read_only=True, data_only=False)
    result = WorkbookRequests(book.sheetnames)
    with Path(path).open("rb") as stream:
        result.source_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    try:
        require(set(book.sheetnames) == {"Introduction", *BY_SHEET}, "unexpected workbook sheets")
        for order, sheet in enumerate(book):
            if sheet.title == "Introduction":
                continue
            t = BY_SHEET[sheet.title]
            require(sheet.max_row <= 5002, "worksheet row limit exceeded")
            rows = sheet.iter_rows()
            next(rows)
            header = tuple(c.value for c in next(rows))
            require(header == t.columns, "input columns changed")
            for number, cells in enumerate(rows, 3):
                values = [c.value for c in cells]
                if all(v in (None, "") for v in values):
                    continue
                try:
                    require(not any(c.data_type == "f" for c in cells), "formulas forbidden in input")
                    source_inputs = dict(zip(t.columns, values))
                    result.append(request(t.id, normalize_display_inputs(t, source_inputs), source_inputs=source_inputs,
                                          sheet_order=order, row=number))
                except (PlanError, ValueError, TypeError):
                    result.errors.append(dict(sheet=t.sheet, row=number, reason="INVALID_INPUT_ROW"))
                require(len(result) + len(result.errors) <= MAX_ROWS, "workbook row limit exceeded")
        return result
    finally:
        book.close()


def export_plan(plan, path):
    require(not Path(path).exists(), "output already exists")
    book = _base()
    data = plan.to_dict()
    book["Introduction"]["B1"] = plan.digest
    results = {r["row_id"]: r for r in data["results"]}
    names = data["layout"]
    book._sheets = [book[s] for s in names]
    for t in CATALOGUE:
        sheet = book[t.sheet]
        for i, name in enumerate(EXTRA, len(t.columns) + 1):
            literal(sheet.cell(2, i), name)
            sheet.column_dimensions[get_column_letter(i)].width = 40
        dv = DataValidation(type="list", formula1='"Pending,Approve,Reject"')
        sheet.add_data_validation(dv)
        col = get_column_letter(len(t.columns) + len(EXTRA))
        dv.add(f"{col}3:{col}5002")
    details = book.create_sheet("Evidence Details")
    details.append(["Reference", "Source", "Line", "Exact sanitized excerpt"])
    summary = book.create_sheet("Summary")
    summary.append(["Sheet", "Row", "Result"])
    for error in data["input_errors"]:
        summary.append([error["sheet"], error["row"], error["reason"]])
        literal(book[error["sheet"]].cell(error["row"], 1), "Invalid input omitted; correct source workbook and re-plan")
    for r in data["requests"]:
        t, p, result = BY_ID[r["template_id"]], r["inputs"], results[r["row_id"]]
        sheet = book[t.sheet]
        summary.append([t.sheet, r["row"], "No-op" if result["no_op"] else result["decision"]])
        obs = data["observations"].get(p["management_ip"], {}) if t.family != "All" else {}
        excerpts = scoped_evidence(r, obs)
        for e in excerpts:
            row = details.max_row + 1
            for col, v in enumerate((r["row_id"], e["source_filename"], e["line"], e["excerpt"]), 1):
                literal(details.cell(row, col), v)
        evidence = "\n".join(e["excerpt"] for e in excerpts)
        if len(evidence) > 30000:
            evidence = "Evidence Details: " + r["row_id"]
        commands = result["commands"]
        original = r["source_inputs"]
        values = [(",".join(map(str, original[k])) if isinstance(original.get(k), list) else original.get(k, "")) for k in t.columns]
        values += [r["row_id"], evidence, commands if isinstance(commands, str) else "\n".join(commands),
                   result["live_validation"], result["consistency"], ",".join(result["dependencies"]), obs.get("observed_at", ""),
                   ",".join(result["findings"]), str(result["no_op"]), result["decision"]]
        for i, v in enumerate(values, 1):
            literal(sheet.cell(r["row"], i), v)
        sheet.row_dimensions[r["row"]].height = 90
    for c in ("A", "B", "C", "D"):
        details.column_dimensions[c].width = 70 if c == "D" else 28
    with Path(path).open("xb") as stream:
        book.save(stream)


def consume_decisions(original, path, *, expected_digest, now=None):
    """Future preflight adapter: caller pins a trusted plan digest; no authority.

    Validates protected values, then evaluates untrusted decision intent in memory.
    Never persists, re-signs or modifies the source plan.
    """
    require(original.digest == expected_digest, "source plan digest mismatch")
    # Regenerate the exact expected workbook in memory; compare every populated
    # cell and physical sheet order except ordinary engineer decision cells.
    from tempfile import TemporaryDirectory
    book = load_workbook(path, data_only=False)
    decisions = {}
    with TemporaryDirectory() as directory:
        expected_path = Path(directory) / "expected.xlsx"
        export_plan(original, expected_path)
        expected = load_workbook(expected_path, data_only=False)
        try:
            require(book.sheetnames == expected.sheetnames, "review worksheet order changed")
            decision_cells = {}
            for r in original.to_dict()["requests"]:
                t = BY_ID[r["template_id"]]
                decision_cells[(t.sheet, r["row"], len(t.columns) + len(EXTRA))] = r["row_id"]
            for sheet in expected:
                actual = book[sheet.title]
                require(actual.max_row == sheet.max_row and actual.max_column == sheet.max_column, "review dimensions changed")
                for row in sheet:
                    for cell in row:
                        other = actual.cell(cell.row, cell.column)
                        require(other.data_type != "f", "review formulas forbidden")
                        identity = decision_cells.get((sheet.title, cell.row, cell.column))
                        if identity:
                            decisions[identity] = other.value
                        else:
                            require(other.value == cell.value, "review content changed; re-plan required")
        finally:
            expected.close()
            book.close()
    return evaluate_decisions(original, decisions, expected_digest=expected_digest, now=now)
