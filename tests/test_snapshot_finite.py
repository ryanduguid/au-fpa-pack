import contextlib
import io
import json

import pytest
import yaml

from pyfpa.backtest.score import ScoreResult
from pyfpa.backtest.snapshot import Snapshot, load_snapshot, save_snapshot
from pyfpa.cli import main
from pyfpa.portfolio.recover import best_snapshot

_BAD = [float("nan"), float("inf"), -float("inf")]
_FIELDS = ["predicted", "fitness", "per_line", "weights"]


def _document():
    return {
        "label": "Fabricated AUD forecast", "created": "2026-07-31",
        "assumptions": {"currency": "AUD"}, "predicted": {"ending_cash": 110.0},
        "score": {"fitness": 0.1, "per_line": {"ending_cash": 0.1},
                  "weights": {"ending_cash": 1.0}, "actual_signs": {"ending_cash": 1}},
    }


def _invalid_document(field, value):
    document = _document()
    if field == "predicted":
        document["predicted"]["ending_cash"] = value
    elif field == "fitness":
        document["score"]["fitness"] = value
    else:
        document["score"][field]["ending_cash"] = value
    return document


@pytest.mark.parametrize("value", _BAD)
@pytest.mark.parametrize("field", _FIELDS)
def test_snapshot_creation_refuses_nonfinite_evidence(field, value):
    with pytest.raises(ValueError, match="finite"):
        Snapshot.model_validate(_invalid_document(field, value))


@pytest.mark.parametrize("value", _BAD)
@pytest.mark.parametrize("field", ["fitness", "per_line", "weights"])
def test_score_creation_refuses_nonfinite_evidence(field, value):
    with pytest.raises(ValueError, match="finite"):
        ScoreResult.model_validate(_invalid_document(field, value)["score"])


@pytest.mark.parametrize("value", _BAD)
@pytest.mark.parametrize("field", _FIELDS)
def test_snapshot_load_refuses_nonfinite_evidence(tmp_path, field, value):
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(_invalid_document(field, value)), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="finite"):
        load_snapshot(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("value", _BAD)
@pytest.mark.parametrize("field", _FIELDS)
@pytest.mark.parametrize("change", ["copy", "mutation"])
@pytest.mark.parametrize("overwrite,exists", [(False, False), (True, False), (True, True)])
def test_save_revalidates_changed_evidence_before_opening(tmp_path, field, value, change, overwrite, exists):
    original = Snapshot.model_validate(_document())
    path = tmp_path / "forecast.yaml"
    if exists:
        save_snapshot(original, path)
        before = path.read_bytes()
    altered = original.model_copy(deep=True)
    assert altered.score is not None
    if change == "copy":
        update = _invalid_document(field, value)
        if field == "predicted":
            altered = altered.model_copy(update={"predicted": update["predicted"]})
        else:
            altered = altered.model_copy(update={"score": altered.score.model_copy(update=update["score"])})
    elif field == "predicted":
        altered.predicted["ending_cash"] = value
    elif field == "fitness":
        altered.score.fitness = value
    else:
        getattr(altered.score, field)["ending_cash"] = value
    with pytest.raises(ValueError, match="finite"):
        save_snapshot(altered, path, overwrite=overwrite)
    if exists:
        assert path.read_bytes() == before
        assert load_snapshot(path) == original
    else:
        assert not path.exists()


@pytest.mark.parametrize("value", _BAD)
@pytest.mark.parametrize("field", _FIELDS)
def test_scorecard_reports_nonfinite_snapshot_and_preserves_output(tmp_path, field, value):
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        assert main(["init", str(tmp_path)]) == 0
    memory = tmp_path / ".fpa"
    path = memory / "forecasts" / "invalid.yaml"
    path.write_text(yaml.safe_dump(_invalid_document(field, value)), encoding="utf-8")
    scorecard = memory / "scorecard.md"
    scorecard.write_text("Previous reviewed scorecard\n", encoding="utf-8")
    before = scorecard.read_bytes()
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        status = main(["scorecard-render", str(tmp_path)])
    result = json.loads(captured.getvalue())
    assert status != 0 and not result["ok"]
    assert result["error"]["type"] == "invalid_snapshot"
    assert "invalid.yaml" in result["error"]["message"]
    assert scorecard.read_bytes() == before


@pytest.mark.parametrize("value", _BAD)
def test_best_snapshot_reports_nonfinite_stored_fitness(tmp_path, value):
    forecasts = tmp_path / ".fpa" / "forecasts"
    forecasts.mkdir(parents=True)
    path = forecasts / "invalid.snapshot.yaml"
    path.write_text(yaml.safe_dump(_invalid_document("fitness", value)), encoding="utf-8")
    save_snapshot(Snapshot.model_validate(_document()), forecasts / "valid.snapshot.yaml")
    with pytest.raises(ValueError, match="finite"):
        best_snapshot(tmp_path)


def test_legacy_finite_snapshot_keeps_negative_values_and_missing_actual_signs(tmp_path):
    document = _document()
    document["predicted"]["ending_cash"] = -80.0
    document["score"] = {"fitness": 0.2, "per_line": {"ending_cash": -0.2}, "weights": {}}
    path = tmp_path / "legacy.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    snapshot = load_snapshot(path)
    assert snapshot.predicted == {"ending_cash": -80.0}
    assert snapshot.score is not None
    assert snapshot.score.actual_signs is None
    assert snapshot.score.per_line == {"ending_cash": -0.2}
    save_snapshot(snapshot, tmp_path / "roundtrip.yaml")
    assert load_snapshot(tmp_path / "roundtrip.yaml") == snapshot


@pytest.mark.parametrize("value", _BAD)
@pytest.mark.parametrize("field", ["fitness", "per_line", "weights"])
def test_snapshot_creation_revalidates_an_existing_score(field, value):
    score = ScoreResult.model_validate(_document()["score"])
    score = score.model_copy(update=_invalid_document(field, value)["score"])
    with pytest.raises(ValueError, match="finite"):
        Snapshot.model_validate(_document() | {"score": score})


@pytest.mark.parametrize("value", _BAD)
@pytest.mark.parametrize("field", _FIELDS)
def test_snapshot_validation_revalidates_an_existing_instance(field, value):
    snapshot = Snapshot.model_validate(_document())
    if field == "predicted":
        snapshot.predicted["ending_cash"] = value
    else:
        assert snapshot.score is not None
        snapshot.score = snapshot.score.model_copy(update=_invalid_document(field, value)["score"])
    with pytest.raises(ValueError, match="finite"):
        Snapshot.model_validate(snapshot)
