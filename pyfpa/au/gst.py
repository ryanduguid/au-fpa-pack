# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""GST and BAS cash timing.

Turns a monthly P&L view (GST-exclusive revenue and purchases) into net
GST positions and BAS settlement cash flows, for both the monthly model
and the 13-week cash forecast. Cash timing only; not tax-return
software. Fuel tax credits, PAYG withholding and instalments on the BAS
are out of scope here (PAYG withholding belongs with payroll cash).

Categories: `taxable_sales_pct` covers GST-free (exports, basic food,
health) and input-taxed (financial supplies, residential rent) revenue
by exclusion; likewise `creditable_purchases_pct` for acquisitions
without input tax credits.

A due date that is not a business day moves to the first business day after
it: Taxation Administration Act 1953 s 8AAZMB for payment and Schedule 1
s 388-52 for lodgment. A public holiday for the whole of any State, the
Australian Capital Territory or the Northern Territory is not a business day,
in any State. For example, 28 February 2027 is a Sunday and Monday 1 March is
Labour Day throughout Western Australia, so the effective date is Tuesday
2 March 2027. Schedules keep that apart from the nominal date the rule names.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from enum import Enum
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from pyfpa.au.calendar import require_iso
from pyfpa.au.rates import (
    load_gst_bas_data,
    load_public_holidays,
    require_bas_dates_reviewed,
    require_holidays_reviewed,
)
from pyfpa.cash13.schemas import WeeklyFlow


