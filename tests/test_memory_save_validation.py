import json

import pytest

from pyfpa.cli import main
from pyfpa.memory.corrections import Correction, Override, save_correction
from pyfpa.memory.experiments import (
    Experiment,
    ExperimentCheck,
    ExperimentDecision,
    load_experiment,
    save_experiment,
)
from pyfpa.memory.intake import (
    Intake,
    load_intake,
    record_intake_fact,
    save_intake,
)
from pyfpa.memory.workspace import initialize_workspace

_NONFINITE = [float("nan"), float("inf"), -float("inf")]
_INVALID_CONFIDENCE = [-0.1, 1.1, *_NONFINITE]


def _intake():
    return record_intake_fact(
        Intake(business_name="Fabricated AUD company"),
        key="financing",
        answer="AUD 125,000 overdraft limit",
        source_type="local_file",
        sources=["company-data/aud-facility.md"],
        confidence=0.9,
    )


def _experiment():
    return Experiment(
        slug="2026-07-aud-cash",
        created="2026-07-01",
        status="accepted",
        hypothesis="Fabricated AUD collections evidence reduces forecast error.",
        evidence=["fixtures/aud-source.csv"],
        files_changed=["models/generated/aud_cash.py"],
        metrics_before={"ending_cash_wape": 0.18},
        metrics_after={"ending_cash_wape": 0.07},
        checks=[ExperimentCheck(name="cash reconciliation", result="pass")],
        decision=ExperimentDecision(
            outcome="accepted", decided_by="Synthetic reviewer", decided_at="2026-07-01"
        ),
    )


@pytest.mark.parametrize("relation", ["new", "matching", "conflicting"])
@pytest.mark.parametrize("confidence", _INVALID_CONFIDENCE)
def test_record_intake_refuses_invalid_incoming_confidence(relation, confidence):
    intake = Intake() if relation == "new" else _intake()
    before = intake.model_dump_json()
    answer = "AUD 175,000 overdraft limit" if relation == "conflicting" else "AUD 125,000 overdraft limit"
    with pytest.raises(ValueError, match="confidence"):
        record_intake_fact(
            intake, key="financing", answer=answer,
            source_type="local_file", confidence=confidence,
        )
    assert intake.model_dump_json() == before


@pytest.mark.parametrize("confidence", _INVALID_CONFIDENCE)
def test_save_intake_revalidates_nested_confidence_before_writing(tmp_path, confidence):
    intake = _intake()
    path = tmp_path / "intake.md"
    save_intake(intake, path)
    before = path.read_bytes()
    intake.facts[0].confidence = confidence
    with pytest.raises(ValueError, match="confidence"):
        save_intake(intake, path)
    assert path.read_bytes() == before
    assert load_intake(path) == _intake()


@pytest.mark.parametrize("relation,confidence", [("matching", 1.1), ("conflicting", -0.1)])
def test_cli_invalid_intake_update_preserves_saved_evidence(tmp_path, capsys, relation, confidence):
    workspace = initialize_workspace(tmp_path)
    path = workspace / "intake.md"
    save_intake(_intake(), path)
    before = path.read_bytes()
    answer = "AUD 175,000 overdraft limit" if relation == "conflicting" else "AUD 125,000 overdraft limit"
    code = main([
        "intake-record", str(tmp_path), "--key", "financing", "--answer", answer,
        "--source-type", "local_file", "--confidence", str(confidence),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"]["type"] == "invalid_intake_fact"
    assert path.read_bytes() == before
    assert load_intake(path) == _intake()


@pytest.mark.parametrize("field", ["evidence", "files_changed", "checks", "decision"])
def test_save_experiment_revalidates_mutated_ratification(tmp_path, field):
    experiment = _experiment()
    path = save_experiment(experiment, tmp_path)
    before = path.read_bytes()
    if field == "decision":
        assert experiment.decision is not None
        experiment.decision.outcome = "rejected"
    else:
        getattr(experiment, field).clear()
    with pytest.raises(ValueError):
        save_experiment(experiment, tmp_path, overwrite=True)
    assert path.read_bytes() == before
    assert load_experiment(path) == _experiment()


@pytest.mark.parametrize("field", ["metrics_before", "metrics_after"])
@pytest.mark.parametrize("value", _NONFINITE)
def test_experiment_metrics_must_be_finite(field, value):
    data = _experiment().model_dump()
    data[field]["ending_cash_wape"] = value
    with pytest.raises(ValueError, match="finite"):
        Experiment.model_validate(data)


@pytest.mark.parametrize("value", _NONFINITE)
def test_save_experiment_revalidates_nested_metrics(tmp_path, value):
    experiment = _experiment()
    path = save_experiment(experiment, tmp_path)
    before = path.read_bytes()
    experiment.metrics_after["ending_cash_wape"] = value
    with pytest.raises(ValueError, match="finite"):
        save_experiment(experiment, tmp_path, overwrite=True)
    assert path.read_bytes() == before


def test_save_correction_revalidates_mutated_status(tmp_path):
    correction = Correction(
        slug="2026-07-aud-revenue", type="parametric",
        target="channels[0].annual_revenue", status="applied", date="2026-07-01",
        override=Override(path="channels[0].annual_revenue", value=24000),
    )
    save_correction(correction, tmp_path)
    path = tmp_path / f"{correction.slug}.md"
    before = path.read_bytes()
    invalid = correction.model_copy(update={"status": "invalid status"})
    with pytest.raises(ValueError):
        save_correction(invalid, tmp_path, overwrite=True)
    assert path.read_bytes() == before
