# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""The payment plan estimate, checked against a fixture worked by hand.

Fabricated: $10,000.00 of BAS due Monday 21 September 2026, $2,000.00 paid that
day and $3,000.00 a month from 21 October 2026. GIC applies to each day's closing
balance at the ATO's rates, 11.43% to 30 September and 11.51% from 1 October,
each divided by 365 (r1 and r2):

    21 Sep close   8,000.00          after the up-front payment
    21 Sep-30 Sep  10 days at r1     8,000.00 (1 + r1)^10
     1 Oct-20 Oct  20 days at r2     8,075.8523 before the 21 October payment
    21 Oct close   5,075.8523        GIC so far 75.8523
    21 Oct-20 Nov  31 days at r2     5,125.7073 before the 21 November payment
    21 Nov close   2,125.7073        GIC so far 125.7073
    21 Nov-20 Dec  30 days at r2     2,145.9093 before the 21 December payment

So the last instalment is $2,145.91, GIC is $145.91 and $10,145.91 is paid. A row
stands at the end of its day, after that day's GIC, except the row that clears the
debt, which accrues none:

    21 Sep  GIC so far    2.5052     balance 8,002.5052
    21 Oct  GIC so far   77.4529     balance 5,077.4529
    21 Nov  GIC so far  126.3777     balance 2,126.3777
    21 Dec  GIC so far  145.9093     cleared
