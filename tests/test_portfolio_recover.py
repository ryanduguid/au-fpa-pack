import pytest

from pyfpa.backtest.score import ScoreResult
from pyfpa.backtest.snapshot import Snapshot, save_snapshot
from pyfpa.portfolio.recover import best_snapshot, recover_actuals


def _snap(label, fitness, predicted, per_line):
    return Snapshot(label=label, created="2026-01-01", assumptions={}, predicted=predicted,
                    score=ScoreResult(fitness=fitness, per_line=per_line, weights={}))


def test_recover_actuals_inverts_error():
    snap = _snap("p", 0.1, {"revenue": 110.0, "ebitda": 90.0}, {"revenue": 0.10, "ebitda": -0.10})
    act = recover_actuals(snap)
    assert act["revenue"] == pytest.approx(100.0)
    assert act["ebitda"] == pytest.approx(100.0)


@pytest.mark.parametrize("predicted", [0.0, None])
def test_recover_actuals_reports_unrecoverable_line(predicted):
    values = {"ebitda": 100.0}
    if predicted is not None:
        values["revenue"] = predicted
    snap = _snap("p", 0.5, values, {"revenue": -1.0, "ebitda": 0.0})
    with pytest.raises(ValueError, match="cannot recover actuals.*revenue"):
        recover_actuals(snap)


def test_recover_actuals_no_score_is_empty():
    snap = Snapshot(label="p", created="2026-01-01", assumptions={}, predicted={"revenue": 1.0})
    assert recover_actuals(snap) == {}


def test_best_snapshot_picks_lowest_fitness(tmp_path):
    forecasts = tmp_path / ".fpa" / "forecasts"
    forecasts.mkdir(parents=True, exist_ok=True)
    save_snapshot(_snap("2026-01", 0.20, {"revenue": 1.0}, {"revenue": 0.0}), forecasts / "a.snapshot.yaml")
    save_snapshot(_snap("2026-02", 0.05, {"revenue": 1.0}, {"revenue": 0.0}), forecasts / "b.snapshot.yaml")
    best = best_snapshot(tmp_path)
    assert best is not None
    assert best.label == "2026-02"


def test_best_snapshot_none_when_unscored_or_missing(tmp_path):
    assert best_snapshot(tmp_path / "nope") is None
    forecasts = tmp_path / ".fpa" / "forecasts"
    forecasts.mkdir(parents=True, exist_ok=True)
    unscored = Snapshot(label="p", created="2026-01-01", assumptions={}, predicted={"revenue": 1.0})
    save_snapshot(unscored, forecasts / "u.snapshot.yaml")
    assert best_snapshot(tmp_path) is None


def test_best_snapshot_ignores_unusable_fitness(tmp_path):
    forecasts = tmp_path / ".fpa" / "forecasts"
    forecasts.mkdir(parents=True, exist_ok=True)
    for name, fitness in (("a", -float("inf")), ("b", float("nan")), ("c", -0.5)):
        save_snapshot(_snap(name, fitness, {"revenue": 1.0}, {"revenue": 0.0}),
                      forecasts / f"{name}.snapshot.yaml")
    assert best_snapshot(tmp_path) is None
    save_snapshot(_snap("d", 0.2, {"revenue": 1.0}, {"revenue": 0.0}), forecasts / "d.snapshot.yaml")
    best = best_snapshot(tmp_path)
    assert best is not None
    assert best.label == "d"


@pytest.mark.parametrize("prediction,error", [
    (1e308, -0.9999999999999999),
    (float("inf"), 0.0),
    (float("nan"), 0.0),
    (100.0, float("inf")),
    (100.0, -float("inf")),
    (100.0, float("nan")),
])
def test_recover_actuals_refuses_unsupported_consumed_evidence(prediction, error):
    snapshot = _snap("p", abs(error), {"cash": prediction}, {"cash": error})
    with pytest.raises(ValueError, match="cash.*finite"):
        recover_actuals(snapshot)


def test_recover_actuals_preserves_finite_zero():
    snapshot = _snap("p", 0.0, {"cash": 0.0}, {"cash": 0.0})
    assert recover_actuals(snapshot) == {"cash": 0.0}


def test_recover_actuals_refuses_an_unchecked_unrepresentable_prediction():
    snapshot = _snap("p", 0.0, {"cash": 100.0}, {"cash": 0.0})
    # The public nested mapping can be mutated after Pydantic construction.
    snapshot.predicted["cash"] = 10**1000
    with pytest.raises(ValueError, match="cash.*finite"):
        recover_actuals(snapshot)
