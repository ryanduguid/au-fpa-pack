# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""The online concession, agent program dates and FBT dates (ATO pages read 5 November 2026)."""

from datetime import date

import pandas as pd
import pytest

from pyfpa.au.fbt import (
    fbt_due_date,
    fbt_nominal_due_date,
    fbt_schedule,
    fbt_weekly_flows,
)
from pyfpa.au.gst import (
    BasCycle,
    GstAssumptions,
    LodgmentChannel,
    bas_schedule,
    monthly_activity_statement_due_date,
    quarterly_bas_due_date,
    quarterly_bas_nominal_due_date,
)
from pyfpa.au.payg_instalments import payg_instalment_schedule
from pyfpa.au.paygw import paygw_due_rule
from pyfpa.au.rates import load_fbt_data

ONLINE = LodgmentChannel.ONLINE
AGENT = LodgmentChannel.AGENT


def _quarter(month: str) -> pd.Period:
    return pd.Period(month, freq="M")


@pytest.mark.parametrize(
    ("quarter", "channel", "due"),
    [
        ("2026-09", LodgmentChannel.ORIGINAL, date(2026, 10, 28)),
        ("2026-09", ONLINE, date(2026, 11, 11)),
        ("2026-09", AGENT, date(2026, 11, 25)),
        ("2027-03", ONLINE, date(2027, 5, 12)),
        ("2027-03", AGENT, date(2027, 5, 26)),
        ("2027-06", ONLINE, date(2027, 8, 11)),
        # Quarter 2 already has its extra month, so neither concession applies.
        ("2026-12", ONLINE, date(2027, 3, 2)),
        ("2026-12", AGENT, date(2027, 3, 2)),
    ],
)
def test_a_quarterly_statement_is_due_on_its_channels_date(quarter, channel, due):
    assert quarterly_bas_due_date(_quarter(quarter), channel) == due


def test_the_online_concession_counts_from_the_original_date_before_any_roll():
    # 28 February is the nominal date under every channel; the roll comes after.
    assert quarterly_bas_nominal_due_date(_quarter("2026-12"), ONLINE) == date(2027, 2, 28)


def test_an_agent_date_the_ato_has_not_confirmed_is_refused():
    # The ATO marks 25 August 2027 'to be confirmed'.
    with pytest.raises(ValueError, match="no agent program date"):
        quarterly_bas_due_date(_quarter("2027-06"), AGENT)


def test_an_agent_date_outside_the_recorded_program_is_refused():
    with pytest.raises(ValueError, match="no agent program date"):
        quarterly_bas_due_date(_quarter("2026-03"), AGENT)


def test_a_schedule_takes_its_channel_from_the_assumptions():
    net = pd.Series(6000.0, index=pd.period_range("2026-07", periods=6, freq="M"))
    schedule = bas_schedule(net, GstAssumptions(lodgment_channel=ONLINE))
    assert schedule["due_date"].tolist() == [date(2026, 11, 11), date(2027, 3, 2)]


def test_the_default_channel_stays_on_the_original_dates():
    assert GstAssumptions().lodgment_channel is LodgmentChannel.ORIGINAL


def test_a_december_monthly_statement_moves_only_when_the_agent_date_applies():
    december = _quarter("2026-12")
    assert monthly_activity_statement_due_date(december) == date(2027, 1, 21)
    # 21 February 2027 is a Sunday.
    assert monthly_activity_statement_due_date(december, december_agent_date=True) == date(2027, 2, 22)
    assert monthly_activity_statement_due_date(_quarter("2026-11"), december_agent_date=True) == date(2026, 12, 21)


def test_a_monthly_schedule_applies_the_december_agent_date():
    net = pd.Series(6000.0, index=pd.period_range("2026-11", periods=2, freq="M"))
    assumptions = GstAssumptions(bas_cycle=BasCycle.MONTHLY, lodgment_channel=AGENT, december_agent_date=True)
    schedule = bas_schedule(net, assumptions)
    assert schedule["nominal_due_date"].tolist() == [date(2026, 12, 21), date(2027, 2, 21)]
    assert schedule["due_date"].tolist() == [date(2026, 12, 21), date(2027, 2, 22)]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"bas_cycle": BasCycle.MONTHLY, "december_agent_date": True},
        {"bas_cycle": BasCycle.QUARTERLY, "lodgment_channel": AGENT, "december_agent_date": True},
    ],
)
def test_the_december_agent_date_is_refused_where_it_cannot_apply(kwargs):
    with pytest.raises(ValueError, match="monthly cycle lodged by an agent"):
        GstAssumptions(**kwargs)


