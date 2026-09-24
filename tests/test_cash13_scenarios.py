from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

import pyfpa
from pyfpa import Cash13Config, FlowChange, Scenario, WeeklyFlow

RIDGELINE = Path(__file__).resolve().parents[1] / "examples" / "ridgeline"


def _base() -> Cash13Config:
    return Cash13Config(
        opening_cash=100.0,
        weeks=4,
        receipts=[
            WeeklyFlow(name="Sales", amount=50.0, start_week=1, recurrence="weekly"),
            WeeklyFlow(name="Debtor", amount=200.0, start_week=2),
            WeeklyFlow(name="Debtor", amount=100.0, start_week=4),
        ],
        disbursements=[WeeklyFlow(name="Rent", amount=120.0, start_week=1, recurrence="weekly")],
    )


def test_a_delay_moves_every_flow_of_that_name_and_can_leave_the_horizon() -> None:
    changed = pyfpa.apply_scenario(_base(), Scenario(
        name="late", receipts=[FlowChange(name="Debtor", delay_weeks=2)]))
    debtors = [flow for flow in changed.receipts if flow.name == "Debtor"]
    assert [flow.start_week for flow in debtors] == [4, 6]
    weekly = pyfpa.cash13_forecast(changed)
    # Week 6 is past the 4-week horizon, so only the first debtor arrives, in week 4.
    assert weekly["receipts"].tolist() == [50.0, 50.0, 50.0, 250.0]


def test_a_factor_scales_and_additions_append_without_touching_the_base() -> None:
    base = _base()
    changed = pyfpa.apply_scenario(base, Scenario(
        name="down",
        receipts=[FlowChange(name="Sales", amount_factor=0.5)],
        add_disbursements=[WeeklyFlow(name="Hire", amount=30.0, start_week=3, recurrence="weekly")],
    ))
    weekly = pyfpa.cash13_forecast(changed)
    assert weekly["receipts"].tolist() == [25.0, 225.0, 25.0, 125.0]
    assert weekly["disbursements"].tolist() == [120.0, 120.0, 150.0, 150.0]
    assert [flow.amount for flow in base.receipts] == [50.0, 200.0, 100.0]


def test_compare_lists_base_first_with_trough_and_closing_cash() -> None:
    table = pyfpa.compare_scenarios(_base(), [
        Scenario(name="late", receipts=[FlowChange(name="Debtor", delay_weeks=2)]),
    ])
    assert table.index.tolist() == ["base", "late"]
    # Base: 100 +50-120=30, +250-120=160, +50-120=90, +150-120=120.
    base = table.loc["base"]
    assert (base["min_cash"], base["min_week"], base["ending_cash"]) == (30.0, 1, 120.0)
    assert pd.isna(base["first_negative_week"])
    # Late: 30, -40, -110, +130 -> 20.
    late = table.loc["late"]
    assert (late["min_cash"], late["min_week"], late["first_negative_week"], late["ending_cash"]) == (
        -110.0, 3, 2, 20.0)


@pytest.mark.parametrize(
    "scenario",
    [
        Scenario(name="typo", receipts=[FlowChange(name="Debtors", delay_weeks=1)]),
        Scenario(name="wrong side", disbursements=[FlowChange(name="Sales", amount_factor=0)]),
        Scenario(name="twice", receipts=[FlowChange(name="Sales"), FlowChange(name="Sales")]),
    ],
)
def test_an_unmatched_or_repeated_change_is_refused(scenario: Scenario) -> None:
    with pytest.raises(ValueError):
        pyfpa.apply_scenario(_base(), scenario)


def test_scenario_names_must_be_unique_and_not_base() -> None:
    with pytest.raises(ValueError):
        pyfpa.compare_scenarios(_base(), [Scenario(name="base")])
    with pytest.raises(ValueError):
        pyfpa.compare_scenarios(_base(), [Scenario(name="a"), Scenario(name="a")])


def test_negative_changes_and_unknown_keys_fail_validation() -> None:
    with pytest.raises(ValidationError):
        FlowChange(name="Sales", amount_factor=-1)
    with pytest.raises(ValidationError):
        FlowChange(name="Sales", delay_weeks=-1)
    for factor in (float("inf"), float("nan")):
        with pytest.raises(ValidationError):
            FlowChange(name="Sales", amount_factor=factor)


def test_a_factor_that_overflows_the_amount_is_refused() -> None:
    base = Cash13Config(opening_cash=0.0, receipts=[WeeklyFlow(name="Big", amount=1e308, start_week=1)])
    with pytest.raises(ValueError, match="not a finite amount"):
        pyfpa.apply_scenario(base, Scenario(name="x", receipts=[FlowChange(name="Big", amount_factor=10)]))
    with pytest.raises(ValidationError):
        Scenario.model_validate({"name": "x", "recipts": []})


def test_the_ridgeline_example_scenarios_load_and_compare() -> None:
    config = pyfpa.load_cash13_config(RIDGELINE / "cash13.yaml")
    scenarios = pyfpa.load_cash13_scenarios(RIDGELINE / "scenarios.yaml")
    table = pyfpa.compare_scenarios(config, scenarios)
    assert table.index.tolist() == [
        "base", "Wholesale pays 5 weeks late", "D2C sales 20 per cent down", "Hire two staff from week 5"]
    for name in table.index[1:]:
        assert table.loc[name, "ending_cash"] < table.loc["base", "ending_cash"]


def test_a_delay_moves_the_end_week_with_the_start() -> None:
    base = Cash13Config(opening_cash=0.0, weeks=6, disbursements=[
        WeeklyFlow(name="Lease", amount=10.0, start_week=1, recurrence="weekly", end_week=3)])
    changed = pyfpa.apply_scenario(base, Scenario(
        name="later", disbursements=[FlowChange(name="Lease", delay_weeks=2)]))
    assert pyfpa.cash13_forecast(changed)["disbursements"].tolist() == [0.0, 0.0, 10.0, 10.0, 10.0, 0.0]
