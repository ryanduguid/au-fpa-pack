import pytest

from pyfpa.memory.experiments import ExperimentCheck
from pyfpa.research.epochs import ResearchEpoch, evaluate_challenger
from pyfpa.research.objective import MetricObjective, ResearchObjective
from pyfpa.research.registry import (
    ModelRegistry,
    ModelVersion,
    load_model_registry,
    promote_challenger,
    register_challenger,
    save_model_registry,
)


def _epoch(challenger_id="model-v2", *, eligible=True):
    objective = ResearchObjective(
        metrics=[MetricObjective(name="cash_error", weight=1.0)],
        hard_checks=["reconcile"],
        min_improvement=0.05,
    )
    evaluation = evaluate_challenger(
        objective,
        {"cash_error": 0.20},
        {"cash_error": 0.10 if eligible else 0.195},
        [ExperimentCheck(name="reconcile", result="pass")],
    )
    return ResearchEpoch(
        epoch_id="epoch-1",
        created="2026-06-09",
        status="proposed" if eligible else "discarded",
        hypothesis="Improve collections timing",
        champion_id="model-v1",
        challenger_id=challenger_id,
        checks=[ExperimentCheck(name="reconcile", result="pass")],
        evaluation=evaluation,
    )


def test_register_and_promote_challenger_with_human_approval(tmp_path):
    champion = ModelVersion(model_id="model-v1", created="2026-01-01", artifact="model.py")
    challenger = ModelVersion(
        model_id="model-v2",
        created="2026-06-09",
        artifact="models/generated/collections.py",
        source_epoch="epoch-1",
    )
    registry = register_challenger(ModelRegistry(champion=champion), challenger)
    promoted = promote_challenger(
        registry,
        challenger_id="model-v2",
        epoch=_epoch(),
        objective=_objective(),
        approved_by="CFO",
        approved_at="2026-06-09",
    )

    assert promoted.champion == challenger
    assert promoted.retired == [champion]
    assert promoted.promotions[0].approved_by == "CFO"
    path = tmp_path / "registry.yaml"
    save_model_registry(promoted, path)
    assert load_model_registry(path) == promoted


def test_promotion_rejects_missing_approval_or_ineligible_epoch():
    challenger = ModelVersion(
        model_id="model-v2",
        created="2026-06-09",
        artifact="candidate.py",
        source_epoch="epoch-1",
    )
    registry = register_challenger(ModelRegistry(), challenger)
    with pytest.raises(ValueError, match="approved_by"):
        promote_challenger(
            registry,
            challenger_id="model-v2",
            epoch=_epoch(),
            approved_by="",
            approved_at="2026-06-09",
        )
    with pytest.raises(ValueError, match="promotion-eligible"):
        promote_challenger(
            registry,
            challenger_id="model-v2",
            epoch=_epoch(eligible=False),
            objective=_objective(),
            approved_by="CFO",
            approved_at="2026-06-09",
        )


def test_duplicate_model_id_rejected():
    version = ModelVersion(model_id="model-v1", created="2026-01-01", artifact="model.py")
    with pytest.raises(ValueError, match="already registered"):
        register_challenger(ModelRegistry(champion=version), version)


def _objective():
    return ResearchObjective(
        metrics=[MetricObjective(name="cash_error", weight=1.0)],
        hard_checks=["reconcile"],
        min_improvement=0.05,
    )


def _doctored_epoch() -> ResearchEpoch:
    """An epoch whose stored promotion_eligible=True but whose metrics do not support it.

    The improvement (2.5%) is below min_improvement (5%). The checks are present
    so the recompute can run; the verdict mismatch comes from the metrics alone.
    """
    from pyfpa.research.epochs import EpochEvaluation

    bad_eval = EpochEvaluation(
        champion_metrics={"cash_error": 0.20},
        challenger_metrics={"cash_error": 0.195},
        per_metric_improvement={"cash_error": 0.025},
        weighted_improvement=0.025,
        complexity_cost=0.0,
        objective_gain=0.025,
        hard_checks_passed=True,
        promotion_eligible=True,
    )
    return ResearchEpoch(
        epoch_id="epoch-1",
        created="2026-06-09",
        status="proposed",
        hypothesis="Doctored",
        champion_id="model-v1",
        challenger_id="model-v2",
        checks=[ExperimentCheck(name="reconcile", result="pass")],
        evaluation=bad_eval,
    )


def test_promote_with_objective_rejects_doctored_epoch():
    """A hand-edited epoch claiming eligibility is rejected when objective is provided."""
    challenger = ModelVersion(
        model_id="model-v2",
        created="2026-06-09",
        artifact="candidate.py",
        source_epoch="epoch-1",
    )
    registry = register_challenger(ModelRegistry(), challenger)
    epoch = _doctored_epoch()

    with pytest.raises(ValueError, match="stored evaluation does not reproduce"):
        promote_challenger(
            registry,
            challenger_id="model-v2",
            epoch=epoch,
            approved_by="CFO",
            approved_at="2026-06-09",
            objective=_objective(),
        )


def test_promote_without_objective_refuses_doctored_evaluation():
    """Human approval cannot bypass objective validation."""
    challenger = ModelVersion(
        model_id="model-v2",
        created="2026-06-09",
        artifact="candidate.py",
        source_epoch="epoch-1",
    )
    registry = register_challenger(ModelRegistry(), challenger)
    epoch = _doctored_epoch()

    with pytest.raises(ValueError, match="objective is required"):
        promote_challenger(
            registry,
            challenger_id="model-v2",
            epoch=epoch,
            approved_by="CFO",
            approved_at="2026-06-09",
        )


def test_promotion_rejects_stale_champion_and_forged_complexity():
    champion = ModelVersion(model_id="model-v1", created="2026-01-01", artifact="model.py")
    challenger = ModelVersion(model_id="model-v2", created="2026-06-09", artifact="candidate.py", source_epoch="epoch-1")
    registry = register_challenger(ModelRegistry(champion=champion), challenger)
    epoch = _epoch()
    objective = _objective().model_copy(update={"complexity_penalty": 0.1})
    epoch.checks = [ExperimentCheck(name="reconcile", result="pass")]
    epoch.evaluation = evaluate_challenger(objective, {"cash_error": 0.2}, {"cash_error": 0.1}, epoch.checks,
                                         champion_complexity=1.0, challenger_complexity=1.1)
    args = {"challenger_id": "model-v2", "epoch": epoch, "approved_by": "CFO", "approved_at": "2026-06-09", "objective": objective}
    assert promote_challenger(registry, **args).champion == challenger
    epoch.evaluation.complexity_cost = -1.0
    with pytest.raises(ValueError, match="does not reproduce"):
        promote_challenger(registry, **args)
    epoch.evaluation = evaluate_challenger(objective, {"cash_error": 0.2}, {"cash_error": 0.1}, epoch.checks,
                                         champion_complexity=1.0, challenger_complexity=1.1)
    stale = registry.model_copy(update={"champion": champion.model_copy(update={"model_id": "new-champion"})})
    with pytest.raises(ValueError, match="current registry champion"):
        promote_challenger(stale, **args)