"""

from datetime import date, timedelta
from typing import Any

import pandas as pd
import pytest

from pyfpa.au.gst import monthly_activity_statement_due_date
from pyfpa.au.payment_plan import (
    ESTIMATE_NOTE,
    FLOW_NAME,
    PaymentPlanEstimate,
    PlanFrequency,
    _daily_rate,
    payment_plan_estimate,
    payment_plan_weekly_flows,
)
from pyfpa.au.rates import RateEntry, load_gic_table, rate_at


def _plan(**overrides: Any) -> PaymentPlanEstimate:
    terms: dict[str, Any] = {
        "amount_owed": 10000.0,
        "due_date": date(2026, 9, 21),
        "upfront": 2000.0,
        "upfront_on": date(2026, 9, 21),
        "instalment": 3000.0,
        "first_instalment_on": date(2026, 10, 21),
    }
    return payment_plan_estimate(**(terms | overrides))


def test_the_hand_worked_plan_to_the_cent():
    plan = _plan()
    assert plan.schedule.to_dict("records") == [
        {"period_label": "upfront", "due_date": date(2026, 9, 21), "amount": 2000.0,
         "gic_accrued": 2.51, "closing_balance": 8002.51},
        {"period_label": "instalment 1", "due_date": date(2026, 10, 21), "amount": 3000.0,
         "gic_accrued": 74.94, "closing_balance": 5077.45},
        {"period_label": "instalment 2", "due_date": date(2026, 11, 21), "amount": 3000.0,
         "gic_accrued": 48.93, "closing_balance": 2126.38},
        {"period_label": "instalment 3", "due_date": date(2026, 12, 21), "amount": 2145.91,
         "gic_accrued": 19.53, "closing_balance": 0.0},
    ]
    assert plan.estimated_gic == 145.91
    assert plan.total_paid == 10145.91


def test_a_dated_closing_balance_includes_that_days_gic():
    # 8,000.00 closes 21 September, and that day's GIC at 11.43% / 365 is 2.5052.
    first = _plan().schedule.iloc[0]
    assert (first["gic_accrued"], first["closing_balance"]) == (2.51, 8002.51)


def test_the_payment_that_clears_the_debt_accrues_nothing_that_day():
    # 1 day of GIC on 8,000.00 at 11.43% / 365, then the balance clears on 22 September.
    plan = _plan(first_instalment_on=date(2026, 9, 22), instalment=9000.0)
    assert plan.schedule["gic_accrued"].tolist() == [2.51, 0.0]
    assert plan.schedule["closing_balance"].tolist() == [8002.51, 0.0]


def test_paying_a_balance_rounded_up_from_half_a_cent_clears_it():
    # 3,650.00 at 10.65% / 365 accrues exactly 1.065 on 5 January, so the
    # balance of 3,651.065 rounds up to 3,651.07 and that payment clears it.
    plan = _plan(
        amount_owed=4000.0,
        due_date=date(2026, 1, 5),
        upfront=350.0,
        upfront_on=date(2026, 1, 5),
        instalment=4000.0,
        first_instalment_on=date(2026, 1, 6),
        frequency="weekly",
    )
    assert plan.schedule[["amount", "gic_accrued", "closing_balance"]].values.tolist() == [
        [350.0, 1.07, 3651.07],
        [3651.07, 0.0, 0.0],
    ]
    assert (plan.estimated_gic, plan.total_paid) == (1.07, 4001.07)


def test_the_estimate_is_labelled_and_implies_no_approval():
    plan = _plan()
    assert plan.note == ESTIMATE_NOTE
    assert "Estimate only" in plan.note
    assert "not an ATO approved payment plan" in plan.note
    assert "The ATO decides" in plan.note
    flows = payment_plan_weekly_flows(plan, window_start=date(2026, 9, 21))
    assert all(flow.name.startswith(FLOW_NAME) for flow in flows)
    assert "estimate, not ATO approved" in FLOW_NAME


def test_each_days_gic_comes_after_that_days_payment():
    # A payment on the due date leaves no GIC on what it paid; a day later it does.
    on_time = _plan(upfront=9000.0, instalment=1100.0, first_instalment_on=date(2026, 9, 22))
    late = _plan(upfront=9000.0, upfront_on=date(2026, 9, 22), instalment=1100.0,
                 first_instalment_on=date(2026, 9, 23))
    # 1 day on 1,000.00 at r1 is 31c; 1 day on 10,000.00 at r1 then 1 on 1,003.13 is $3.45.
    assert on_time.estimated_gic == 0.31
    assert late.estimated_gic == 3.45


def test_the_flows_land_in_their_weeks_and_drop_past_the_window():
    flows = payment_plan_weekly_flows(_plan(), window_start=date(2026, 9, 21), weeks=5)
    assert [(flow.name, flow.amount, flow.start_week) for flow in flows] == [
        (f"{FLOW_NAME} upfront", 2000.0, 1),
        (f"{FLOW_NAME} instalment 1", 3000.0, 5),
    ]


@pytest.mark.parametrize(
    ("frequency", "dates"),
    [
        (PlanFrequency.WEEKLY, [date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 19)]),
        (PlanFrequency.FORTNIGHTLY, [date(2026, 10, 5), date(2026, 10, 19), date(2026, 11, 2)]),
        ("weekly", [date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 19)]),
        ("fortnightly", [date(2026, 10, 5), date(2026, 10, 19), date(2026, 11, 2)]),
        ("monthly", [date(2026, 10, 5), date(2026, 11, 5), date(2026, 12, 5)]),
    ],
)
def test_instalments_fall_on_the_chosen_frequency(frequency, dates):
    plan = _plan(first_instalment_on=dates[0], frequency=frequency)
    assert plan.schedule["due_date"].tolist()[1:] == dates


def test_an_unknown_frequency_is_refused():
    with pytest.raises(ValueError, match="not a valid PlanFrequency"):
        _plan(frequency="quarterly")


def test_a_monthly_instalment_on_the_31st_keeps_its_day():
    plan = _plan(first_instalment_on=date(2026, 10, 31))
    assert plan.schedule["due_date"].tolist()[1:] == [date(2026, 10, 31), date(2026, 11, 30), date(2026, 12, 31)]


def test_a_plan_running_past_the_gic_table_is_refused():
    table = load_gic_table()
    assert table.reviewed_until == date(2026, 12, 31)
    with pytest.raises(ValueError, match="verified only to 2026-12-31"):
        _plan(instalment=1000.0)


def test_a_plan_that_never_clears_is_refused():
    with pytest.raises(ValueError, match="verified only to 2026-12-31"):
        _plan(instalment=0.01)


def test_the_published_daily_rates_match_the_table():
    table = load_gic_table()
    assert round(float(_daily_rate(table, date(2026, 3, 31))) * 100, 8) == 0.02917808
    assert round(float(_daily_rate(table, date(2026, 4, 1))) * 100, 8) == 0.03002740
    assert round(float(_daily_rate(table, date(2026, 9, 30))) * 100, 8) == 0.03131507
    assert round(float(_daily_rate(table, date(2026, 10, 1))) * 100, 8) == 0.03153425
    assert rate_at(table, date(2026, 12, 31)) == 0.1151


def test_a_leap_year_divides_by_366():
    table = [RateEntry.model_validate({"from": date(2028, 1, 1), "rate": 0.0732})]
    assert float(_daily_rate(table, date(2028, 1, 1))) == pytest.approx(0.0002)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"amount_owed": 0.0}, "amount_owed"),
        ({"amount_owed": float("nan")}, "amount_owed"),
        ({"amount_owed": float("inf")}, "amount_owed"),
        ({"amount_owed": 100.001}, "amount_owed"),
        ({"upfront": 0.0}, "upfront"),
        ({"instalment": -1.0}, "instalment"),
        ({"upfront": 10000.0}, "needs no payment plan"),
        ({"due_date": date(2026, 9, 26), "upfront_on": date(2026, 9, 26)}, "not a business day"),
        ({"upfront_on": date(2026, 9, 20)}, "before the due date"),
        ({"first_instalment_on": date(2026, 9, 21)}, "after upfront_on"),
        # 1 December 2025 is before the holiday list, so it cannot be shown to be a business day.
        ({"due_date": date(2025, 12, 1), "upfront_on": date(2025, 12, 1)}, "cannot be shown"),
    ],
)
def test_bad_terms_are_refused(overrides, message):
    with pytest.raises(ValueError, match=message):
        _plan(**overrides)


@pytest.mark.parametrize("due", [date(2026, 9, 28), date(2026, 11, 3), date(2026, 12, 24), date(2026, 12, 31)])
def test_a_day_the_ato_lists_but_the_statute_does_not_exclude_is_a_valid_due_date(due):
    plan = _plan(due_date=due, upfront_on=due, first_instalment_on=due + timedelta(days=1), instalment=9000.0)
    assert plan.estimated_gic > 0


def test_a_debt_due_before_july_crosses_the_quarter_at_each_rate():
    # 900.00 closes 30 June at 10.96%, then 900.2702 closes 1 July at 11.43%: GIC 0.5522.
    plan = _plan(amount_owed=1000.0, due_date=date(2026, 6, 30), upfront=100.0, upfront_on=date(2026, 6, 30),
                 instalment=2000.0, first_instalment_on=date(2026, 7, 2))
    assert (plan.estimated_gic, plan.total_paid) == (0.55, 1000.55)


def test_the_count_starts_on_the_effective_date_a_schedule_gives():
    # October's statement is nominally due on Saturday 21 November 2026.
    effective = monthly_activity_statement_due_date(pd.Period("2026-10", freq="M"))
    assert effective == date(2026, 11, 23)
    assert _plan(due_date=effective, upfront_on=effective, first_instalment_on=date(2026, 11, 24),
                 instalment=9000.0).estimated_gic == 2.52  # 1 day on 8,000.00 at r2.
    with pytest.raises(ValueError, match="not a business day"):
        _plan(due_date=date(2026, 11, 21), upfront_on=date(2026, 11, 21))
