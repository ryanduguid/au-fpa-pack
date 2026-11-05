# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""FBT return and payment dates for the 13-week cash forecast.

Fringe Benefits Tax Assessment Act 1986 s 68 sets the return for 21 May after
the FBT year, or a later date the Commissioner allows, and s 90 makes the tax
due on 21 May. The ATO's lodgment program generally gives 25 June for lodging
and paying when a tax agent lodges electronically and has the employer on its
FBT client list by 21 May. An employer lodging its own return, and a paper
return from an agent, stay on 21 May. `fbt.yaml` holds the dates and sources.

The FBT year is named by the 31 March it ends on, so 2027 is the year to
31 March 2027, whose return falls due in May 2027. `amount` is what is left to
pay with the return after instalments; a negative amount is a refund, which
`fbt_weekly_flows` forecasts only on a date the caller gives. FBT instalments are
paid on activity statements, so they take the BAS dates in `pyfpa.au.gst`.
"""

from __future__ import annotations

import math
from datetime import date

import pandas as pd

from pyfpa.au.gst import LodgmentChannel, _next_business_day, dated_weekly_flows
from pyfpa.au.rates import load_fbt_data, require_fbt_dates_reviewed
from pyfpa.cash13.schemas import WeeklyFlow


def fbt_nominal_due_date(fbt_year: int, channel: LodgmentChannel | str = LodgmentChannel.ORIGINAL) -> date:
    """The date the rule names for the FBT year ending 31 March `fbt_year`, before any roll."""
    channel = LodgmentChannel(channel)
    require_fbt_dates_reviewed(date(fbt_year, 3, 31))
    data = load_fbt_data()
    rule = data["agent_due" if channel is LodgmentChannel.AGENT else "return_due"]
    return date(fbt_year, rule["month"], rule["day"])


def fbt_due_date(fbt_year: int, channel: LodgmentChannel | str = LodgmentChannel.ORIGINAL) -> date:
    """Effective date to lodge the return and pay for the FBT year ending 31 March `fbt_year`."""
    return _next_business_day(fbt_nominal_due_date(fbt_year, channel))


def fbt_schedule(
    fbt_year: int,
    amount: float,
    channel: LodgmentChannel | str = LodgmentChannel.ORIGINAL,
) -> pd.DataFrame:
    """The return's settlement: columns period_label, nominal_due_date, due_date, amount."""
    if not math.isfinite(amount):
        raise ValueError("the FBT amount must be a finite number")
    return pd.DataFrame(
        [{
            "period_label": str(fbt_year),
            "nominal_due_date": fbt_nominal_due_date(fbt_year, channel),
            "due_date": fbt_due_date(fbt_year, channel),
            "amount": float(amount),
        }]
    )


def fbt_weekly_flows(
    schedule: pd.DataFrame,
    window_start: date | str,
    weeks: int = 13,
    *,
    expected_receipt_on: date | None = None,
) -> tuple[list[WeeklyFlow], list[WeeklyFlow]]:
    """Map an FBT settlement into 13-week-forecast (receipts, disbursements).

    A payment is a disbursement on its due date. A refund has no due date: 21 May
    is the payment deadline, and a refund depends on lodgment, ATO processing and
    offsets. So a negative settlement is a receipt only on `expected_receipt_on`,
    the date the caller expects it; without that date it is left out of the
    forecast, though `fbt_schedule` keeps it. Flows outside the window are dropped.
    """
    refund = schedule["amount"] < 0
    _, disbursements = dated_weekly_flows(schedule[~refund], window_start, weeks, "FBT")
    if expected_receipt_on is None:
        return [], disbursements
    expected = schedule[refund].assign(due_date=expected_receipt_on)
    receipts, _ = dated_weekly_flows(expected, window_start, weeks, "FBT")
    return receipts, disbursements
