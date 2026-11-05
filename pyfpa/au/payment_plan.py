# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""Estimate what paying an ATO debt by instalments would cost in cash and GIC.

This shows the cost of a proposed plan; it does not make one. The Commissioner
decides whether to permit instalments, and an arrangement does not change when
the amount is due: GIC runs from the due date regardless (Taxation Administration
Act 1953 Schedule 1 s 255-15, read on the Federal Register on 5 November 2026).

The estimate follows the statute (ss 8AAC, 8AAD and 8AAZF, Schedule 1 ss 16-80
and 105-80). GIC runs from the start of the day the amount was due. For each day
it is that day's rate times the balance at the end of the day, a payment made
that day having already come off, and it joins the balance, so it compounds. The
rate for a day is the annual rate for its quarter divided by the days in the
calendar year.

It stays an estimate. It assumes the single amount passed in is the whole
balance and that every payment arrives on its date. The ATO's own account
decides the figure, later liabilities and credits change it, and it can remit
GIC, as it does on a kept interest-free plan for an eligible small business. The
ATO's estimator does not cover super guarantee charge debts, and nor does this.
Amounts are carried exactly and rounded to the cent half up only for display.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import NamedTuple

import pandas as pd

from pyfpa.au.gst import _next_business_day, dated_weekly_flows
from pyfpa.au.rates import RateEntry, load_gic_table, rate_at
from pyfpa.cash13.schemas import WeeklyFlow

ESTIMATE_NOTE = (
    "Estimate only, not an ATO figure, and not an ATO approved payment plan. The ATO decides "
    "whether to accept a plan and on what terms, and GIC keeps accruing until the debt is paid."
)
FLOW_NAME = "Proposed ATO payment plan (estimate, not ATO approved)"

_CENT = Decimal("0.01")


class PlanFrequency(str, Enum):
    WEEKLY = "weekly"
    FORTNIGHTLY = "fortnightly"
    MONTHLY = "monthly"


class PaymentPlanEstimate(NamedTuple):
    """`schedule` has columns period_label, due_date, amount, gic_accrued, closing_balance.

    `gic_accrued` and `closing_balance` stand at the end of the row's day, with that
    day's GIC included. The payment that clears the debt accrues none that day.
    """

    schedule: pd.DataFrame
    estimated_gic: float
    total_paid: float
    note: str


def _money(value: float, what: str) -> Decimal:
    amount = Decimal(str(value))
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(_CENT):
        raise ValueError(f"{what} must be a positive amount in whole cents, got {value!r}")
    return amount


def _cents(amount: Decimal) -> Decimal:
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


def _daily_rate(table: list[RateEntry], day: date) -> Decimal:
    days_in_year = 366 if calendar.isleap(day.year) else 365
    return Decimal(str(rate_at(table, day))) / days_in_year


def _instalment_dates(first: date, frequency: PlanFrequency) -> Iterator[date]:
    number = 0
    while True:
        if frequency is PlanFrequency.MONTHLY:
            # From the first date each time, so a 31st keeps returning after February.
            yield (pd.Timestamp(first) + pd.DateOffset(months=number)).date()
        else:
            yield first + timedelta(weeks=number * (1 if frequency is PlanFrequency.WEEKLY else 2))
        number += 1


def _plan_rows(
    owed: Decimal,
    start: date,
    first: tuple[date, Decimal],
    instalment: Decimal,
    dates: Iterator[date],
) -> tuple[list[dict[str, object]], Decimal, Decimal]:
    """The schedule's rows, the GIC and the total paid, to the payment that clears the debt."""
    table = load_gic_table()
    label, (pay_on, amount) = "upfront", first
    number = 0
    balance = owed
    gic = Decimal(0)
    paid = Decimal(0)
    gic_shown = Decimal(0)
    rows: list[dict[str, object]] = []
    day = start
    while True:
        pay_day = day == pay_on
        cleared = False
        if pay_day:
            payment = min(amount, _cents(balance))
            balance -= payment
            paid += payment
            cleared = _cents(balance) == 0
        if not cleared:
            accrued = balance * _daily_rate(table, day)
            balance += accrued
            gic += accrued
        if pay_day:
            # Rounding the running total keeps the column adding to the total.
            gic_so_far = _cents(gic)
            rows.append(
                {
                    "period_label": label,
                    "due_date": day,
                    "amount": float(payment),
                    "gic_accrued": float(gic_so_far - gic_shown),
                    "closing_balance": float(owed + gic_so_far - paid),
                }
            )
            gic_shown = gic_so_far
            if cleared:
                return rows, gic_shown, paid
            number += 1
            label, pay_on, amount = f"instalment {number}", next(dates), instalment
        day += timedelta(days=1)


def payment_plan_estimate(
    amount_owed: float,
    due_date: date,
    *,
    upfront: float,
    upfront_on: date,
    instalment: float,
    first_instalment_on: date,
    frequency: PlanFrequency | str = PlanFrequency.MONTHLY,
) -> PaymentPlanEstimate:
    """Payments that would clear `amount_owed`, with the GIC they would carry.

    `due_date` is the effective date, as a schedule's `due_date` column gives it:
    a date that is not a business day is refused, because the count starts there.
    The ATO says a plan needs an up-front payment, so `upfront` must be above 0.
    Each instalment is `instalment` until the last, which clears the balance
    including GIC. The estimate is refused when any day it needs falls past the
    rate table's reviewed_until, which is also where a plan that never clears ends.
    """
    frequency = PlanFrequency(frequency)
    owed = _money(amount_owed, "amount_owed")
    first_payment = _money(upfront, "upfront")
    regular = _money(instalment, "instalment")
    if first_payment >= owed:
        raise ValueError("an upfront payment of the whole amount needs no payment plan")
    if _next_business_day(due_date) != due_date:
        raise ValueError(f"{due_date.isoformat()} is not a business day; pass the effective due date")
    if upfront_on < due_date:
        raise ValueError("upfront_on cannot be before the due date")
    if first_instalment_on <= upfront_on:
        raise ValueError("first_instalment_on must be after upfront_on")

    rows, gic, paid = _plan_rows(
        owed, due_date, (upfront_on, first_payment), regular, _instalment_dates(first_instalment_on, frequency)
    )
    return PaymentPlanEstimate(pd.DataFrame(rows), float(gic), float(paid), ESTIMATE_NOTE)


def payment_plan_weekly_flows(
    estimate: PaymentPlanEstimate,
    window_start: date | str,
    weeks: int = 13,
) -> list[WeeklyFlow]:
    """The plan's payments inside the window, as disbursements labelled an estimate.

    For a scenario only: there they replace the tax's flow on its due date
    instead of sitting beside it. The base case keeps the statutory date.
    """
    return dated_weekly_flows(estimate.schedule, window_start, weeks, FLOW_NAME)[1]
