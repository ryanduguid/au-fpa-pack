"""Accounting depreciation for a forecast, from evidence held on disk.

Three things stay apart here, because a model that mixes them produces a
plausible cash forecast that is wrong:

- **Depreciation expense** reduces profit and moves no cash.
- **An asset purchase** moves cash on its own date, which is usually not the
  date the charge begins.
- **Tax** is a separate assumption. An AASB 116 carrying amount is not a
  deduction under ITAA 1997 Division 40, the two use different lives and
  conventions, and nothing in this module produces a tax figure.

`load_evidence` reads a calculation-evidence file something else produced. It
opens no socket and calls no service, which is what makes this usable in a
default model run: the figures were obtained once, deliberately, and committed
or kept beside the workspace.

`asset_movement` closes or refuses. If opening plus additions less depreciation
does not equal closing, it says so and names the gap. It never derives the
addition that would close it, because a number computed to make a
reconciliation pass is not evidence of anything.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

SUPPORTED_EVIDENCE_SCHEMAS = ("lodgeit-calculation-evidence/1",)
TOLERANCE = Decimal("0.01")


class DepreciationEvidenceError(ValueError):
    """An evidence file cannot support a forecast figure."""


@dataclass(frozen=True)
class DepreciationEvidence:
    """One validated accounting-depreciation figure, and where it came from."""

    label: str
    calculator: str
    period: str
    status: str
    opening: Decimal | None
    closing: Decimal | None
    charge: Decimal | None
    additions: Decimal | None
    advisory_notes: tuple[str, ...]
    source_path: Path
    calculation_sha256: str
    synthetic_input: bool

    @property
    def usable(self) -> bool:
        return self.status == "COMPUTED" and self.charge is not None


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _money(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DepreciationEvidenceError(
            f"{field} is {type(value).__name__}, not a decimal string. A JSON number has "
            "already lost whatever the calculator meant by it."
        )
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise DepreciationEvidenceError(f"{field} is not a decimal: {value!r}") from exc
    if not amount.is_finite():
        raise DepreciationEvidenceError(f"{field} is not finite")
    return amount


def load_evidence(path: str | Path) -> DepreciationEvidence:
    """Read one evidence file. Reads a file; contacts nothing.

    The digest is checked against the file's own calculation block, so a file
    edited after it was produced is refused rather than quietly believed.
    """
    source = Path(path)
    try:
        record = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DepreciationEvidenceError(f"{source} could not be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DepreciationEvidenceError(f"{source} is not valid JSON: {exc}") from exc
    if not isinstance(record, dict) or record.get("schema") not in SUPPORTED_EVIDENCE_SCHEMAS:
        raise DepreciationEvidenceError(
            f"{source}: evidence schema {record.get('schema') if isinstance(record, dict) else None!r} "
            f"is not one this pack reads ({', '.join(SUPPORTED_EVIDENCE_SCHEMAS)})."
        )
    calculation = record.get("calculation")
    if not isinstance(calculation, dict):
        raise DepreciationEvidenceError(f"{source}: no calculation block.")
    recorded = record.get("calculation_sha256")
    actual = hashlib.sha256(_canonical(calculation)).hexdigest()
    if recorded != actual:
        raise DepreciationEvidenceError(
            f"{source}: calculation_sha256 {recorded} does not match the calculation block "
            f"({actual}). The file has changed since it was produced."
        )
    call = calculation.get("call") or {}
    values = (calculation.get("normalised") or {}).get("values") or {}
    advisory = (calculation.get("upstream") or {}).get("advisory") or {}
    notes = tuple(note for note in advisory.get("notes", []) if isinstance(note, str))
    return DepreciationEvidence(
        label=str(calculation.get("label") or source.stem),
        calculator=str(call.get("calculator") or ""),
        period=str(call.get("period") or ""),
        status=str(call.get("status") or "UNKNOWN"),
        opening=_money(values.get("opening_wdv"), "opening_wdv"),
        closing=_money(values.get("closing_wdv"), "closing_wdv"),
        charge=_money(values.get("range_dep"), "range_dep"),
        additions=_money(values.get("cost_additions"), "cost_additions"),
        advisory_notes=notes,
        source_path=source,
        calculation_sha256=actual,
        synthetic_input=bool(calculation.get("synthetic_input")),
    )


@dataclass(frozen=True)
class MovementCheck:
    """Whether an asset movement closes, and by how much it does not."""

    opening: Decimal
    additions: Decimal
    depreciation: Decimal
    closing: Decimal
    gap: Decimal
    closes: bool
    reasons: tuple[str, ...]


def asset_movement(
    opening: Decimal,
    additions: Decimal,
    depreciation: Decimal,
    closing: Decimal,
    *,
    tolerance: Decimal = TOLERANCE,
) -> MovementCheck:
    """opening + additions - depreciation = closing, or a named gap.

    Nothing is derived to make it close. A gap is returned as a gap.
    """
    expected = opening + additions - depreciation
    gap = closing - expected
    closes = gap.copy_abs() <= tolerance
    reasons: tuple[str, ...] = ()
    if not closes:
        reasons = (
            f"movement does not close: opening {opening} plus additions {additions} less "
            f"depreciation {depreciation} is {expected}, against a closing balance of "
            f"{closing}, a gap of {gap}. No addition has been derived to close it.",
        )
    return MovementCheck(opening, additions, depreciation, closing, gap, closes, reasons)


def straight_line_schedule(
    evidence: DepreciationEvidence,
    months: pd.PeriodIndex,
) -> pd.Series:
    """Spread one evidenced charge evenly across the forecast months.

    A deliberate simplification, and the only kind of spreading this module
    does. The evidence carries a charge for a window; a monthly forecast needs
    it by month, and without a monthly breakdown the honest options are an even
    spread or nothing.

    ponytail: even spreading is wrong for a diminishing-value asset within the
    window. Where that matters, obtain evidence per month and sum it; the
    upgrade is more evidence, not more arithmetic here.
    """
    if not evidence.usable:
        raise DepreciationEvidenceError(
            f"{evidence.label}: evidence status is {evidence.status} and carries no charge, so "
            "there is nothing to spread. A refusal is not a nil amount."
        )
    if len(months) == 0:
        raise DepreciationEvidenceError("no months to spread the charge across")
    assert evidence.charge is not None
    per_month = float(evidence.charge) / len(months)
    return pd.Series(per_month, index=months, name="depreciation_expense")


def cash_and_expense(
    schedule: pd.Series,
    purchases: pd.Series | None = None,
) -> pd.DataFrame:
    """Depreciation expense beside asset purchases, kept apart.

    Returns a frame with `depreciation_expense` (profit, no cash) and
    `asset_purchases` (cash, no profit effect on its own). A caller that adds
    the two has undone the point of the split.
    """
    frame = pd.DataFrame({"depreciation_expense": schedule})
    frame["asset_purchases"] = 0.0 if purchases is None else purchases.reindex(
        schedule.index, fill_value=0.0,
    )
    frame["cash_effect"] = -frame["asset_purchases"]
    frame["profit_effect"] = -frame["depreciation_expense"]
    return frame
