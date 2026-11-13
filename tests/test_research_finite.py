"""Finite research evidence and stable financial ranking contracts."""
from __future__ import annotations

import copy

import pytest
import yaml

from pyfpa.memory.experiments import ExperimentCheck
from pyfpa.research.epochs import (
    EpochEvaluation,
    ResearchEpoch,
    evaluate_challenger,
    load_epoch,
    save_epoch,
)
from pyfpa.research.objective import (
    MetricObjective,
    ResearchObjective,
    load_research_objective,
    save_research_objective,
)
from pyfpa.research.registry import (
    ModelRegistry,
    ModelVersion,
    promote_challenger,
)

NONFINITE = [float("nan"), float("inf"), -float("inf")]
CONTROLS = ["weight", "min_improvement", "complexity_penalty", "max_metric_regression"]
EVIDENCE = [
    "champion_metrics", "challenger_metrics", "per_metric_improvement",
    "weighted_improvement", "complexity_cost", "objective_gain",
    "champion_complexity", "challenger_complexity",
]


def _objective() -> ResearchObjective:
    return ResearchObjective(metrics=[MetricObjective(name="error", weight=1)])


def _evaluation() -> EpochEvaluation:
    return evaluate_challenger(_objective(), {"error": 100}, {"error": 80}, [])


def _epoch() -> ResearchEpoch:
    return ResearchEpoch(
        epoch_id="finite-research", created="2026-11-14", status="proposed",
        hypothesis="Synthetic AUD forecast error improvement",
        champion_id="old", challenger_id="new", holdout_periods=["2026-07"],
        evaluation=_evaluation(),
    )


def _invalid_control(field: str, value: float, *, copied: bool) -> ResearchObjective:
    objective = _objective()
    if field == "weight":
        if copied:
            objective.metrics[0] = objective.metrics[0].model_copy(update={field: value})
        else:
            objective.metrics[0].weight = value
    elif copied:
        objective = objective.model_copy(update={field: value})
    else:
        setattr(objective, field, value)
    return objective


def _invalidate(evaluation: EpochEvaluation, field: str, value: float) -> None:
    if field in {"champion_metrics", "challenger_metrics", "per_metric_improvement"}:
        # An unused key is still persisted evidence and must remain finite.
        getattr(evaluation, field)["unused"] = value
    else:
        setattr(evaluation, field, value)


@pytest.mark.parametrize("field", CONTROLS)
@pytest.mark.parametrize("value", NONFINITE)
def test_nonfinite_objective_controls_cannot_load(field, value, tmp_path):
    data = _objective().model_dump()
    if field == "weight":
        data["metrics"][0]["weight"] = value
    else:
        data[field] = value
    path = tmp_path / "objective.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        ResearchObjective.model_validate(data)
    with pytest.raises(ValueError):
        load_research_objective(path)


@pytest.mark.parametrize("field", CONTROLS)
@pytest.mark.parametrize("copied", [False, True])
def test_evaluation_rechecks_mutated_and_copied_objectives(field, copied):
    objective = _invalid_control(field, float("inf"), copied=copied)
    with pytest.raises(ValueError):
        evaluate_challenger(objective, {"error": 100}, {"error": 80}, [])


@pytest.mark.parametrize("field", CONTROLS)
@pytest.mark.parametrize("copied", [False, True])
@pytest.mark.parametrize("existing", [False, True])
def test_invalid_objective_save_preserves_destination(field, copied, existing, tmp_path):
    path = tmp_path / "new-directory" / "objective.yaml"
    if existing:
        path.parent.mkdir()
        path.write_bytes(b"prior objective\n")
    objective = _invalid_control(field, float("inf"), copied=copied)
    with pytest.raises(ValueError):
        save_research_objective(objective, path)
    if existing:
        assert path.read_bytes() == b"prior objective\n"
    else:
        assert not path.parent.exists()


