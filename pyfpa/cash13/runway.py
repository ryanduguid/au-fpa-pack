from __future__ import annotations

from typing import Any

import pandas as pd


def _first_week(weeks: pd.Index) -> int | None:
    return None if weeks.empty else int(weeks[0])


def runway_summary(forecast_df: pd.DataFrame, headroom_buffer: float = 0.0) -> dict[str, Any]:
    """Summarise a 13-week forecast: cash trough and the weeks below zero.

    Returns {"min_cash": float, "min_week": int, "first_negative_week": int | None,
    "negative_weeks": list[int]}, where "negative_weeks" names every week whose
    ending cash is below zero, in order. A forecast with a headroom column adds
    "min_headroom", "first_headroom_breach_week" and "headroom_breach_weeks", the
    first and every week headroom is below `headroom_buffer`.
    """
    if not 0 <= headroom_buffer < float("inf"):
        raise ValueError(f"headroom_buffer must be finite and not negative, got {headroom_buffer}")
    ending = forecast_df["ending_cash"]
    negative = ending.index[ending < 0]
    summary: dict[str, Any] = {
        "min_cash": float(ending.min()),
        "min_week": int(ending.idxmin()),
        "first_negative_week": _first_week(negative),
        "negative_weeks": [int(week) for week in negative],
    }
    if "headroom" in forecast_df.columns:
        headroom = forecast_df["headroom"]
        breach = headroom.index[headroom < headroom_buffer]
        summary["min_headroom"] = float(headroom.min())
        summary["first_headroom_breach_week"] = _first_week(breach)
        summary["headroom_breach_weeks"] = [int(week) for week in breach]
    return summary
