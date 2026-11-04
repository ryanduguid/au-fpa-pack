from datetime import date

import pytest
from pydantic import ValidationError

from pyfpa.cash13.flows import expand_flow
from pyfpa.cash13.schemas import Cash13Config, WeeklyFlow


def _hits(amounts):
    """Week number to amount for every week the flow lands in."""
    return {week: amount for week, amount in enumerate(amounts, start=1) if amount}


def test_once_hits_single_week():
    f = WeeklyFlow(name="x", amount=200.0, start_week=3, recurrence="once")
    assert expand_flow(f, 5) == [0.0, 0.0, 200.0, 0.0, 0.0]


def test_weekly_spans_to_default_end():
    f = WeeklyFlow(name="x", amount=10.0, start_week=1, recurrence="weekly")
    assert expand_flow(f, 4) == [10.0, 10.0, 10.0, 10.0]


def test_weekly_respects_explicit_end():
    f = WeeklyFlow(name="x", amount=10.0, start_week=2, recurrence="weekly", end_week=3)
    assert expand_flow(f, 5) == [0.0, 10.0, 10.0, 0.0, 0.0]


def test_biweekly_every_other_week():
    f = WeeklyFlow(name="x", amount=5.0, start_week=1, recurrence="biweekly")
    assert expand_flow(f, 6) == [5.0, 0.0, 5.0, 0.0, 5.0, 0.0]


def test_start_week_beyond_horizon_is_empty():
    f = WeeklyFlow(name="x", amount=99.0, start_week=10, recurrence="once")
    assert expand_flow(f, 5) == [0.0, 0.0, 0.0, 0.0, 0.0]


def test_misspelt_weekly_field_is_rejected():
    # F077: end_wek used to load silently, leaving the flow running to the
    # horizon instead of the week the author meant. A config arrives as a
    # mapping, so validate one rather than passing a keyword mypy would catch.
    with pytest.raises(ValidationError):
        WeeklyFlow.model_validate(
            {"name": "x", "amount": 10.0, "start_week": 1, "recurrence": "weekly", "end_wek": 3}
        )


def test_misspelt_weekly_config_field_is_rejected():
    with pytest.raises(ValidationError):
        Cash13Config.model_validate({"opening_cash": 100.0, "weeks": 13, "reciepts": []})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_opening_cash_is_rejected(value):
    # A NaN opening balance made every ending_cash row NaN without an error.
    with pytest.raises(ValidationError, match="finite"):
        Cash13Config.model_validate({"opening_cash": value})


@pytest.mark.parametrize("side", ["receipts", "disbursements"])
@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_weekly_amount_is_rejected(side, value):
    flow = {"name": "x", "amount": value, "start_week": 1}
    with pytest.raises(ValidationError, match="finite"):
        Cash13Config.model_validate({"opening_cash": 100.0, side: [flow]})


@pytest.mark.parametrize(
    ("window_start", "february_week"),
    [
        # 29 February 2028 is 56 days after 4 January: the first day of week 9.
        (date(2028, 1, 4), 9),
        # 28 February 2027 is 55 days after 4 January: the last day of week 8.
        (date(2027, 1, 4), 8),
    ],
)
def test_a_monthly_31st_falls_on_the_last_day_of_february(window_start, february_week):
    flow = WeeklyFlow(name="Rent", amount=10.0, start_week=1, recurrence="monthly",
                      anchor_date=window_start.replace(day=31))
    # 31 January is week 4. March returns to the 31st (week 13) instead of
    # keeping February's day: 28 March 2027 would be week 12.
    assert _hits(expand_flow(flow, 13, window_start)) == {4: 10.0, february_week: 10.0, 13: 10.0}


def test_a_monthly_date_on_a_week_boundary_lands_in_the_week_it_starts():
    # Week 1 runs from Monday 2 November to Sunday 8 November 2026; week 2
    # starts on 9 November, the split gst_weekly_flows uses for a due date.
    window_start = date(2026, 11, 2)
    last_day = WeeklyFlow(name="x", amount=5.0, start_week=1, recurrence="monthly",
                          anchor_date=date(2026, 11, 8))
    first_day = last_day.model_copy(update={"anchor_date": date(2026, 11, 9)})
    assert _hits(expand_flow(last_day, 13, window_start)) == {1: 5.0, 6: 5.0, 10: 5.0}
    assert _hits(expand_flow(first_day, 13, window_start)) == {2: 5.0, 6: 5.0, 10: 5.0}


def test_a_quarterly_flow_anchored_before_the_window_lands_once_inside_it():
    # 20 August is before week 1, 20 November is week 3 and 20 February 2027
    # is week 16, past the 13-week horizon.
    flow = WeeklyFlow(name="Insurance", amount=7.0, start_week=1, recurrence="quarterly",
                      anchor_date=date(2026, 8, 20))
    assert _hits(expand_flow(flow, 13, date(2026, 11, 2))) == {3: 7.0}


def test_monthly_occurrences_never_share_a_week():
    # The closest two are 28 days apart (31 January to 28 February 2027), so a
    # 52-week year puts each of its 11 occurrences in a week of its own. The
    # 12th, 31 December, is week 53 and leaves the horizon.
    flow = WeeklyFlow(name="Rent", amount=3.0, start_week=1, recurrence="monthly",
                      anchor_date=date(2027, 1, 31))
    weeks = [5, 9, 13, 18, 22, 26, 31, 35, 39, 44, 48]
    assert _hits(expand_flow(flow, 52, date(2027, 1, 1))) == dict.fromkeys(weeks, 3.0)


def test_start_and_end_week_bound_a_monthly_flow():
    # 5 November is week 1, before start_week; 5 January is week 10, after end_week.
    flow = WeeklyFlow(name="x", amount=2.0, start_week=3, end_week=9, recurrence="monthly",
                      anchor_date=date(2026, 11, 5))
    assert _hits(expand_flow(flow, 13, date(2026, 11, 2))) == {5: 2.0}


@pytest.mark.parametrize("recurrence", ["monthly", "quarterly"])
def test_a_flow_anchored_in_the_last_month_date_can_hold_lands_once(recurrence):
    # The next date would be in the year 10000, which date cannot hold.
    flow = WeeklyFlow(name="x", amount=4.0, start_week=1, recurrence=recurrence,
                      anchor_date=date(9999, 12, 1))
    assert expand_flow(flow, 1, date(9999, 12, 1)) == [4.0]


def test_anchor_date_comes_with_monthly_and_quarterly_only():
    with pytest.raises(ValidationError, match="anchor_date"):
        WeeklyFlow(name="x", amount=1.0, start_week=1, recurrence="monthly")
    with pytest.raises(ValidationError, match="anchor_date"):
        WeeklyFlow(name="x", amount=1.0, start_week=1, recurrence="weekly",
                   anchor_date=date(2026, 11, 2))


def test_a_monthly_flow_needs_the_window_start():
    flow = {"name": "x", "amount": 1.0, "start_week": 1, "recurrence": "quarterly",
            "anchor_date": "2026-11-02"}
    with pytest.raises(ValidationError, match="window_start"):
        Cash13Config.model_validate({"opening_cash": 0.0, "receipts": [flow]})
    with pytest.raises(ValueError, match="window_start"):
        expand_flow(WeeklyFlow.model_validate(flow), 13)


@pytest.mark.parametrize("recurrence", ["yearly", "fortnightly", "Monthly"])
def test_an_unknown_recurrence_is_refused(recurrence):
    with pytest.raises(ValidationError):
        WeeklyFlow.model_validate(
            {"name": "x", "amount": 1.0, "start_week": 1, "recurrence": recurrence}
        )
