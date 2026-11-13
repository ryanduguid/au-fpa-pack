import pytest
from pydantic import ValidationError

from pyfpa.cash13.forecast import cash13_forecast
from pyfpa.cash13.schemas import Cash13Config, WeeklyFlow


def test_weeklyflow_defaults():
    f = WeeklyFlow(name="Payroll", amount=1000.0, start_week=1)
    assert f.recurrence == "once"
    assert f.end_week is None


def test_weeklyflow_rejects_end_before_start():
    with pytest.raises(ValidationError):
        WeeklyFlow(name="x", amount=1.0, start_week=5, recurrence="weekly", end_week=3)


def test_cash13config_defaults():
    cfg = Cash13Config(opening_cash=500.0)
    assert cfg.weeks == 13
    assert cfg.receipts == []
    assert cfg.disbursements == []


def test_weeklyflow_amount_nonnegative():
    with pytest.raises(ValidationError):
        WeeklyFlow(name="x", amount=-5.0, start_week=1)


def test_forecast_weekly_trajectory():
    cfg = Cash13Config(
        opening_cash=100.0,
        weeks=4,
        receipts=[WeeklyFlow(name="Sales", amount=50.0, start_week=1, recurrence="weekly")],
        disbursements=[
            WeeklyFlow(name="Opex", amount=40.0, start_week=1, recurrence="weekly"),
            WeeklyFlow(name="Rent", amount=200.0, start_week=3, recurrence="once"),
        ],
    )
    df = cash13_forecast(cfg)
    assert list(df.columns) == ["receipts", "disbursements", "net_cash", "ending_cash"]
    assert df.index.tolist() == [1, 2, 3, 4]
    # receipts 50 each week; disb 40,40,240,40
    assert df["receipts"].tolist() == [50.0, 50.0, 50.0, 50.0]
    assert df["disbursements"].tolist() == [40.0, 40.0, 240.0, 40.0]
    # net 10,10,-190,10 ; ending 110,120,-70,-60
    assert df["net_cash"].tolist() == [10.0, 10.0, -190.0, 10.0]
    assert df["ending_cash"].tolist() == [110.0, 120.0, -70.0, -60.0]


def test_forecast_empty_flows_holds_opening_cash():
    cfg = Cash13Config(opening_cash=500.0, weeks=3)
    df = cash13_forecast(cfg)
    assert df["ending_cash"].tolist() == [500.0, 500.0, 500.0]
    assert df["receipts"].sum() == 0.0


def test_forecast_biweekly_and_same_week_merge():
    cfg = Cash13Config(
        opening_cash=0.0,
        weeks=5,
        receipts=[WeeklyFlow(name="Amazon", amount=100.0, start_week=1, recurrence="biweekly")],
        disbursements=[
            WeeklyFlow(name="Overhead", amount=10.0, start_week=1, recurrence="weekly"),
            WeeklyFlow(name="Big bill", amount=50.0, start_week=3, recurrence="once"),
        ],
    )
    df = cash13_forecast(cfg)
    # biweekly receipts hit weeks 1,3,5; overhead 10 every week; big bill 50 merges into wk3
    assert df["receipts"].tolist() == [100.0, 0.0, 100.0, 0.0, 100.0]
    assert df["disbursements"].tolist() == [10.0, 10.0, 60.0, 10.0, 10.0]
    # net: 90,-10,40,-10,90 ; ending: 90,80,120,110,200
    assert df["ending_cash"].tolist() == [90.0, 80.0, 120.0, 110.0, 200.0]


@pytest.mark.parametrize(
    "overrides",
    [
        {"receipts": [{"name": "Sales", "amount": 1e308, "start_week": 1}] * 2},
        {"disbursements": [{"name": "Payroll", "amount": 1e308, "start_week": 1}] * 2},
        {"opening_cash": 1e308, "receipts": [{"name": "Sales", "amount": 1e308, "start_week": 1}]},
        {"opening_cash": -1e308, "disbursements": [{"name": "Payroll", "amount": 1e308, "start_week": 1}]},
        {"weeks": 2, "receipts": [{"name": "Sales", "amount": 1e308, "start_week": 1, "recurrence": "weekly"}]},
        {"opening_cash": 1e308, "facility_limit": 1e308},
        {
            "receipts": [{"name": "Sales", "amount": 1e308, "start_week": 1}] * 2,
            "disbursements": [{"name": "Payroll", "amount": 1e308, "start_week": 1}] * 2,
        },
    ],
    ids=["receipt-total", "payment-total", "cash-positive", "cash-negative", "cumulative-cash", "headroom", "offsetting-totals"],
)
def test_forecast_rejects_arithmetic_overflow(overrides):
    # Every supplied amount is finite; summing them must not publish inf or NaN.
    cfg = Cash13Config.model_validate({"opening_cash": 0.0, "weeks": 1, **overrides})
    with pytest.raises(ValueError, match="non-finite"):
        cash13_forecast(cfg)


def test_forecast_preserves_large_finite_results():
    cfg = Cash13Config(
        opening_cash=1e308,
        weeks=1,
        receipts=[WeeklyFlow(name="Sales", amount=1e307, start_week=1)],
        disbursements=[WeeklyFlow(name="Payroll", amount=1e307, start_week=1)],
        facility_limit=1e307,
    )
    frame = cash13_forecast(cfg)
    assert frame["receipts"].tolist() == [1e307]
    assert frame["disbursements"].tolist() == [1e307]
    assert frame["net_cash"].tolist() == [0.0]
    assert frame["ending_cash"].tolist() == [1e308]
    assert frame["headroom"].tolist() == [1.1e308]