@pytest.mark.parametrize("field", EVIDENCE)
@pytest.mark.parametrize("value", NONFINITE)
def test_nonfinite_epoch_evidence_cannot_load(field, value, tmp_path):
    evaluation = _evaluation()
    _invalidate(evaluation, field, value)
    with pytest.raises(ValueError):
        EpochEvaluation.model_validate(evaluation.model_dump())
    epoch = _epoch()
    epoch.evaluation = evaluation
    path = tmp_path / "invalid.epoch.yaml"
    path.write_text(yaml.safe_dump(epoch.model_dump()))
    with pytest.raises(ValueError):
        load_epoch(path)


@pytest.mark.parametrize("field", EVIDENCE)
@pytest.mark.parametrize("copied", [False, True])
@pytest.mark.parametrize("existing", [False, True])
def test_invalid_epoch_save_preserves_destination(field, copied, existing, tmp_path):
    epoch = _epoch()
    evaluation = epoch.evaluation
    assert evaluation is not None
    _invalidate(evaluation, field, float("inf"))
    if copied:
        epoch = epoch.model_copy(update={"evaluation": evaluation.model_copy()})
    directory = tmp_path / "research"
    path = directory / "finite-research.epoch.yaml"
    if existing:
        directory.mkdir()
        path.write_bytes(b"prior epoch\n")
    with pytest.raises(ValueError):
        save_epoch(epoch, directory, overwrite=True)
    if existing:
        assert path.read_bytes() == b"prior epoch\n"
    else:
        assert not directory.exists()


@pytest.mark.parametrize("field", EVIDENCE)
def test_promotion_rechecks_all_stored_numeric_evidence(field):
    epoch = _epoch()
    assert epoch.evaluation is not None
    _invalidate(epoch.evaluation, field, float("inf"))
    registry = ModelRegistry(
        champion=ModelVersion(model_id="old", created="2026-11-14", artifact="old.py"),
        challengers=[ModelVersion(model_id="new", created="2026-11-14", artifact="new.py", source_epoch=epoch.epoch_id)],
    )
    before = copy.deepcopy(registry.model_dump())
    with pytest.raises(ValueError):
        promote_challenger(
            registry, challenger_id="new", epoch=epoch, objective=_objective(),
            approved_by="Synthetic reviewer", approved_at="2026-11-14",
        )
    assert registry.model_dump() == before


@pytest.mark.parametrize("weight", [1e308, 5e-324, 1.0])
@pytest.mark.parametrize(("challenger", "expected", "eligible"), [(120, -0.2, False), (80, 0.2, True)])
def test_weight_scale_cannot_hide_twenty_percent_change(weight, challenger, expected, eligible):
    objective = ResearchObjective(metrics=[MetricObjective(name=name, weight=weight) for name in ["a", "b"]])
    result = evaluate_challenger(objective, {"a": 100, "b": 100}, {"a": challenger, "b": challenger}, [])
    assert result.weighted_improvement == pytest.approx(expected)
    assert result.objective_gain == pytest.approx(expected)
    assert result.promotion_eligible is eligible


def test_large_unequal_weights_preserve_ratios_checks_and_complexity():
    objective = ResearchObjective(
        metrics=[MetricObjective(name="a", weight=1e308), MetricObjective(name="b", weight=5e307)],
        hard_checks=["balanced"], complexity_penalty=0.01,
    )
    result = evaluate_challenger(
        objective, {"a": 100, "b": 100}, {"a": 80, "b": 110},
        [ExperimentCheck(name="balanced", result="pass")],
        champion_complexity=1, challenger_complexity=3,
    )
    assert result.weighted_improvement == pytest.approx(0.1)
    assert result.objective_gain == pytest.approx(0.08)
    assert result.promotion_eligible


def test_unrepresentable_complexity_cost_refuses_instead_of_saving_infinity():
    objective = _objective().model_copy(update={"complexity_penalty": 1e308})
    with pytest.raises(ValueError):
        evaluate_challenger(objective, {"error": 100}, {"error": 80}, [], challenger_complexity=1e308)


def test_finite_legacy_epoch_and_exclusive_save_remain_supported(tmp_path):
    epoch = _epoch()
    assert epoch.evaluation is not None
    epoch.evaluation.champion_complexity = None
    epoch.evaluation.challenger_complexity = None
    path = save_epoch(epoch, tmp_path)
    assert load_epoch(path) == epoch
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        save_epoch(epoch, tmp_path)
    assert path.read_bytes() == before
