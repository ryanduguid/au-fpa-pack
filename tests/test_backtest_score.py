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


def test_score_forecast_accepts_an_explicit_cash_only_objective():
    res = score_forecast(
        {"ending_cash": 90.0, "ebitda": 30.0},
        {"ending_cash": 100.0, "ebitda": 0.0},
        weights={"ending_cash": 1.0},
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


def test_a_zero_weight_line_no_longer_blocks_scoring():
    # A zero weight is how a caller disables a metric. Requiring complete evidence for
    # it stopped the positive-weight lines being scored at all.
    result = score_forecast(
        {"revenue": 100.0},
        {"revenue": 90.0, "ebitda": 0.0},
        weights={"revenue": 1.0, "ebitda": 0.0},
    )

    assert set(result.weights) == {"revenue"}
    assert "ebitda" not in result.per_line


def test_score_forecast_refuses_overflowed_positive_weight_total():
    with pytest.raises(ValueError, match="weights must sum to a finite number"):
        score_forecast(
            {"revenue": 150.0, "ebitda": 50.0},
            {"revenue": 100.0, "ebitda": 100.0},
            weights={"revenue": 1e308, "ebitda": 1e308},
        )


@pytest.mark.parametrize("weight", [1.0, 1e307])
def test_large_finite_equal_weights_preserve_signed_errors(weight):
    result = score_forecast(
        {"revenue": 150.0, "ebitda": 50.0},
        {"revenue": 100.0, "ebitda": 100.0},
        weights={"revenue": weight, "ebitda": weight},
    )
    revenue_error = (150.0 - 100.0) / 100.0
    ebitda_error = (50.0 - 100.0) / 100.0
    assert result.per_line == {"revenue": revenue_error, "ebitda": ebitda_error}  # nosec B101: pytest outcome assertion
    assert result.weights == {"revenue": 0.5, "ebitda": 0.5}  # nosec B101: pytest outcome assertion
    assert result.fitness == (abs(revenue_error) + abs(ebitda_error)) / 2  # nosec B101: pytest outcome assertion


def test_large_finite_weight_does_not_require_disabled_evidence():
    result = score_forecast(
        {"revenue": 110.0}, {"revenue": 100.0},
        weights={"revenue": 1e308, "absent": 0.0},
    )
    assert result.weights == {"revenue": 1.0}  # nosec B101: pytest outcome assertion
    assert result.fitness == pytest.approx((110.0 - 100.0) / 100.0)  # nosec B101: pytest outcome assertion


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), pd.NA])
@pytest.mark.parametrize("line,column", [
    ("revenue", "revenue"),
    ("gross_margin", "revenue"),
    ("gross_margin", "gross_profit"),
    ("ending_cash", "ending_cash"),
])
def test_extract_lines_refuses_non_finite_selected_values(value, line, column):
    frame = pd.DataFrame({"revenue": [100.0, 100.0], "gross_profit": [40.0, 40.0],
                          "ending_cash": [80.0, 90.0]})
    frame[column] = pd.Series([frame[column].iloc[0], value], dtype=object)
    with pytest.raises(ValueError, match="finite"):
        extract_lines(frame, [line])


@pytest.mark.parametrize("line,column", [
    ("revenue", "revenue"),
    ("gross_margin", "revenue"),
    ("gross_margin", "gross_profit"),
    ("ending_cash", "ending_cash"),
])
def test_extract_lines_reports_missing_selected_columns(line, column):
    frame = _forecast().drop(columns=[column])
    with pytest.raises(ValueError, match="missing"):
        extract_lines(frame, [line])


@pytest.mark.parametrize("line", ["revenue", "gross_margin", "ending_cash"])
def test_extract_lines_refuses_zero_periods(line):
    with pytest.raises(ValueError, match="period"):
        extract_lines(_forecast().iloc[:0], [line])


@pytest.mark.parametrize("columns,line", [
    ({"revenue": [1e308, 1e308]}, "revenue"),
    ({"revenue": [1e308, 1e308], "gross_profit": [1.0, 1.0]}, "gross_margin"),
    ({"revenue": [1.0, 1.0], "gross_profit": [1e308, 1e308]}, "gross_margin"),
    ({"revenue": [1e-308], "gross_profit": [1e308]}, "gross_margin"),
])
def test_extract_lines_refuses_non_finite_aggregates(columns, line):
    with pytest.raises(ValueError, match="finite"):
        extract_lines(pd.DataFrame(columns), [line])


