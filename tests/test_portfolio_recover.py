import pytest
import yaml

from pyfpa.backtest.score import ScoreResult, score_forecast
from pyfpa.backtest.snapshot import Snapshot, load_snapshot, save_snapshot
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


def _round_trip(snapshot, tmp_path):
    path = tmp_path / "s.snapshot.yaml"
    save_snapshot(snapshot, path)
    return load_snapshot(path)


def test_recover_actuals_inverts_a_negative_actual(tmp_path):
    # per_line divides by |actual| (#219), so predicted / (1 + error) recovered a
    # loss of 100 forecast as 80 as -66.67.
    predicted = {"net_income": -80.0}
    score = score_forecast(predicted, {"net_income": -100.0}, weights={"net_income": 1.0})
    assert score.per_line == {"net_income": pytest.approx(0.2)}
    snapshot = Snapshot(label="p", created="2026-10-28", assumptions={},
                        predicted=predicted, score=score)
    assert recover_actuals(_round_trip(snapshot, tmp_path)) == {"net_income": pytest.approx(-100.0)}


def test_recover_actuals_inverts_mixed_signs(tmp_path):
    predicted = {"revenue": 100.0, "net_income": -80.0, "ebitda": 50.0, "ending_cash": -10.0}
    actual = {"revenue": 125.0, "net_income": -100.0, "ebitda": -20.0, "ending_cash": 40.0}
    score = score_forecast(predicted, actual, weights=dict.fromkeys(actual, 1.0))
    assert score.actual_signs == {"revenue": 1, "net_income": -1, "ebitda": -1, "ending_cash": 1}
    snapshot = Snapshot(label="p", created="2026-10-28", assumptions={},
                        predicted=predicted, score=score)
    recovered = recover_actuals(_round_trip(snapshot, tmp_path))
    assert recovered == {line: pytest.approx(value) for line, value in actual.items()}


def _v030_snapshot(tmp_path, predicted, actual):
    """A snapshot as 0.3.0 wrote it: no actual_signs, error = predicted / actual - 1."""
    per_line = {line: predicted[line] / actual[line] - 1 for line in actual}
    path = tmp_path / "v030.snapshot.yaml"
    path.write_text(yaml.safe_dump({
        "label": "2026-09", "created": "2026-10-01", "assumptions": {}, "predicted": predicted,
        "score": {"fitness": 0.1, "per_line": per_line, "weights": dict.fromkeys(actual, 0.5)},
    }, sort_keys=False), encoding="utf-8")
    return load_snapshot(path)


def test_v030_snapshot_recovers_lines_both_formulas_agree_on(tmp_path):
    # Positive actuals divide identically either way. A positive forecast of a
    # negative actual has a 0.3.0 error below -1, which no |actual| error can be.
    snapshot = _v030_snapshot(tmp_path, {"revenue": 110.0, "ebitda": 50.0},
                              {"revenue": 100.0, "ebitda": -20.0})
    assert recover_actuals(snapshot) == {"revenue": pytest.approx(100.0),
                                         "ebitda": pytest.approx(-20.0)}


def test_v030_snapshot_refuses_a_line_that_also_fits_another_negative_actual(tmp_path):
    # 0.3.0 stored -0.2 for a loss of 100 forecast as 80. Under |actual| the same
    # error means a loss of 66.67, and the snapshot does not say which build wrote it.
    snapshot = _v030_snapshot(tmp_path, {"revenue": 110.0, "net_income": -80.0},
                              {"revenue": 100.0, "net_income": -100.0})
    with pytest.raises(ValueError, match=r"lines \['net_income'\].*no actual signs"):
        recover_actuals(snapshot)


@pytest.mark.parametrize("actual", [25.0, -50.0])
def test_recorded_sign_resolves_an_error_two_actuals_fit(tmp_path, actual):
    # Forecasting 100 gives error 3 for an actual of 25 and for one of -50.
    predicted = {"ebitda": 100.0}
    score = score_forecast(predicted, {"ebitda": actual}, weights={"ebitda": 1.0})
    assert score.per_line == {"ebitda": pytest.approx(3.0)}
    snapshot = Snapshot(label="p", created="2026-10-28", assumptions={},
                        predicted=predicted, score=score)
    assert recover_actuals(_round_trip(snapshot, tmp_path)) == {"ebitda": pytest.approx(actual)}
    unsigned = snapshot.model_copy(update={"score": score.model_copy(update={"actual_signs": None})})
    with pytest.raises(ValueError, match=r"lines \['ebitda'\].*no actual signs"):
        recover_actuals(unsigned)


def test_recover_actuals_refuses_a_missing_or_contradicted_sign():
    snapshot = Snapshot(label="p", created="2026-10-28", assumptions={},
                        predicted={"revenue": 110.0, "ebitda": 90.0},
                        score=ScoreResult(fitness=0.1, per_line={"revenue": 0.1, "ebitda": -0.1},
                                          weights={}, actual_signs={"revenue": 1}))
    with pytest.raises(ValueError, match=r"cannot recover actuals for lines: \['ebitda'\]"):
        recover_actuals(snapshot)
    assert snapshot.score is not None
    snapshot.score.actual_signs = {"revenue": 1, "ebitda": -1}
    with pytest.raises(ValueError, match=r"lines \['ebitda'\].*recorded sign"):
        recover_actuals(snapshot)
