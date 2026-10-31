"""Refusal paths in pyfpa.research epochs, objectives and the model registry."""

import pytest

from pyfpa.memory.experiments import ExperimentCheck
from pyfpa.research.epochs import (
    ResearchEpoch,
    evaluate_challenger,
    load_epoch,
    load_epochs,
)
from pyfpa.research.objective import (
    MetricObjective,
    ResearchObjective,
    load_research_objective,
)
from pyfpa.research.registry import (
    ModelRegistry,
    ModelVersion,
    promote_challenger,
    register_challenger,
)

CHECKS = [ExperimentCheck(name="reconcile", result="pass")]


def _objective(complexity_penalty: float = 0.0) -> ResearchObjective:
    return ResearchObjective(
        metrics=[MetricObjective(name="cash_error", weight=1.0)],
        hard_checks=["reconcile"],
        min_improvement=0.05,
        complexity_penalty=complexity_penalty,
    )


def _epoch(*, status: str = "proposed", objective: ResearchObjective | None = None,
           **changes) -> ResearchEpoch:
    values = {
        "epoch_id": "epoch-1",
        "created": "2026-06-09",
        "status": status,
        "hypothesis": "Improve collections timing",
        "champion_id": "model-v1",
        "challenger_id": "model-v2",
        "holdout_periods": ["FY2025"],
        "checks": CHECKS,
        "evaluation": evaluate_challenger(
            objective or _objective(), {"cash_error": 0.20}, {"cash_error": 0.10}, CHECKS,
        ),
        **changes,
    }
    return ResearchEpoch.model_validate(values)


def _registry(**challenger_changes) -> ModelRegistry:
    challenger = ModelVersion.model_validate({
        "model_id": "model-v2",
        "created": "2026-06-09",
        "artifact": "models/generated/collections.py",
        "source_epoch": "epoch-1",
        **challenger_changes,
    })
    return register_challenger(ModelRegistry(), challenger)


def _promote(registry: ModelRegistry, epoch: ResearchEpoch, *,
             objective: ResearchObjective | None = None) -> ModelRegistry:
    return promote_challenger(
        registry,
        challenger_id="model-v2",
        epoch=epoch,
        objective=objective or _objective(),
        approved_by="CFO",
        approved_at="2026-06-09",
    )


# --- epochs -----------------------------------------------------------------------

def test_epoch_refuses_repeated_check_names():
    with pytest.raises(ValueError, match="check names must be unique"):
        _epoch(checks=CHECKS * 2)


def test_generated_epoch_needs_no_evaluation():
    epoch = _epoch(status="generated", evaluation=None)

    assert epoch.evaluation is None  # nosec B101: pytest outcome assertion


def test_evaluated_epoch_requires_an_evaluation():
    with pytest.raises(ValueError, match="evaluated epochs require an evaluation"):
        _epoch(status="evaluated", evaluation=None)


def test_missing_epoch_records(tmp_path):
    with pytest.raises(FileNotFoundError, match="research epoch not found"):
        load_epoch(tmp_path / "epoch-1.epoch.yaml")
    assert load_epochs(tmp_path / "absent") == []  # nosec B101: pytest outcome assertion


# --- objective --------------------------------------------------------------------

def test_missing_research_objective_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError, match="research objective not found"):
        load_research_objective(tmp_path / "objective.yaml")


# --- registry ---------------------------------------------------------------------

def test_promotion_refuses_evaluation_without_complexity_inputs():
    # Evaluations stored before complexity inputs were recorded carry None.
    objective = _objective(complexity_penalty=0.1)
    epoch = _epoch(objective=objective)
    assert epoch.evaluation is not None  # nosec B101: pytest outcome assertion
    epoch.evaluation = epoch.evaluation.model_copy(update={"champion_complexity": None})

    with pytest.raises(ValueError, match="stored evaluation lacks complexity inputs"):
        _promote(_registry(), epoch, objective=objective)


def test_promotion_refuses_an_unregistered_challenger():
    with pytest.raises(ValueError, match="challenger not found: model-v2"):
        _promote(ModelRegistry(), _epoch())


def test_promotion_refuses_an_epoch_for_another_challenger():
    with pytest.raises(ValueError, match="epoch challenger does not match registry challenger"):
        _promote(_registry(), _epoch(challenger_id="model-v3"))


def test_promotion_refuses_a_challenger_from_another_epoch():
    with pytest.raises(ValueError, match="challenger source epoch does not match"):
        _promote(_registry(source_epoch="epoch-0"), _epoch())


def test_first_promotion_retires_nothing():
    registry = _registry()

    promoted = _promote(registry, _epoch())

    assert promoted.champion == registry.challengers[0]  # nosec B101: pytest outcome assertion
    assert promoted.challengers == []  # nosec B101: pytest outcome assertion
    assert promoted.retired == []  # nosec B101: pytest outcome assertion
    assert promoted.promotions[0].from_model == ""  # nosec B101: pytest outcome assertion
    assert promoted.promotions[0].to_model == "model-v2"  # nosec B101: pytest outcome assertion
