import pandas as pd
import pytest

from pyfpa.backtest.score import (
    DEFAULT_SCORE_LINES,
    aggregate_periods,
    extract_lines,
    score_forecast,
)


def _forecast():
    idx = pd.period_range("2026-01", periods=3, freq="M")
    return pd.DataFrame({
        "revenue": [100.0, 100.0, 100.0],
        "gross_profit": [40.0, 40.0, 40.0],
        "ebitda": [30.0, 30.0, 30.0],
        "ending_cash": [50.0, 70.0, 90.0],
    }, index=idx)


def test_extract_lines_flow_stock_ratio():
    out = extract_lines(_forecast(), DEFAULT_SCORE_LINES)
    assert out["revenue"] == 300.0
    assert out["ebitda"] == 90.0
    assert out["ending_cash"] == 90.0
    assert out["gross_margin"] == pytest.approx(120.0 / 300.0)


def test_aggregate_periods_matches_extract():
    periods = [
        {"revenue": 100.0, "gross_profit": 40.0, "ebitda": 30.0, "ending_cash": 50.0},
        {"revenue": 100.0, "gross_profit": 40.0, "ebitda": 30.0, "ending_cash": 70.0},
        {"revenue": 100.0, "gross_profit": 40.0, "ebitda": 30.0, "ending_cash": 90.0},
    ]
    out = aggregate_periods(periods, DEFAULT_SCORE_LINES)
    assert out["revenue"] == 300.0
    assert out["ebitda"] == 90.0
    assert out["ending_cash"] == 90.0
    assert out["gross_margin"] == pytest.approx(0.4)


def test_aggregate_periods_rejects_empty_evidence():
    with pytest.raises(ValueError, match="period"):
        aggregate_periods([], DEFAULT_SCORE_LINES)


@pytest.mark.parametrize("periods,lines", [
    ([{"revenue": 100.0}, {}], ["revenue"]),
    ([{"revenue": 100.0, "gross_profit": 40.0}, {"revenue": 100.0}], ["gross_margin"]),
    ([{"ending_cash": 100.0}, {}], ["ending_cash"]),
    ([{"revenue": 100.0}, {"revenue": float("nan")}], ["revenue"]),
    ([{"revenue": float("inf")}], ["revenue"]),
])
def test_aggregate_periods_rejects_incomplete_or_non_finite_evidence(periods, lines):
    with pytest.raises(ValueError, match="missing|finite"):
        aggregate_periods(periods, lines)


def test_aggregate_periods_preserves_explicit_zero_and_final_stock():
    assert aggregate_periods([{"revenue": 100.0}, {"revenue": 0.0}], ["revenue"]) == {"revenue": 100.0}
    assert aggregate_periods([{}, {"ending_cash": 0.0}], ["ending_cash"]) == {"ending_cash": 0.0}


def test_score_forecast_weighted_mape():
    predicted = {"ending_cash": 110.0, "ebitda": 90.0, "revenue": 300.0, "gross_margin": 0.40}
    actual = {"ending_cash": 100.0, "ebitda": 100.0, "revenue": 300.0, "gross_margin": 0.40}
    res = score_forecast(predicted, actual)
    assert res.per_line["ending_cash"] == pytest.approx(0.10)
    assert res.per_line["ebitda"] == pytest.approx(-0.10)
    assert res.per_line["revenue"] == pytest.approx(0.0)
    assert res.fitness == pytest.approx(0.07)


def test_score_forecast_skips_absent_and_zero_actual_lines():
    res = score_forecast(
        {"ending_cash": 90.0, "ebitda": 30.0},
        {"ending_cash": 100.0, "ebitda": 0.0},
    )
    assert set(res.per_line) == {"ending_cash"}
    assert res.weights == {"ending_cash": pytest.approx(1.0)}  # renormalized to the one line
    assert res.fitness == pytest.approx(0.10)


def test_score_forecast_rejects_insufficient_evidence():
    with pytest.raises(ValueError, match="no scorable lines"):
        score_forecast({}, {})
    with pytest.raises(ValueError, match="no scorable lines"):
        score_forecast({"ebitda": 100.0}, {"ebitda": 0.0})


def test_score_forecast_rejects_non_positive_weights():
    with pytest.raises(ValueError, match="weights must sum"):
        score_forecast(
            {"revenue": 100.0},
            {"revenue": 90.0},
            weights={"revenue": 0.0},
        )
