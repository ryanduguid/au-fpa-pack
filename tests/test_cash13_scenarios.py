from __future__ import annotations

from datetime import date
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


def test_a_delay_moves_a_monthly_flows_anchor_date() -> None:
    base = Cash13Config(opening_cash=0.0, window_start=date(2026, 11, 2), disbursements=[
        WeeklyFlow(name="Rent", amount=10.0, start_week=1, recurrence="monthly",
                   anchor_date=date(2026, 11, 3))])
    changed = pyfpa.apply_scenario(base, Scenario(
        name="later", disbursements=[FlowChange(name="Rent", delay_weeks=2)]))
    assert changed.disbursements[0].anchor_date == date(2026, 11, 17)

    def weeks_paid(config: Cash13Config) -> list[int]:
        paid = pyfpa.cash13_forecast(config)["disbursements"]
        return [int(week) for week, amount in paid.items() if amount]

    # The 3rd of each month is weeks 1, 5 and 9; the 17th is weeks 3, 7 and 11.
    assert weeks_paid(base) == [1, 5, 9]
    assert weeks_paid(changed) == [3, 7, 11]


def test_a_delay_across_a_month_end_keeps_the_later_day_of_month() -> None:
    base = Cash13Config(opening_cash=0.0, window_start=date(2027, 1, 25), disbursements=[
        WeeklyFlow(name="Loan", amount=10.0, start_week=1, end_week=10, recurrence="monthly",
                   anchor_date=date(2027, 1, 31))])
    changed = pyfpa.apply_scenario(base, Scenario(
        name="later", disbursements=[FlowChange(name="Loan", delay_weeks=1)]))
    late = changed.disbursements[0]
    assert (late.anchor_date, late.start_week, late.end_week) == (date(2027, 2, 7), 2, 11)

    def weeks_paid(config: Cash13Config) -> list[int]:
        paid = pyfpa.cash13_forecast(config)["disbursements"]
        return [int(week) for week, amount in paid.items() if amount]

    # Base: 31 January, 28 February and 31 March (weeks 1, 5 and 10); 30 April
    # is week 14. Delayed: 7 February, 7 March and 7 April (weeks 2, 6 and 11),
    # which the shifted end week 11 keeps.
    assert weeks_paid(base) == [1, 5, 10]
    assert weeks_paid(changed) == [2, 6, 11]
