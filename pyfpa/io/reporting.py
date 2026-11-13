from __future__ import annotations

import math
from collections.abc import Iterable
from numbers import Integral, Number
from pathlib import Path
from typing import Any

import pandas as pd

from pyfpa.io.atomic import staged_output

_REQUIRED_COLUMNS = {"revenue", "ebitda", "net_income", "ending_cash"}


def _require_finite(value: Any) -> None:
    try:
        if isinstance(value, Integral) or math.isfinite(value):
            return
    except (TypeError, ValueError, OverflowError):
        pass
    raise ValueError("financial reporting values must be finite numbers")


def _money(value: int | float) -> str:
    _require_finite(value)
    sign = "-" if value < 0 else ""
    if isinstance(value, Integral):
        return f"{sign}${abs(int(value)):,}"
    return f"{sign}${abs(value):,.0f}"


def _total(values: Iterable[int | float]) -> int | float:
    return sum(int(value) if isinstance(value, Integral) else value for value in values)


def _weeks_text(weeks: list[int]) -> str:
    if not weeks:
        return "none"
    if len(weeks) == 1:
        return f"1 (week {weeks[0]})"
    listed = ", ".join(str(week) for week in weeks[:-1]) + f" and {weeks[-1]}"
    return f"{len(weeks)} (weeks {listed})"


def to_briefing_md(
    forecast_df: pd.DataFrame,
    *,
    title: str = "Cash Flow Briefing",
    runway: dict[str, Any] | None = None,
) -> str:
    """Render a monthly forecast as a board-style markdown briefing.

    Expects columns: revenue, ebitda, net_income, ending_cash. If `runway`
    (the dict from cash13.runway_summary) is provided, a 13-week section is added.
    """
    missing = _REQUIRED_COLUMNS - set(forecast_df.columns)
    if missing:
        raise ValueError(f"forecast_df missing required columns: {sorted(missing)}")
    if forecast_df.empty:
        # Ending cash is read with .iloc[-1], which raises IndexError on an empty
        # frame. Refuse it the way a missing column is refused, rather than failing
        # inside the headline block.
        raise ValueError("forecast_df has no rows to brief")
    df = forecast_df
    for column in _REQUIRED_COLUMNS:
        for value in df[column]:
            _require_finite(value)
    lines = [f"# {title}", "", "## Headline", ""]
    lines += [
        f"- **Revenue:** {_money(_total(df['revenue']))}",
        f"- **EBITDA:** {_money(_total(df['ebitda']))}",
        f"- **Net income:** {_money(_total(df['net_income']))}",
        f"- **Ending cash:** {_money(df['ending_cash'].iloc[-1])}",
        "",
    ]

    if runway is not None:
        first_neg = runway["first_negative_week"]
        first_neg_text = f"week {first_neg}" if first_neg is not None else "none"
        lines += [
            "## 13-Week Cash Runway",
            "",
            f"- **Trough:** {_money(runway['min_cash'])} (week {runway['min_week']})",
            f"- **First negative week:** {first_neg_text}",
        ]
        # A hand-built runway without the key keeps the briefing it had before.
        if "negative_weeks" in runway:
            lines.append(f"- **Weeks below zero:** {_weeks_text(runway['negative_weeks'])}")
        lines.append("")

    lines += [
        "## Monthly",
        "",
        "| Month | Revenue | EBITDA | Net Income | Ending Cash |",
        "|---|---|---|---|---|",
    ]
    columns = ["revenue", "ebitda", "net_income", "ending_cash"]
    for period, revenue, ebitda, net_income, ending_cash in df[columns].itertuples(name=None):
        lines.append(
            f"| {period} | {_money(revenue)} | {_money(ebitda)} | "
            f"{_money(net_income)} | {_money(ending_cash)} |"
        )
    return "\n".join(lines) + "\n"


def forecast_to_excel(forecast_df: pd.DataFrame, path: str | Path) -> None:
    """Write a forecast DataFrame to an .xlsx workbook (sheet 'Forecast')."""
    # The stream carries no suffix, so pandas always writes xlsx bytes.
    if Path(path).suffix.lower() != ".xlsx":
        raise ValueError(f"forecast_to_excel writes .xlsx only, not {Path(path).name}")
    for _, series in forecast_df.items():
        if series.isna().any():
            raise ValueError("forecast values must be finite; missing cells are not reportable")
        for value in series:
            if isinstance(value, Number):
                _require_finite(value)
    with staged_output(path) as staged:
        with staged.open("wb") as stream:
            forecast_df.to_excel(stream, sheet_name="Forecast")