class BasCycle(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class LodgmentChannel(str, Enum):
    """Which dates a statement falls on. The caller states that it qualifies.

    ORIGINAL is the standard date. ONLINE is the 2-week concession for a
    quarterly statement received and lodged online. AGENT is the lodgment
    program date when a registered agent lodges electronically, which also needs
    the previous statement lodged electronically. Neither covers a head company's
    instalment statement or instalment notices; the pages `gst_bas.yaml` cites
    set the full conditions.
    """

    ORIGINAL = "original"
    ONLINE = "online"
    AGENT = "agent"


class GstAssumptions(BaseModel):
    """Entity-level GST assumptions for cash forecasting."""

    bas_cycle: BasCycle = BasCycle.QUARTERLY
    lodgment_channel: LodgmentChannel = LodgmentChannel.ORIGINAL
    # True takes the 21 February date for an eligible December monthly BAS.
    december_agent_date: bool = False
    taxable_sales_pct: float = Field(default=1.0, ge=0, le=1)
    creditable_purchases_pct: float = Field(default=1.0, ge=0, le=1)
    # None uses the bundled rate; explicit rates are forecast scenarios.
    gst_rate: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    def resolved_rate(self) -> float:
        if self.gst_rate is not None:
            return self.gst_rate
        return float(load_gst_bas_data()["gst_rate"])

    @model_validator(mode="after")
    def _channel_fits_the_cycle(self) -> GstAssumptions:
        monthly = self.bas_cycle is BasCycle.MONTHLY
        if self.december_agent_date and not (monthly and self.lodgment_channel is LodgmentChannel.AGENT):
            raise ValueError("december_agent_date applies only to a monthly cycle lodged by an agent")
        if monthly and self.lodgment_channel is not LodgmentChannel.ORIGINAL and not self.december_agent_date:
            raise ValueError("a monthly cycle takes a lodgment channel only with december_agent_date")
        return self


def _validate_monthly_series(series: pd.Series) -> None:
    index = series.index
    if not isinstance(index, pd.PeriodIndex) or index.freqstr != "M":
        raise ValueError("expected a monthly PeriodIndex")
    if index.hasnans or not index.is_unique:
        raise ValueError("monthly periods must be unique and contain no missing dates")
    if len(index) and len(index) != index.max().ordinal - index.min().ordinal + 1:
        raise ValueError("monthly index has missing periods")
    try:
        finite = all(math.isfinite(value) for value in series)
    except TypeError:
        finite = False
    if not finite:
        raise ValueError("monthly amounts must be finite numbers, with no missing values")


def monthly_gst(
    revenue: pd.Series,
    purchases: pd.Series,
    assumptions: GstAssumptions | None = None,
) -> pd.DataFrame:
    """Net GST position by month from GST-exclusive revenue and purchases.

    `revenue` and `purchases` share a monthly PeriodIndex. Positive
    net_gst is payable to the ATO; negative is a refund.
    """
    assumptions = assumptions or GstAssumptions()
    rate = assumptions.resolved_rate()
    if not revenue.index.equals(purchases.index):
        raise ValueError("revenue and purchases must share the same monthly index")
    _validate_monthly_series(revenue)
    _validate_monthly_series(purchases)
    output_gst = revenue * assumptions.taxable_sales_pct * rate
    input_gst = purchases * assumptions.creditable_purchases_pct * rate
    frame = pd.DataFrame(
        {
            "output_gst": output_gst,
            "input_gst": input_gst,
            "net_gst": output_gst - input_gst,
        }
    )
    return frame


def _next_business_day(due: date) -> date:
    """`due` when it is a business day, otherwise the first business day after it.

    A weekend or a day in public_holidays.yaml is not a business day. The day
    the roll lands on must fall inside the span that list was verified for, or
    a holiday nobody has listed could be taken for a business day.
    """
    holidays = load_public_holidays()["holidays"]
    day = due
    while day.weekday() >= 5 or day in holidays:
        day += timedelta(days=1)
    require_holidays_reviewed(day)
    return day


def quarterly_bas_nominal_due_date(
    quarter_end: pd.Period,
    channel: LodgmentChannel | str = LodgmentChannel.ORIGINAL,
) -> date:
    """The date the rule names for the quarter ending with month `quarter_end`, before any roll."""
    channel = LodgmentChannel(channel)
    require_bas_dates_reviewed(quarter_end.end_time.date())
    data = load_gst_bas_data()
    if channel is LodgmentChannel.AGENT:
        program_date: date | None = data["agent_quarterly_due"].get(str(quarter_end))
        if program_date is None:
            raise ValueError(
                f"no agent program date is recorded for the quarter ending {quarter_end}; "
                "the ATO has not confirmed one, or gst_bas.yaml does not reach it"
            )
        return program_date
    key = f"{quarter_end.month:02d}"
    rule = data["quarterly_due"][key]  # {'month': int, 'day': int} relative to quarter end
    due_year = quarter_end.year + (1 if rule["month"] < quarter_end.month else 0)
    original = date(due_year, rule["month"], rule["day"])
    if channel is LodgmentChannel.ONLINE and key in data["online_concession_quarters"]:
        return original + timedelta(days=int(data["online_concession_days"]))
    return original


def quarterly_bas_due_date(
    quarter_end: pd.Period,
    channel: LodgmentChannel | str = LodgmentChannel.ORIGINAL,
) -> date:
    """Effective due date for the quarterly BAS whose quarter ends with month `quarter_end`."""
    return _next_business_day(quarterly_bas_nominal_due_date(quarter_end, channel))


def monthly_activity_statement_nominal_due_date(month: pd.Period, *, december_agent_date: bool = False) -> date:
    """The 21st of the month after `month`, before any roll.

    `december_agent_date` states that an eligible business's December statement
    takes the ATO's 21 February date (see `gst_bas.yaml`); other months ignore it.
    """
    require_bas_dates_reviewed(month.end_time.date())
    data = load_gst_bas_data()
    if december_agent_date and month.month == 12:
        rule = data["december_agent_due"]
        return date(month.year + 1, rule["month"], rule["day"])
    following = month + 1
    return date(following.year, following.month, int(data["monthly_due_day"]))


def monthly_activity_statement_due_date(month: pd.Period, *, december_agent_date: bool = False) -> date:
    """Effective due date for the monthly activity statement for `month`."""
    return _next_business_day(
        monthly_activity_statement_nominal_due_date(month, december_agent_date=december_agent_date)
    )


def bas_schedule(
    net_gst: pd.Series,
    assumptions: GstAssumptions | None = None,
) -> pd.DataFrame:
    """BAS settlement events from a monthly net_gst series.

    Returns a frame with columns period_label, nominal_due_date, due_date,
    amount: `nominal_due_date` is the date the rule names and `due_date` the
    effective date after the next-business-day roll.
    Quarterly cycles sum months into Sep/Dec/Mar/Jun quarters; a trailing
    quarter that ends after the series is excluded, because its BAS falls
    beyond the series. A leading partial quarter settles the months the
    series actually holds, so its GST cash is not lost.
    Positive amount = payment to ATO; negative = refund.
    Missing values, duplicate months and non-monthly indexes are rejected.
    """
    assumptions = assumptions or GstAssumptions()
    _validate_monthly_series(net_gst)
    rows: list[dict[str, Any]] = []
    if assumptions.bas_cycle is BasCycle.MONTHLY:
        for period, amount in net_gst.items():
            rows.append(
                {
                    "period_label": str(period),
                    "nominal_due_date": monthly_activity_statement_nominal_due_date(
                        period, december_agent_date=assumptions.december_agent_date
                    ),
                    "due_date": monthly_activity_statement_due_date(
                        period, december_agent_date=assumptions.december_agent_date
                    ),
                    "amount": float(amount),
                }
            )
    else:
        last_month = net_gst.index.max()
        for quarter, amounts in net_gst.groupby(net_gst.index.asfreq("Q-JUN")):
            quarter_end = quarter.asfreq("M", how="end")
            if quarter_end > last_month:
                continue  # quarter still open; BAS not yet determinable

            rows.append(
                {
                    "period_label": str(quarter),
                    "nominal_due_date": quarterly_bas_nominal_due_date(quarter_end, assumptions.lodgment_channel),
                    "due_date": quarterly_bas_due_date(quarter_end, assumptions.lodgment_channel),
                    "amount": float(amounts.sum()),
                }
            )
    return pd.DataFrame(rows, columns=["period_label", "nominal_due_date", "due_date", "amount"])


def gst_weekly_flows(
    schedule: pd.DataFrame,
    window_start: date | str,
    weeks: int = 13,
) -> tuple[list[WeeklyFlow], list[WeeklyFlow]]:
    """Map BAS settlements into 13-week-forecast flows.

    Returns (receipts, disbursements) of `WeeklyFlow` for settlements
    due inside the window. Payments become disbursements; refunds
    become receipts. Settlements outside the window are dropped.
    """
    return dated_weekly_flows(schedule, window_start, weeks, "BAS")


def dated_weekly_flows(
    schedule: pd.DataFrame,
    window_start: date | str,
    weeks: int,
    name: str,
) -> tuple[list[WeeklyFlow], list[WeeklyFlow]]:
    """Map rows of period_label, due_date and amount into flows named `name` and the label."""
    if isinstance(window_start, str):
        window_start = require_iso(window_start, "window_start")
    start = pd.Timestamp(window_start).date()
    receipts: list[WeeklyFlow] = []
    disbursements: list[WeeklyFlow] = []
    for row in schedule.itertuples(index=False):
        offset_days = (row.due_date - start).days
        if offset_days < 0:
            continue
        week = offset_days // 7 + 1
        if week > weeks:
            continue
        flow_name = f"{name} {row.period_label}"
        if row.amount >= 0:
            disbursements.append(
                WeeklyFlow(name=flow_name, amount=row.amount, start_week=week, recurrence="once")
            )
        else:
            receipts.append(
                WeeklyFlow(name=flow_name, amount=-row.amount, start_week=week, recurrence="once")
            )
    return receipts, disbursements
