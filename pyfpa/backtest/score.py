from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import pandas as pd
from pydantic import BaseModel

from pyfpa.analysis.reconcile import reconcile

DEFAULT_SCORE_LINES = ["ending_cash", "ebitda", "revenue", "gross_margin"]
DEFAULT_WEIGHTS = {"ending_cash": 0.4, "ebitda": 0.3, "revenue": 0.2, "gross_margin": 0.1}


def _forecast_values(
    forecast_df: pd.DataFrame, column: str, *, final_only: bool = False
) -> pd.Series:
    if column not in forecast_df.columns:
        raise ValueError(f"forecast is missing {column!r}")
    values = forecast_df[column]
    if values.empty:
        raise ValueError("at least one forecast period is required")
    if final_only:
        values = values.iloc[-1:]
    try:
        finite = not values.isna().any() and all(math.isfinite(value) for value in values)
    except (TypeError, ValueError, OverflowError):
        finite = False
    if not finite:
        raise ValueError(f"forecast {column!r} must contain finite numeric values")
    if pd.api.types.is_integer_dtype(values):
        # Fixed-width integer sums wrap silently; Python integers keep the exact total.
        return values.astype(object)
    return values


def extract_lines(forecast_df: pd.DataFrame, score_lines: Sequence[str]) -> dict[str, float]:
    """Reduce a monthly forecast to a {line: value} dict for scoring.

    `ending_cash` is a stock (take the last month); `gross_margin` is a ratio
    (Σ gross_profit / Σ revenue); every other line is a flow (sum).
    Selected evidence and aggregates must be finite. Stocks require only the
    final period. Fully observed zero revenue retains the zero-margin convention.
    """
    out: dict[str, float] = {}
    for line in score_lines:
        try:
            if line == "ending_cash":
                out[line] = float(_forecast_values(forecast_df, line, final_only=True).iloc[-1])
            elif line == "gross_margin":
                revenue = float(_forecast_values(forecast_df, "revenue").sum())
                gp = float(_forecast_values(forecast_df, "gross_profit").sum())
                if not math.isfinite(revenue) or not math.isfinite(gp):
                    raise ValueError("forecast gross_margin must have finite totals")
                out[line] = (gp / revenue) if revenue else 0.0
            else:
                out[line] = float(_forecast_values(forecast_df, line).sum())
        except (TypeError, OverflowError) as error:
            raise ValueError(f"forecast {line!r} must have a finite aggregate") from error
        if not math.isfinite(out[line]):
            raise ValueError(f"forecast {line!r} must have a finite aggregate")
    return out


def aggregate_periods(
    period_dicts: Sequence[Mapping[str, float]], score_lines: Sequence[str]
) -> dict[str, float]:
    """Aggregate a chronological list of per-period actual dicts the same way
    `extract_lines` aggregates a forecast (flow=sum, stock=last, ratio=ΣGP/Σrev).

    Every flow and ratio input must be present and finite in every period;
    stocks require the final period's value. Missing evidence is never zero.
    Required totals and returned aggregates must also be finite.
    """
    if not period_dicts:
        raise ValueError("at least one actual period is required")
    required = set(score_lines) - {"ending_cash", "gross_margin"}
    if "gross_margin" in score_lines:
        required.update(("revenue", "gross_profit"))
    for index, period in enumerate(period_dicts):
        fields = required.copy()
        if "ending_cash" in score_lines and index == len(period_dicts) - 1:
            fields.add("ending_cash")
        for field in fields:
            if field not in period:
                raise ValueError(f"actual period {index + 1} is missing {field!r}")
            if not math.isfinite(period[field]):
                raise ValueError(f"actual period {index + 1} {field!r} must be finite")
    out: dict[str, float] = {}
    for line in score_lines:
        if line == "ending_cash":
            out[line] = float(period_dicts[-1]["ending_cash"])
        elif line == "gross_margin":
            revenue = sum(float(d["revenue"]) for d in period_dicts)
            gp = sum(float(d["gross_profit"]) for d in period_dicts)
            if not math.isfinite(revenue) or not math.isfinite(gp):
                raise ValueError("actual gross_margin must have finite totals")
            out[line] = (gp / revenue) if revenue else 0.0
        else:
            out[line] = sum(float(d[line]) for d in period_dicts)
        if not math.isfinite(out[line]):
            raise ValueError(f"actual {line!r} must have a finite aggregate")
    return out


class ScoreResult(BaseModel):
    fitness: float                       # weighted MAPE across scored lines; lower is better
    per_line: dict[str, float]           # signed error %, predicted/actual - 1
    weights: dict[str, float]            # the (renormalized) weights actually used


def score_forecast(
    predicted: Mapping[str, float],
    actual: Mapping[str, float],
    *,
    weights: Mapping[str, float] | None = None,
) -> ScoreResult:
    """Weighted MAPE requiring complete, finite evidence for every weighted line.

    Relative error is undefined for a zero actual; callers must choose an
    explicit alternative objective instead of silently omitting that line.
    Active relative errors and returned fitness must be finite.
    Every positive input weight must retain a positive normalised coefficient.
    """
    weights = dict(DEFAULT_WEIGHTS if weights is None else weights)
    if any(not math.isfinite(weight) or weight < 0 for weight in weights.values()):
        raise ValueError("scoring weights must be finite and non-negative")
    # A zero weight is how a caller disables a metric, and the docstring asks for
    # complete evidence for every *weighted* line. Requiring it for a zero-weight line
    # stopped otherwise scorable evidence being evaluated at all.
    lines = [line for line in weights if weights[line] > 0]
    if not lines:
        raise ValueError("scoring weights must sum to a positive value")
    unscorable = [line for line in lines if line not in predicted or line not in actual
                  or actual[line] == 0 or not math.isfinite(actual[line])
                  or not math.isfinite(predicted[line])]
    if unscorable:
        raise ValueError(f"no scorable lines for requested evidence: {unscorable}")
    rec = reconcile({line: predicted[line] for line in lines},
                    {line: actual[line] for line in lines})
    per_line = {line: float(rec.loc[line, "variance_pct"]) for line in lines}
    for line, error in per_line.items():
        if not math.isfinite(error):
            raise ValueError(f"scoring error for {line!r} must be finite")
    total_w = sum(weights[line] for line in lines)
    if not math.isfinite(total_w):
        raise ValueError("scoring weights must sum to a finite number")
    # Unreachable: every weight in lines is positive, so their sum is too.
    if total_w <= 0:  # pragma: no cover
        raise ValueError("scoring weights must sum to a positive value")
    used = {line: weights[line] / total_w for line in lines}
    for line, weight in used.items():
        if weight == 0.0:
            raise ValueError(
                f"positive scoring weight for {line!r} rounds to zero during normalisation"
            )
    fitness = sum(used[line] * abs(per_line[line]) for line in lines)
    if not math.isfinite(fitness):
        raise ValueError("scoring fitness must be finite")
    return ScoreResult(fitness=fitness, per_line=per_line, weights=used)
