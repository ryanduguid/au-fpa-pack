from __future__ import annotations

import math

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from pyfpa.cash13.forecast import cash13_forecast
from pyfpa.cash13.runway import runway_summary
from pyfpa.cash13.schemas import Cash13Config, WeeklyFlow

_STRICT = ConfigDict(extra="forbid")


class FlowChange(BaseModel):
    """Change every base flow of one name: scale its amount, push it later, or both.

    A flow pushed past the horizon leaves the forecast, which is what a slipped
    receipt does to a 13-week view."""

    model_config = _STRICT

    name: str
    amount_factor: float = Field(default=1.0, ge=0, allow_inf_nan=False)
    delay_weeks: int = Field(default=0, ge=0)


class Scenario(BaseModel):
    """A named set of declared changes to a base 13-week forecast."""

    model_config = _STRICT

    name: str
    receipts: list[FlowChange] = Field(default_factory=list)
    disbursements: list[FlowChange] = Field(default_factory=list)
    add_receipts: list[WeeklyFlow] = Field(default_factory=list)
    add_disbursements: list[WeeklyFlow] = Field(default_factory=list)


def _changed(flows: list[WeeklyFlow], changes: list[FlowChange], side: str) -> list[WeeklyFlow]:
    by_name = {change.name: change for change in changes}
    if len(by_name) != len(changes):
        raise ValueError(f"a scenario changes one {side} name more than once")
    unknown = sorted(set(by_name) - {flow.name for flow in flows})
    if unknown:
        # A misspelt name would otherwise leave the scenario identical to the base.
        raise ValueError(f"no base {side} named {', '.join(map(repr, unknown))}")
    result = []
    for flow in flows:
        change = by_name.get(flow.name)
        if change is None:
            result.append(flow)
            continue
        amount = flow.amount * change.amount_factor
        if not math.isfinite(amount):
            raise ValueError(f"scaling {side} {flow.name!r} by {change.amount_factor} is not a finite amount")
        result.append(flow.model_copy(update={
            "amount": amount,
            "start_week": flow.start_week + change.delay_weeks,
            "end_week": None if flow.end_week is None else flow.end_week + change.delay_weeks,
        }))
    return result


def apply_scenario(cfg: Cash13Config, scenario: Scenario) -> Cash13Config:
    """Return the base config with the scenario's changes and additions applied."""
    return cfg.model_copy(update={
        "receipts": _changed(cfg.receipts, scenario.receipts, "receipt") + scenario.add_receipts,
        "disbursements": (_changed(cfg.disbursements, scenario.disbursements, "disbursement")
                          + scenario.add_disbursements),
    })


def compare_scenarios(cfg: Cash13Config, scenarios: list[Scenario]) -> pd.DataFrame:
    """One row per scenario, base first: cash trough, its week, first negative week, closing cash."""
    names = [scenario.name for scenario in scenarios]
    if "base" in names or len(set(names)) != len(names):
        raise ValueError("scenario names must be unique and must not be 'base'")
    rows = []
    for name, config in [("base", cfg)] + [(s.name, apply_scenario(cfg, s)) for s in scenarios]:
        weekly = cash13_forecast(config)
        rows.append({"scenario": name, **runway_summary(weekly),
                     "ending_cash": float(weekly["ending_cash"].iloc[-1])})
    # Nullable integer, so a scenario that never goes negative reads as missing, not NaN.
    return pd.DataFrame(rows).astype({"first_negative_week": "Int64"}).set_index("scenario")