def test_extract_lines_reports_unsupported_selected_values():
    with pytest.raises(ValueError, match="finite"):
        extract_lines(pd.DataFrame({"revenue": ["unsupported"]}), ["revenue"])


def test_extract_lines_refuses_an_integer_total_beyond_float_range():
    # Each integer converts to a finite float, but their exact sum does not.
    frame = pd.DataFrame({"revenue": pd.Series([10**308, 10**308], dtype=object)})
    with pytest.raises(ValueError, match="finite aggregate"):
        extract_lines(frame, ["revenue"])


def test_extract_lines_preserves_explicit_zero_and_final_stock_evidence():
    frame = pd.DataFrame({"revenue": [100.0, 0.0], "ending_cash": [float("nan"), 90.0],
                          "unselected": [pd.NA, pd.NA]})
    assert extract_lines(frame, ["revenue", "ending_cash"]) == {  # nosec B101: pytest outcome assertion
        "revenue": 100.0, "ending_cash": 90.0,
    }


def test_extract_lines_preserves_zero_revenue_margin_convention():
    frame = pd.DataFrame({"revenue": [0.0], "gross_profit": [0.0]})
    assert extract_lines(frame, ["gross_margin"]) == {"gross_margin": 0.0}  # nosec B101: pytest outcome assertion


def test_extract_lines_empty_selection_requires_no_evidence():
    assert extract_lines(pd.DataFrame(), []) == {}  # nosec B101: pytest outcome assertion


@pytest.mark.parametrize("predicted,actual", [
    (1e308, -1e308), (-1e308, 1e308), (1e308, 1e-308),
])
def test_score_forecast_refuses_unsupported_derived_errors(predicted, actual):
    with pytest.raises(ValueError, match="finite"):
        score_forecast({"cash": predicted}, {"cash": actual}, weights={"cash": 1.0})


@pytest.mark.parametrize("error", [float("nan"), float("inf"), -float("inf")])
def test_score_forecast_enforces_its_own_error_postcondition(monkeypatch, error):
    # A faulty reconciliation result must not become a usable score.
    frame = pd.DataFrame({"variance_pct": [error]}, index=["cash"])
    monkeypatch.setattr("pyfpa.backtest.score.reconcile", lambda model, actual: frame)
    with pytest.raises(ValueError, match="cash.*finite"):
        score_forecast({"cash": 110.0}, {"cash": 100.0}, weights={"cash": 1.0})


def test_score_forecast_refuses_an_overflowed_weighted_result():
    import sys

    # Individually finite errors and normalised weights can still round beyond
    # the finite range during their final reduction.
    predicted = {str(i): sys.float_info.max for i in range(11)}
    actual = {line: 1.0 for line in predicted}
    with pytest.raises(ValueError, match="fitness.*finite"):
        score_forecast(predicted, actual, weights=actual)


@pytest.mark.parametrize("periods,lines", [
    ([{"revenue": 1e308}, {"revenue": 1e308}], ["revenue"]),
    ([{"revenue": 1e308, "gross_profit": 1.0}] * 2, ["gross_margin"]),
    ([{"revenue": 1.0, "gross_profit": 1e308}] * 2, ["gross_margin"]),
    ([{"revenue": 0.0, "gross_profit": 1e308}] * 2, ["gross_margin"]),
    ([{"revenue": 1e-308, "gross_profit": 1e308}], ["gross_margin"]),
])
def test_aggregate_periods_refuses_unsupported_totals_and_ratios(periods, lines):
    with pytest.raises(ValueError, match="finite"):
        aggregate_periods(periods, lines)


@pytest.mark.parametrize("periods", [
    [{"revenue": 0.0, "gross_profit": 1.0}],
    [{"revenue": -100.0, "gross_profit": 2.0},
     {"revenue": 100.0, "gross_profit": 2.0}],
])
def test_aggregate_periods_preserves_the_finite_zero_revenue_convention(periods):
    assert aggregate_periods(periods, ["gross_margin"]) == {"gross_margin": 0.0}


def test_disabled_line_does_not_require_supported_arithmetic():
    result = score_forecast(
        {"cash": 110.0, "disabled": 1e308},
        {"cash": 100.0, "disabled": -1e308},
        weights={"cash": 1.0, "disabled": 0.0},
    )
    assert result.fitness == 0.1
    assert result.per_line == {"cash": 0.1}
