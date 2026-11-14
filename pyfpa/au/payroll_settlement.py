# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""Payroll liabilities and their settlement: when each payroll cost is owed and paid.

`payroll_forecast` gives monthly costs, and its cash view treats them as paid in
the month incurred. This module turns those costs into dated settlement events
and keeps three dates apart: the obligation date (when the liability arises),
the due date (from a rule the caller supplies for each component) and the cash
date (when the forecast pays). Monthly cash, month-end liabilities and 13-week
flows are all derived from the same events, so they cannot disagree.

This is a forecast allocation, not a payroll calculation. By default each
month's gross pay is split equally across that month's paydays, and PAYG
withholding is a declared average rate. Alternatively the caller passes each
role's pay and Schedule 1 withholding for each payday, worked out by the native
calculator (`pyfpa.io.native_tax`); this module only reconciles and dates them.
Leave provisions are accruals and have no settlement here. No statutory calendar lives in this
module: due-date rules are passed in.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd

from pyfpa.au.payg_withholding import RoleWithholding
from pyfpa.cash13.schemas import WeeklyFlow

DueRule = Callable[[date], date]

# Components whose liability arises on each payday, and those that accrue monthly.
PAYDAY_COMPONENTS = ("net_wages", "payg_withholding", "super_guarantee")
MONTHLY_COMPONENTS = ("payroll_tax", "workers_comp")
COMPONENTS = PAYDAY_COMPONENTS + MONTHLY_COMPONENTS


@dataclass(frozen=True)
class SettlementEvent:
    component: str
    source_period: pd.Period
    obligation_date: date
    due_date: date
    cash_date: date
    amount: float

    def __post_init__(self) -> None:
        if self.component not in COMPONENTS:
            raise ValueError(f"unknown component {self.component!r}")
        if not math.isfinite(self.amount) or self.amount < 0:
            raise ValueError(f"{self.component} for {self.source_period} must be a finite amount of 0 or more")
        if self.due_date < self.obligation_date:
            raise ValueError(f"{self.component} for {self.source_period} falls due before it arises")
        if self.cash_date < self.obligation_date:
            raise ValueError(f"{self.component} for {self.source_period} would be paid before it arises")


def _event(component: str, period: pd.Period, obligation: date, amount: float,
           due_rules: Mapping[str, DueRule], early: Mapping[str, int]) -> SettlementEvent:
    due = obligation if component == "net_wages" else due_rules[component](obligation)
    cash = due - timedelta(days=early.get(component, 0))
    return SettlementEvent(component, period, obligation, due, cash, amount)


def _role_pays(
    role_withholding: Sequence[RoleWithholding], paydays: Sequence[date],
) -> tuple[dict[date, tuple[Decimal, Decimal]], Counter[date]]:
    """Each payday's gross and withholding across its role payments, and how many there are."""
    scheduled: dict[date, tuple[Decimal, Decimal]] = {}
    counts: Counter[date] = Counter()
    seen: set[tuple[str, date]] = set()
    for result in role_withholding:
        payment = result.payment
        key = (payment.role_name, payment.payday)
        if key in seen:
            raise ValueError("role_withholding repeats a role and payday")
        seen.add(key)
        if payment.payday not in paydays:
            raise ValueError("role_withholding contains an undeclared payday")
        counts[payment.payday] += 1
        gross_before, tax_before = scheduled.get(payment.payday, (Decimal(0), Decimal(0)))
        scheduled[payment.payday] = (gross_before + payment.earnings, tax_before + result.withholding)
    return scheduled, counts


def _reconciled_withholding(
    period: pd.Period, row: pd.Series, days: Sequence[date],
    scheduled: Mapping[date, tuple[Decimal, Decimal]], counts: Counter[date],
) -> float:
    """The month's scheduled withholding, once its role pays reconcile to the frame's gross."""
    if row["bonuses"] != 0:
        raise ValueError("role_withholding supports regular earnings only, not bonuses")
    gross = float(row["gross_wages"])
    actual = sum((scheduled.get(day, (Decimal(0), Decimal(0)))[0] for day in days), Decimal(0))
    tolerance = Decimal("0.005") * max(sum(counts[day] for day in days), 1)
    if not math.isfinite(gross) or gross < 0 or abs(actual - Decimal(str(gross))) > tolerance:
        raise ValueError(f"role_withholding earnings do not reconcile to {period}")
    if gross and any(day not in scheduled for day in days):
        raise ValueError(f"role_withholding is missing a payday in {period}")
    return float(sum((scheduled[day][1] for day in days if day in scheduled), Decimal(0)))


