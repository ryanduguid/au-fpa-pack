from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import pandas as pd

from pyfpa.backtest.score import (
    DEFAULT_SCORE_LINES,
    DEFAULT_WEIGHTS,
    ScoreResult,
    aggregate_periods,
    extract_lines,
    score_forecast,
)
from pyfpa.config.schemas import EntityConfig
from pyfpa.models.cashflow import cashflow_from_config

BuildCfgFn = Callable[[dict[str, Mapping[str, float]]], EntityConfig]


def holdout_backtest(
    actuals_by_period: Mapping[str, Mapping[str, float]],
    build_cfg_fn: BuildCfgFn,
    *,
    holdout: int,
    score_lines: Sequence[str] = DEFAULT_SCORE_LINES,
    weights: Mapping[str, float] | None = None,
) -> ScoreResult:
    """Fit on all but the last `holdout` months, predict the holdout, and score
    predicted versus the held-out actuals. The business-specific `build_cfg_fn`
    (fit actuals -> a config that forecasts the holdout window) is supplied by the
    caller; this harness only owns the split and the scoring. Nothing is scored on
    data it was fit on. Actual labels must identify unique monthly periods, and
    the generated forecast must cover exactly the held-out months in order."""
    if holdout < 1:
        raise ValueError("holdout must be at least one")
    months = {label: pd.Period(label) for label in actuals_by_period}
    if any(not isinstance(month, pd.Period) or month.freqstr != "M" for month in months.values()):
        raise ValueError("actual periods must be monthly")
    if len(set(months.values())) != len(months):
        raise ValueError("actual periods must be unique months")
    periods = sorted(actuals_by_period, key=months.__getitem__)
    if len(periods) <= holdout:
        raise ValueError(f"need more than {holdout} periods, got {len(periods)}")
    fit_periods = periods[:-holdout]
    holdout_periods = periods[-holdout:]

    fit_actuals: dict[str, Mapping[str, float]] = {
        p: dict(actuals_by_period[p]) for p in fit_periods
    }
    selected_weights = weights if weights is not None else {
        line: DEFAULT_WEIGHTS.get(line, 1.0) for line in score_lines
    }
    # A zero weight disables a metric, so its line is neither extracted nor
    # aggregated: evidence missing for a disabled line must not stop the rest.
    scored = [line for line in score_lines if selected_weights.get(line, 0) > 0]
    cfg = build_cfg_fn(fit_actuals)
    forecast = cashflow_from_config(cfg)
    expected = pd.PeriodIndex([months[period] for period in holdout_periods], freq="M")
    if not forecast.index.equals(expected):
        raise ValueError("forecast periods must match the held-out months")
    predicted = extract_lines(forecast, scored)
    actual = aggregate_periods([dict(actuals_by_period[p]) for p in holdout_periods], scored)
    return score_forecast(predicted, actual, weights=selected_weights)
