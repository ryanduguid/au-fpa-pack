import pytest

from pyfpa.cash13.forecast import cash13_forecast
from pyfpa.cash13.runway import runway_summary
from pyfpa.cash13.scenarios import Scenario, compare_scenarios
from pyfpa.cash13.schemas import Cash13Config, WeeklyFlow


def test_runway_identifies_trough_and_first_negative():
    cfg = Cash13Config(
        opening_cash=100.0,
        weeks=4,
        receipts=[WeeklyFlow(name="Sales", amount=50.0, start_week=1, recurrence="weekly")],
        disbursements=[
            WeeklyFlow(name="Opex", amount=40.0, start_week=1, recurrence="weekly"),
            WeeklyFlow(name="Rent", amount=200.0, start_week=3, recurrence="once"),
        ],
    )
    summary = runway_summary(cash13_forecast(cfg))
    # ending cash: 110,120,-70,-60 -> trough -70 at week 3; first negative week 3
    assert summary["min_cash"] == -70.0
    assert summary["min_week"] == 3
    assert summary["first_negative_week"] == 3


def test_runway_none_when_always_positive():
    # Dips at week 2 but never goes negative, so min_week is a real trough (not week 1).
    cfg = Cash13Config(
        opening_cash=1000.0,
        weeks=3,
        receipts=[WeeklyFlow(name="Sales", amount=10.0, start_week=1, recurrence="weekly")],
        disbursements=[WeeklyFlow(name="OneOff", amount=30.0, start_week=2, recurrence="once")],
    )
    summary = runway_summary(cash13_forecast(cfg))
    # ending cash: 1010, 990, 1000 -> trough 990 at week 2; never negative
    assert summary["first_negative_week"] is None
    assert summary["min_cash"] == 990.0
    assert summary["min_week"] == 2


def _lumpy_config(**facility):
    # ending cash: 110, 120, -70, -60
    return Cash13Config(
        opening_cash=100.0,
        weeks=4,
        receipts=[WeeklyFlow(name="Sales", amount=50.0, start_week=1, recurrence="weekly")],
        disbursements=[
            WeeklyFlow(name="Opex", amount=40.0, start_week=1, recurrence="weekly"),
            WeeklyFlow(name="Rent", amount=200.0, start_week=3, recurrence="once"),
        ],
        **facility,
    )


def test_headroom_is_ending_cash_plus_the_facility_limit():
    weekly = cash13_forecast(_lumpy_config(facility_limit=100.0))
    assert weekly["headroom"].tolist() == [210.0, 220.0, 30.0, 40.0]
    # The limit is capacity, not a draw: raw cash is unchanged.
    assert weekly["ending_cash"].tolist() == [110.0, 120.0, -70.0, -60.0]


def test_first_breach_week_tests_headroom_below_zero_by_default():
    within = runway_summary(cash13_forecast(_lumpy_config(facility_limit=100.0)))
    assert within["min_headroom"] == 30.0
    assert within["first_headroom_breach_week"] is None
    over = runway_summary(cash13_forecast(_lumpy_config(facility_limit=60.0)))
    assert over["min_headroom"] == -10.0
    assert over["first_headroom_breach_week"] == 3


def test_first_breach_week_tests_headroom_below_a_stated_buffer():
    weekly = cash13_forecast(_lumpy_config(facility_limit=100.0))
    # Headroom of exactly the buffer is not a breach; a cent less is.
    assert runway_summary(weekly, headroom_buffer=30.0)["first_headroom_breach_week"] is None
    assert runway_summary(weekly, headroom_buffer=30.01)["first_headroom_breach_week"] == 3


def test_a_zero_limit_still_reports_headroom_equal_to_cash():
    summary = runway_summary(cash13_forecast(_lumpy_config(facility_limit=0.0)))
    assert summary["min_headroom"] == -70.0
    assert summary["first_headroom_breach_week"] == 3


def test_without_a_limit_the_forecast_and_summary_are_unchanged():
    weekly = cash13_forecast(_lumpy_config())
    assert "headroom" not in weekly.columns
    assert set(runway_summary(weekly)) == {"min_cash", "min_week", "first_negative_week"}


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf")])
def test_a_bad_limit_or_buffer_is_refused(bad):
    with pytest.raises(ValueError):
        _lumpy_config(facility_limit=bad)
    with pytest.raises(ValueError):
        _lumpy_config(facility_limit=100.0, headroom_buffer=bad)
    if bad != float("inf"):
        weekly = cash13_forecast(_lumpy_config(facility_limit=100.0))
        with pytest.raises(ValueError, match="headroom_buffer"):
            runway_summary(weekly, headroom_buffer=bad)


def test_a_buffer_without_a_limit_is_refused():
    with pytest.raises(ValueError, match="facility_limit"):
        _lumpy_config(headroom_buffer=10.0)


def test_scenarios_carry_the_limit_and_buffer_into_the_comparison():
    cfg = _lumpy_config(facility_limit=100.0, headroom_buffer=50.0)
    frame = compare_scenarios(cfg, [Scenario(name="more rent", add_disbursements=[
        WeeklyFlow(name="Extra", amount=100.0, start_week=4, recurrence="once")])])
    assert frame.loc["base", "first_headroom_breach_week"] == 3
    assert frame.loc["more rent", "min_headroom"] == -60.0
    plain = compare_scenarios(_lumpy_config(), [])
    assert "first_headroom_breach_week" not in plain.columns
