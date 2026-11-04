from __future__ import annotations

import calendar
from collections.abc import Sequence
from datetime import date

from pyfpa.cash13.schemas import WeeklyFlow


def _months_later(anchor: date, months: int) -> date | None:
    """The anchor's day of month `months` later, or that month's last day if
    earlier; None when that month is past the last one `date` can hold."""
    index = anchor.month - 1 + months
    year, month = anchor.year + index // 12, index % 12 + 1
    if year > date.max.year:
        return None
    return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))


def _monthly_weeks(flow: WeeklyFlow, window_start: date | None, last_week: int) -> list[int]:
    """Weeks from `start_week` to `last_week` that hold a monthly or quarterly date."""
    if flow.anchor_date is None or window_start is None:
        raise ValueError(f"{flow.name!r} recurs {flow.recurrence}, which needs anchor_date and window_start")
    anchor = flow.anchor_date
    step = 1 if flow.recurrence == "monthly" else 3
    # Dates in months before window_start's month cannot reach week 1, so an
    # old anchor does not cost a loop through every month since it.
    months_before = (window_start.year - anchor.year) * 12 + window_start.month - anchor.month
    count = max(0, months_before // step)
    hit_weeks = []
    while (occurrence := _months_later(anchor, count * step)) is not None:
        week = (occurrence - window_start).days // 7 + 1
        if week > last_week:
            break
        if week >= flow.start_week:
            hit_weeks.append(week)
        count += 1
    return hit_weeks


def expand_flow(flow: WeeklyFlow, weeks: int, window_start: date | None = None) -> list[float]:
    """Expand one WeeklyFlow into a length-`weeks` list (index 0 == week 1).

    A monthly or quarterly flow needs `window_start`, the first day of week 1."""
    amounts = [0.0] * weeks
    end = flow.end_week if flow.end_week is not None else weeks

    hit_weeks: Sequence[int]
    if flow.recurrence == "once":
        hit_weeks = [flow.start_week]
    elif flow.recurrence == "weekly":
        hit_weeks = range(flow.start_week, end + 1)
    elif flow.recurrence == "biweekly":
        hit_weeks = range(flow.start_week, end + 1, 2)
    else:  # monthly or quarterly
        hit_weeks = _monthly_weeks(flow, window_start, min(end, weeks))

    for week in hit_weeks:
        if 1 <= week <= weeks:
            amounts[week - 1] += flow.amount
    return amounts
