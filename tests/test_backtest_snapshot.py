import pandas as pd
import pytest
import yaml

from pyfpa.backtest.score import score_forecast
from pyfpa.backtest.snapshot import (
    Snapshot,
    load_snapshot,
    save_snapshot,
    snapshot_forecast,
)
from pyfpa.config.schemas import EntityConfig
from pyfpa.models.cashflow import cashflow_from_config


def _cfg():
    return EntityConfig.model_validate({
        "name": "T", "start_month": "2026-01", "horizon_months": 12, "tax_rate": 0.0,
        "channels": [{"name": "C", "annual_revenue": 1_200_000.0, "growth_rate": 0.0,
                      "seasonality": [1.0] * 12, "cogs_pct": 0.5}],
        "opex": [], "debt": [],
        "working_capital": {"dso_days": 0, "dpo_days": 0, "dio_days": 0},
        "opening_balances": {"cash": 0.0},
    })


def test_snapshot_forecast_captures_assumptions_and_predictions():
    cfg = _cfg()
    snap = snapshot_forecast(cfg, cashflow_from_config(cfg),
                             label="2026", created="2026-02-01")
    assert snap.label == "2026"
    assert snap.assumptions["channels"][0]["annual_revenue"] == 1_200_000.0
    assert snap.predicted["revenue"] == pytest.approx(1_200_000.0)
    assert snap.score is None


def test_snapshot_forecast_refuses_incomplete_caller_supplied_evidence():
    cfg = _cfg().model_copy(update={"horizon_months": 2})
    frame = pd.DataFrame({"revenue": [100.0, float("nan")]},
                         index=pd.period_range("2026-01", periods=2, freq="M"))
    with pytest.raises(ValueError, match="finite"):
        snapshot_forecast(cfg, frame, label="Synthetic", created="2026-10-12",
                          score_lines=["revenue"])


@pytest.mark.parametrize("change", ["reversed", "missing", "duplicate", "extra", "year", "daily", "range"])
def test_snapshot_refuses_periods_that_differ_from_the_configuration(change):
    cfg = _cfg()
    frame = cashflow_from_config(cfg)
    if change == "reversed":
        frame = frame.iloc[::-1]
    elif change == "missing":
        frame = frame.iloc[:-1]
    elif change == "duplicate":
        frame.index = pd.PeriodIndex([frame.index[0], *frame.index[:-1]], freq="M")
    elif change == "extra":
        frame = pd.concat([frame, frame.iloc[-1:]])
        frame.index = pd.period_range("2026-01", periods=13, freq="M")
    elif change == "year":
        frame.index = frame.index + 12
    elif change == "daily":
        frame.index = pd.period_range("2026-01-01", periods=12, freq="D")
    else:
        frame = frame.reset_index(drop=True)
    with pytest.raises(ValueError, match="configured months"):
        snapshot_forecast(cfg, frame, label="Synthetic", created="2026-10-17",
                          score_lines=["revenue", "ending_cash"])


def test_snapshot_accepts_selected_columns_with_the_configured_months():
    cfg = _cfg()
    frame = cashflow_from_config(cfg)[["revenue", "ending_cash"]]
    frame.index.name = "month"
    result = snapshot_forecast(cfg, frame, label="Synthetic", created="2026-10-17",
                               score_lines=["revenue", "ending_cash"])
    assert result.predicted["revenue"] == pytest.approx(1_200_000.0)
    assert result.predicted["ending_cash"] == frame.iloc[-1]["ending_cash"]


def test_snapshot_round_trip(tmp_path):
    cfg = _cfg()
    snap = snapshot_forecast(cfg, cashflow_from_config(cfg),
                             label="2026", created="2026-02-01")
    snap = snap.model_copy(update={"score": score_forecast(snap.predicted, snap.predicted)})
    p = tmp_path / "2026.snapshot.yaml"
    save_snapshot(snap, p)
    back = load_snapshot(p)
    assert back.label == "2026"
    assert back.predicted == snap.predicted
    assert back.score is not None
    assert back.score.fitness == pytest.approx(0.0)
    assert back.assumptions == snap.assumptions


@pytest.mark.parametrize("overwrite,destination_exists", [(False, False), (True, False), (True, True)])
def test_snapshot_serialisation_failure_preserves_destination(tmp_path, overwrite, destination_exists):
    path = tmp_path / "forecast.yaml"
    original = Snapshot(label="Original", created="2026-10-09", assumptions={}, predicted={})
    if destination_exists:
        save_snapshot(original, path)
        original_bytes = path.read_bytes()
    invalid = Snapshot(label="Invalid", created="2026-10-09",
                       assumptions={"unsupported": object()}, predicted={})

    with pytest.raises(yaml.representer.RepresenterError):
        save_snapshot(invalid, path, overwrite=overwrite)

    if destination_exists:
        # These pytest outcome assertions are not production input validation.
        assert path.read_bytes() == original_bytes  # nosec B101
        assert load_snapshot(path) == original  # nosec B101
    else:
        assert not path.exists()  # nosec B101: pytest outcome assertion


def test_a_missing_snapshot_is_reported_by_path(tmp_path):
    with pytest.raises(FileNotFoundError, match="snapshot not found: .*absent.yaml"):
        load_snapshot(tmp_path / "absent.yaml")


def test_forecast_snapshots_are_empty_without_a_forecasts_folder(tmp_path):
    from pyfpa.backtest.snapshot import load_forecast_snapshots

    assert load_forecast_snapshots(tmp_path) == ([], [])  # nosec B101: pytest outcome assertion


def test_forecast_snapshots_list_the_files_that_failed_to_parse(tmp_path):
    from pyfpa.backtest.snapshot import load_forecast_snapshots

    forecasts = tmp_path / "forecasts"
    forecasts.mkdir()
    save_snapshot(Snapshot(label="Good", created="2026-10-09", assumptions={}, predicted={}), forecasts / "a.yaml")
    (forecasts / "b.yaml").write_text("label: [unclosed\n", encoding="utf-8")
    snapshots, errors = load_forecast_snapshots(tmp_path)
    assert [snapshot.label for snapshot in snapshots] == ["Good"]  # nosec B101: pytest outcome assertion
    assert len(errors) == 1 and errors[0].startswith("b.yaml: ")  # nosec B101: pytest outcome assertion