@pytest.mark.parametrize("channel", [ONLINE, AGENT])
def test_a_monthly_cycle_refuses_a_channel_that_would_change_nothing(channel):
    with pytest.raises(ValueError, match="only with december_agent_date"):
        GstAssumptions(bas_cycle=BasCycle.MONTHLY, lodgment_channel=channel)


def test_small_deferred_withholding_follows_the_statement_it_sits_on():
    rule = paygw_due_rule("small", deferred_bas_payer=True, channel=AGENT)
    assert rule(date(2026, 8, 14)) == date(2026, 11, 25)
    # The default keeps the original date.
    assert paygw_due_rule("small", deferred_bas_payer=True)(date(2026, 8, 14)) == date(2026, 10, 28)


@pytest.mark.parametrize(
    ("withholder", "deferred"),
    [("medium", True), ("medium", False), ("small", False)],
)
def test_a_channel_is_refused_for_withholding_outside_a_quarterly_statement(withholder, deferred):
    with pytest.raises(ValueError, match="small withholder that is a deferred BAS payer"):
        paygw_due_rule(withholder, deferred_bas_payer=deferred, channel=ONLINE)


def test_instalments_follow_the_statement_they_sit_on():
    income = pd.Series(1000.0, index=pd.period_range("2026-07", periods=6, freq="M"))
    schedule = payg_instalment_schedule(income, deferred_bas_payer=True, rate=0.05, channel=ONLINE)
    assert schedule["due_date"].tolist() == [date(2026, 11, 11), date(2027, 3, 2)]


def test_a_channel_is_refused_for_instalments_due_on_the_21st():
    income = pd.Series(1000.0, index=pd.period_range("2026-07", periods=6, freq="M"))
    with pytest.raises(ValueError, match="deferred BAS payer"):
        payg_instalment_schedule(income, deferred_bas_payer=False, rate=0.05, channel=ONLINE)


@pytest.mark.parametrize(
    ("channel", "nominal"),
    [
        (LodgmentChannel.ORIGINAL, date(2027, 5, 21)),
        # An employer lodging its own return electronically stays on 21 May.
        (ONLINE, date(2027, 5, 21)),
        (AGENT, date(2027, 6, 25)),
    ],
)
def test_the_fbt_return_and_payment_are_due_on_the_channels_date(channel, nominal):
    assert fbt_nominal_due_date(2027, channel) == nominal
    assert fbt_due_date(2027, channel) == nominal  # Both are Fridays in 2027.


def test_an_fbt_date_on_a_weekend_moves_to_the_next_business_day(monkeypatch):
    data = dict(load_fbt_data(), return_due={"month": 5, "day": 22})  # A Saturday in 2027.
    monkeypatch.setattr("pyfpa.au.fbt.load_fbt_data", lambda: data)
    assert fbt_due_date(2027) == date(2027, 5, 24)


def test_an_fbt_year_past_reviewed_until_is_refused():
    with pytest.raises(ValueError, match="verified only to 2027-03-31"):
        fbt_due_date(2028)


def test_the_fbt_schedule_keeps_both_dates_and_reaches_the_forecast():
    schedule = fbt_schedule(2027, 4200.0, AGENT)
    assert schedule.to_dict("records") == [
        {"period_label": "2027", "nominal_due_date": date(2027, 6, 25),
         "due_date": date(2027, 6, 25), "amount": 4200.0}
    ]
    receipts, disbursements = fbt_weekly_flows(schedule, window_start=date(2027, 6, 21))
    assert receipts == []
    assert [(flow.name, flow.amount, flow.start_week) for flow in disbursements] == [("FBT 2027", 4200.0, 1)]


