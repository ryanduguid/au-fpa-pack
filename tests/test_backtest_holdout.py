import pytest

from pyfpa.backtest.holdout import holdout_backtest
from pyfpa.config.schemas import EntityConfig


def _actuals():
    out = {}
    cash = 0.0
    for i in range(6):
        cash += 20.0
        out[f"2026-{i+1:02d}"] = {"revenue": 100.0, "gross_profit": 40.0,
                                  "ebitda": 30.0, "ending_cash": cash}
    return out


def _build_cfg(growth):
    def _fn(fit_actuals):
        n = len(fit_actuals)
        last_rev = list(fit_actuals.values())[-1]["revenue"]
        annual = last_rev * 12 * (1 + growth)
        return EntityConfig.model_validate({
            "name": "h", "start_month": f"2026-{n+1:02d}", "horizon_months": 3,
            "tax_rate": 0.0,
            "channels": [{"name": "C", "annual_revenue": annual, "growth_rate": 0.0,
                          "seasonality": [1.0] * 12, "cogs_pct": 0.6}],
            "opex": [], "debt": [],
            "working_capital": {"dso_days": 0, "dpo_days": 0, "dio_days": 0},
            "opening_balances": {"cash": 80.0},
        })
    return _fn


def test_holdout_backtest_scores_holdout():
    res = holdout_backtest(_actuals(), _build_cfg(0.0), holdout=3,
                           score_lines=["revenue", "ebitda"])
    assert set(res.per_line) == {"revenue", "ebitda"}
    assert res.per_line["ebitda"] != 0
    assert res.fitness >= 0.0


def test_a_disabled_line_with_no_evidence_does_not_stop_the_backtest():
    # "headcount" is in neither the actuals nor the forecast. Its zero weight disables
    # it, so the backtest scores revenue instead of failing to extract headcount.
    res = holdout_backtest(_actuals(), _build_cfg(0.0), holdout=3,
                           score_lines=["revenue", "headcount"],
                           weights={"revenue": 1.0, "headcount": 0.0})
    assert set(res.per_line) == {"revenue"}


def test_holdout_discriminates_better_assumption():
    good = holdout_backtest(_actuals(), _build_cfg(0.0), holdout=3, score_lines=["revenue"])
    bad = holdout_backtest(_actuals(), _build_cfg(0.5), holdout=3, score_lines=["revenue"])
    assert good.fitness < bad.fitness


def test_holdout_rejects_too_few_periods():
    with pytest.raises(ValueError):
        holdout_backtest({"2026-01": {"revenue": 1.0}}, _build_cfg(0.0), holdout=3,
                         score_lines=["revenue"])


@pytest.mark.parametrize("holdout", [0, -1])
def test_holdout_rejects_non_positive_window(holdout):
    with pytest.raises(ValueError, match="holdout"):
        holdout_backtest(_actuals(), _build_cfg(0), holdout=holdout)


def test_holdout_uses_chronology_instead_of_insertion_order():
    actuals = _actuals()
    for index, values in enumerate(actuals.values()):
        values["revenue"] = 100 * (index + 1)
    ordered = holdout_backtest(actuals, _build_cfg(0), holdout=3, score_lines=["revenue"])
    shuffled = holdout_backtest(dict(reversed(list(actuals.items()))), _build_cfg(0), holdout=3, score_lines=["revenue"])
    assert shuffled == ordered


@pytest.mark.parametrize("labels", [
    ("2026-01", "2026-1"),
    ("2026-01", "2026-01-01"),
    ("2025-12", "2026Q1"),
    ("2025-12", "2026"),
    ("2025-12", "NaT"),
])
def test_holdout_refuses_ambiguous_or_nonmonthly_periods_before_fitting(labels):
    def build(_):
        pytest.fail("invalid evidence reached the fitting callback")

    actuals = {label: {"revenue": 100.0} for label in labels}
    with pytest.raises(ValueError, match="month"):
        holdout_backtest(actuals, build, holdout=1, score_lines=["revenue"])


@pytest.mark.parametrize("start,horizon", [("2026-01", 1), ("2026-02", 2)])
def test_holdout_refuses_a_forecast_for_different_months(start, horizon):
    cfg = _build_cfg(0)({"2026-01": {"revenue": 100.0}})
    cfg = cfg.model_copy(update={"start_month": start, "horizon_months": horizon})
    actuals = {"2026-01": {"revenue": 100.0}, "2026-02": {"revenue": 100.0}}
    with pytest.raises(ValueError, match="held-out months"):
        holdout_backtest(actuals, lambda _: cfg, holdout=1, score_lines=["revenue"])


def test_holdout_refuses_gaps_in_held_out_months():
    cfg = _build_cfg(0)({"2026-01": {"revenue": 100.0}})
    cfg = cfg.model_copy(update={"start_month": "2026-03", "horizon_months": 2})
    actuals = {month: {"revenue": 100.0} for month in ("2026-01", "2026-03", "2026-05")}
    with pytest.raises(ValueError, match="held-out months"):
        holdout_backtest(actuals, lambda _: cfg, holdout=2, score_lines=["revenue"])


def test_holdout_allows_training_gaps_and_preserves_original_month_labels():
    cfg = _build_cfg(0)({"2026-01": {"revenue": 100.0}})
    cfg = cfg.model_copy(update={"start_month": "2026-02", "horizon_months": 1})
    seen = {}

    def build(fit):
        seen.update(fit)
        return cfg

    actuals = {month: {"revenue": 100.0} for month in ("2026-02", "2025/01", "2026-1")}
    result = holdout_backtest(actuals, build, holdout=1, score_lines=["revenue"])
    assert list(seen) == ["2025/01", "2026-1"]
    assert result.fitness == 0