def settlement_events(
    payroll: pd.DataFrame,
    paydays: Sequence[date],
    *,
    payg_withholding_rate_assumption: float | None = None,
    due_rules: Mapping[str, DueRule],
    pay_days_before_due: Mapping[str, int] | None = None,
    role_withholding: Sequence[RoleWithholding] | None = None,
) -> list[SettlementEvent]:
    """Dated settlement events for a `payroll_forecast` frame.

    `due_rules` maps each component other than net wages, which fall due on the
    payday, to a function from its obligation date to its due date.
    `pay_days_before_due` moves a component's cash date that many days before
    its due date (default 0: paid when due).
    Supply either the existing average-rate assumption or explicit per-role
    calculator results. Schedule mode uses their actual gross by payday and
    reconciles the month's earnings to the frame within half a cent a payment,
    as each payment is in whole cents. Retain the
    results' evidence separately; settlement events are cash projections.
    """
    rate = 0.0
    if role_withholding is None:
        if payg_withholding_rate_assumption is None or not 0 <= payg_withholding_rate_assumption < 1:
            raise ValueError("payg_withholding_rate_assumption must be at least 0 and below 1")
        rate = payg_withholding_rate_assumption
    elif payg_withholding_rate_assumption is not None:
        raise ValueError("choose either the average-rate assumption or role_withholding")
    if "net_wages" in due_rules:
        raise ValueError("net_wages fall due on each payday, so due_rules cannot move them")
    early = pay_days_before_due or {}
    for name, mapping in (("due_rules", due_rules), ("pay_days_before_due", early)):
        unknown = sorted(set(mapping) - set(COMPONENTS))
        if unknown:
            raise ValueError(f"{name} names an unknown component: " + ", ".join(unknown))
    if any(isinstance(days, bool) or not isinstance(days, int) or days < 0 for days in early.values()):
        raise ValueError("pay_days_before_due must be whole days, 0 or more")
    if len(set(paydays)) != len(paydays):
        raise ValueError("paydays are repeated")
    months = payroll.index
    by_month: dict[pd.Period, list[date]] = {period: [] for period in months}
    for day in sorted(paydays):
        period = pd.Period(day, freq="M")
        if period not in by_month:
            raise ValueError(f"payday {day.isoformat()} falls outside the payroll months")
        by_month[period].append(day)

    scheduled: Mapping[date, tuple[Decimal, Decimal]] = {}
    counts: Counter[date] = Counter()
    if role_withholding is not None:
        scheduled, counts = _role_pays(role_withholding, paydays)

    events: list[SettlementEvent] = []
    for period, row in payroll.iterrows():
        gross = float(row["gross_wages"] + row["bonuses"])
        days = by_month[period]
        if role_withholding is not None:
            withholding = _reconciled_withholding(period, row, days, scheduled, counts)
            net_wages = gross - withholding
        else:
            withholding = gross * rate
            net_wages = gross * (1 - rate)
        amounts = {
            "net_wages": net_wages,
            "payg_withholding": withholding,
            "super_guarantee": float(row["super_guarantee"]),
            "payroll_tax": float(row["payroll_tax"]),
            "workers_comp": float(row["workers_comp"]),
        }
        for component, amount in amounts.items():
            if amount and component != "net_wages" and component not in due_rules:
                raise ValueError(f"{component} has costs but no due rule")
        if not days and any(amounts[c] for c in PAYDAY_COMPONENTS):
            raise ValueError(f"{period} has payroll costs but no payday")
        for day in days:
            for component in PAYDAY_COMPONENTS:
                amount = amounts[component] / len(days)
                if role_withholding is not None and component != "super_guarantee":
                    gross_pay, withheld_pay = scheduled.get(day, (Decimal(0), Decimal(0)))
                    amount = float(withheld_pay if component == "payg_withholding" else gross_pay - withheld_pay)
                if amount:
                    events.append(_event(component, period, day, amount,
                                         due_rules, early))
        month_end = period.end_time.date()
        for component in MONTHLY_COMPONENTS:
            if amounts[component]:
                events.append(_event(component, period, month_end, amounts[component], due_rules, early))
    return events


def monthly_settlement(events: Sequence[SettlementEvent], months: pd.PeriodIndex) -> pd.DataFrame:
    """Obligations, cash and closing liability by component and month.

    An obligation before the first month opens the liability; cash dated after
    the last month leaves the amount in closing liability. `months` must run
    consecutively: a skipped month would drop its obligations from the roll-forward.
    """
    if not isinstance(months, pd.PeriodIndex) or months.freqstr != "M" or not (
            len(months) and months.is_unique and months.is_monotonic_increasing
            and len(months) == months[-1].ordinal - months[0].ordinal + 1):
        raise ValueError("months must be a monthly PeriodIndex running consecutively, without gaps or repeats")
    columns =[f"{c}_{kind}" for c in COMPONENTS for kind in ("obligations", "cash", "closing")]
    table = pd.DataFrame(0.0, index=months, columns=[*columns, "total_cash"])
    first = months[0]
    for component in COMPONENTS:
        own = [e for e in events if e.component == component]
        opening = sum(e.amount for e in own if pd.Period(e.obligation_date, freq="M") < first) - sum(
            e.amount for e in own if pd.Period(e.cash_date, freq="M") < first)
        closing = opening
        for month in months:
            obligations = sum(e.amount for e in own if pd.Period(e.obligation_date, freq="M") == month)
            cash = sum(e.amount for e in own if pd.Period(e.cash_date, freq="M") == month)
            closing += obligations - cash
            table.loc[month, [f"{component}_obligations", f"{component}_cash", f"{component}_closing"]] = [
                obligations, cash, closing]
    table["total_cash"] = table[[f"{c}_cash" for c in COMPONENTS]].sum(axis=1)
    return table


def settlement_weekly_flows(events: Sequence[SettlementEvent], window_start: date,
                            weeks: int = 13) -> list[WeeklyFlow]:
    """Disbursements for the 13-week forecast; payments outside the window are left out."""
    if isinstance(weeks, bool) or not isinstance(weeks, int) or weeks < 1:
        raise ValueError("weeks must be a whole number of weeks, 1 or more")
    flows = []
    for event in events:
        offset = (event.cash_date - window_start).days
        if 0 <= offset < weeks * 7:
            flows.append(WeeklyFlow(name=f"{event.component} {event.source_period}",
                                    amount=event.amount, start_week=offset // 7 + 1))
    return flows
