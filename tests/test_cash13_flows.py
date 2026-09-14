import pytest
from pydantic import ValidationError

from pyfpa.cash13.flows import expand_flow
from pyfpa.cash13.schemas import Cash13Config, WeeklyFlow


def test_once_hits_single_week():
    f = WeeklyFlow(name="x", amount=200.0, start_week=3, recurrence="once")
    assert expand_flow(f, 5) == [0.0, 0.0, 200.0, 0.0, 0.0]


def test_weekly_spans_to_default_end():
    f = WeeklyFlow(name="x", amount=10.0, start_week=1, recurrence="weekly")
    assert expand_flow(f, 4) == [10.0, 10.0, 10.0, 10.0]


def test_weekly_respects_explicit_end():
    f = WeeklyFlow(name="x", amount=10.0, start_week=2, recurrence="weekly", end_week=3)
    assert expand_flow(f, 5) == [0.0, 10.0, 10.0, 0.0, 0.0]


def test_biweekly_every_other_week():
    f = WeeklyFlow(name="x", amount=5.0, start_week=1, recurrence="biweekly")
    assert expand_flow(f, 6) == [5.0, 0.0, 5.0, 0.0, 5.0, 0.0]


def test_start_week_beyond_horizon_is_empty():
    f = WeeklyFlow(name="x", amount=99.0, start_week=10, recurrence="once")
    assert expand_flow(f, 5) == [0.0, 0.0, 0.0, 0.0, 0.0]


def test_misspelt_weekly_field_is_rejected():
    # F077: end_wek used to load silently, leaving the flow running to the
    # horizon instead of the week the author meant.
    with pytest.raises(ValidationError):
        WeeklyFlow(name="x", amount=10.0, start_week=1, recurrence="weekly", end_wek=3)


def test_misspelt_weekly_config_field_is_rejected():
    with pytest.raises(ValidationError):
        Cash13Config(opening_cash=100.0, weeks=13, reciepts=[])