@pytest.mark.parametrize("channel", [ONLINE, AGENT])
def test_a_channel_passed_as_text_gives_the_same_bas_date(channel):
    quarter = _quarter("2026-09")
    assert quarterly_bas_nominal_due_date(quarter, channel.value) == quarterly_bas_nominal_due_date(quarter, channel)
    assert quarterly_bas_due_date(quarter, channel.value) == quarterly_bas_due_date(quarter, channel)


def test_a_channel_passed_as_text_gives_the_same_fbt_date():
    assert fbt_due_date(2027, "agent") == fbt_due_date(2027, AGENT) == date(2027, 6, 25)
    assert fbt_schedule(2027, 100.0, "agent")["due_date"].tolist() == [date(2027, 6, 25)]


def test_a_channel_passed_as_text_gives_the_same_withholding_date():
    payday = date(2026, 8, 14)
    assert paygw_due_rule("small", deferred_bas_payer=True, channel="agent")(payday) == paygw_due_rule(
        "small", deferred_bas_payer=True, channel=AGENT
    )(payday)
    assert paygw_due_rule("medium", deferred_bas_payer=False, channel="original")(payday) == date(2026, 9, 21)


def test_a_channel_passed_as_text_gives_the_same_instalment_date():
    income = pd.Series(1000.0, index=pd.period_range("2026-07", periods=3, freq="M"))
    as_text = payg_instalment_schedule(income, rate=0.05, deferred_bas_payer=True, channel="agent")
    as_member = payg_instalment_schedule(income, rate=0.05, deferred_bas_payer=True, channel=AGENT)
    assert as_text["due_date"].tolist() == as_member["due_date"].tolist()
    assert payg_instalment_schedule(income, rate=0.05, deferred_bas_payer=False, channel="original").shape[0] == 1


@pytest.mark.parametrize(
    "call",
    [
        lambda: quarterly_bas_nominal_due_date(_quarter("2026-09"), "tax_agent"),
        lambda: quarterly_bas_due_date(_quarter("2026-09"), "tax_agent"),
        lambda: fbt_nominal_due_date(2027, "tax_agent"),
        lambda: fbt_due_date(2027, "tax_agent"),
        lambda: fbt_schedule(2027, 100.0, "tax_agent"),
        lambda: paygw_due_rule("small", deferred_bas_payer=True, channel="tax_agent"),
        lambda: payg_instalment_schedule(
            pd.Series(1000.0, index=pd.period_range("2026-07", periods=3, freq="M")),
            rate=0.05,
            deferred_bas_payer=True,
            channel="tax_agent",
        ),
    ],
)
def test_an_unknown_channel_is_refused(call):
    with pytest.raises(ValueError, match="not a valid LodgmentChannel"):
        call()


def test_an_fbt_refund_stays_in_the_schedule_but_not_the_forecast_without_a_date():
    schedule = fbt_schedule(2027, -300.0)
    assert schedule["amount"].tolist() == [-300.0]
    assert fbt_weekly_flows(schedule, window_start="2027-05-17") == ([], [])


def test_an_fbt_refund_arrives_on_the_date_the_caller_expects():
    receipts, disbursements = fbt_weekly_flows(
        fbt_schedule(2027, -300.0), window_start="2027-05-17", expected_receipt_on=date(2027, 6, 30)
    )
    assert disbursements == []
    assert [(flow.name, flow.amount, flow.start_week) for flow in receipts] == [("FBT 2027", 300.0, 7)]


def test_an_fbt_refund_expected_past_the_window_is_left_out():
    assert fbt_weekly_flows(
        fbt_schedule(2027, -300.0), window_start="2027-05-17", expected_receipt_on=date(2027, 9, 1)
    ) == ([], [])


def test_an_expected_receipt_date_leaves_an_fbt_payment_on_its_due_date():
    receipts, disbursements = fbt_weekly_flows(
        fbt_schedule(2027, 4200.0), window_start="2027-05-17", expected_receipt_on=date(2027, 6, 30)
    )
    assert receipts == []
    assert [(flow.amount, flow.start_week) for flow in disbursements] == [(4200.0, 1)]


@pytest.mark.parametrize("amount", [float("nan"), float("inf")])
def test_an_fbt_amount_must_be_finite(amount):
    with pytest.raises(ValueError, match="finite"):
        fbt_schedule(2027, amount)
