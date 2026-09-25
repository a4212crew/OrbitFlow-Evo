"""Shared approved Excel target input; no device discovery or output logging."""

from pathlib import Path
from openpyxl import load_workbook

REQUIRED_COLUMNS = ("management_ip", "username", "password")


def load_targets(path: str | Path, *, isolate_invalid: bool = False) -> list[dict[str, str]]:
    """Load required fields, ignoring future-compatible columns.

    By default incomplete rows raise, preserving inventory validation behavior.
    Batch consumers may retain them for per-row error recording instead.
    """
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        header_row = next(rows, None)
        if header_row is None:
            raise ValueError("Excel input is empty")
        headers = {
            str(value).strip().casefold(): index
            for index, value in enumerate(header_row)
            if value is not None
        }
        missing = [name for name in REQUIRED_COLUMNS if name not in headers]
        if missing:
            raise ValueError(
                f"Excel input is missing required columns: {', '.join(missing)}"
            )
        targets = []
        for row_number, row in enumerate(rows, start=2):
            values = {
                name: (
                    ""
                    if headers[name] >= len(row) or row[headers[name]] is None
                    else str(row[headers[name]]).strip()
                )
                for name in REQUIRED_COLUMNS
            }
            if not any(values.values()):
                continue
            if not all(values.values()) and not isolate_invalid:
                raise ValueError(f"Excel row {row_number} has an empty required field")
            targets.append(values)
        if not targets:
            raise ValueError("Excel input contains no device rows")
        return targets
    finally:
        workbook.close()

