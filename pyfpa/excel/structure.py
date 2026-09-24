"""Static structure checks for model workbooks.

``verify_workbook`` proves the numbers agree with the engine.
``verify_structure`` proves the build standard without recalculating
anything: every editable driver is a named input on the Assumptions sheet
and styled as one, the Model sheet carries formulas only in its calculation
cells, the formula vocabulary stays restricted, each month column carries
one period label, and a ``check_*`` row holds the workbook's own ties.
"""

from __future__ import annotations

import re
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook
from pydantic import BaseModel

from pyfpa.excel.toolkit import INPUT_FONT_COLOR

_ALLOWED_FUNCTIONS = frozenset({"SUM", "MIN", "MAX", "IF"})
_FUNCTION_CALL = re.compile(r"([A-Z][A-Z0-9.]*)\s*\(")
_REQUIRED_SHEETS = ("Assumptions", "Model")


class StructureReport(BaseModel):
    passed: bool
    failures: list[str]
    checks_run: int


def _font_rgb(cell: object) -> str:
    color = cell.font.color  # type: ignore[attr-defined]
    if color is None:
        return ""
    return str(color.rgb or "").upper()


def _is_input_styled(cell: object) -> bool:
    return _font_rgb(cell).endswith(INPUT_FONT_COLOR)


def _named_input_failures(wb: Workbook, checks: int) -> tuple[list[str], int]:
    """Every defined name is an editable driver: on Assumptions, numeric, styled."""
    failures: list[str] = []
    assumptions = wb["Assumptions"]
    for name in wb.defined_names:
        checks += 1
        defined = wb.defined_names[name]
        destinations = [(str(sheet).strip("'"), ref) for sheet, ref in defined.destinations]
        if any(sheet != "Assumptions" for sheet, _ in destinations):
            failures.append(
                f"input {name}: drivers must live on the Assumptions sheet, "
                f"found {destinations}"
            )
            continue
        for sheet, ref in destinations:
            targets = assumptions[ref.replace("$", "")]
            if not isinstance(targets, tuple):
                targets = ((targets,),)
            for row_cells in targets:
                for cell in row_cells:
                    checks += 1
                    value = cell.value
                    shown = f"{sheet}!{ref}"
                    if isinstance(value, str):
                        failures.append(
                            f"input {name} ({shown}): contains a formula; drivers hold values"
                        )
                    elif isinstance(value, bool) or not isinstance(value, (int, float)):
                        failures.append(f"input {name} ({shown}): is not a number")
                    elif not _is_input_styled(cell):
                        failures.append(
                            f"input {name} ({shown}): is not styled as an input "
                            f"(font colour {INPUT_FONT_COLOR})"
                        )
    return failures, checks


def verify_structure(path: str | Path) -> StructureReport:
    """Check a model workbook's layout contract. No formulas are evaluated."""
    wb = load_workbook(Path(path))
    failures: list[str] = []
    checks = 0

    for sheet in _REQUIRED_SHEETS:
        checks += 1
        if sheet not in wb.sheetnames:
            failures.append(f"{sheet} sheet is missing")
    if failures:
        return StructureReport(passed=False, failures=failures, checks_run=checks)

    model = wb["Model"]

    # Period header: one label per month column, no gaps or duplicates.
    checks += 1
    headers = [model.cell(row=1, column=c).value for c in range(2, model.max_column + 1)]
    if not headers:
        failures.append("Model sheet has no month columns")
    seen: set[str] = set()
    for m_idx, label in enumerate(headers, start=1):
        text = "" if label is None else str(label).strip()
        if not text:
            failures.append(f"Model header month {m_idx}: empty period label")
        elif text in seen:
            failures.append(f"Model header month {m_idx}: duplicate period label {text!r}")
        else:
            seen.add(text)

    # Model rows: labelled, formulas only, restricted vocabulary, no input colour.
    has_checks_row = False
    for row in range(2, model.max_row + 1):
        label = model.cell(row=row, column=1).value
        text = "" if label is None else str(label).strip()
        checks += 1
        if not text:
            failures.append(f"Model row {row}: missing line label")
            continue
        if text.startswith("check_"):
            has_checks_row = True
        for col in range(2, model.max_column + 1):
            cell = model.cell(row=row, column=col)
            formula = cell.value
            checks += 1
            if not (isinstance(formula, str) and formula.startswith("=")):
                failures.append(
                    f"Model {text} month {col - 1}: value is not a formula ({formula!r})"
                )
                continue
            for fn in _FUNCTION_CALL.findall(formula):
                checks += 1
                if fn not in _ALLOWED_FUNCTIONS:
                    failures.append(
                        f"Model {text} month {col - 1}: forbidden function {fn} in {formula}"
                    )
            if _is_input_styled(cell):
                failures.append(
                    f"Model {text} month {col - 1}: calculation cell carries the input colour"
                )

    checks += 1
    if not has_checks_row:
        failures.append(
            "Model sheet has no check_ row: add at least one self-check that evaluates to zero"
        )

    check_counter, checks = _named_input_failures(wb, checks)
    failures.extend(check_counter)

    return StructureReport(passed=not failures, failures=failures, checks_run=checks)
