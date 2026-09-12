"""Regression cases from the continued repository review."""
import pandas as pd
import pytest

from pyfpa.analysis.reconcile import reconcile
from pyfpa.au.payroll import Role, payroll_forecast
from pyfpa.backtest.learn import persistent_miss
from pyfpa.backtest.score import score_forecast
from pyfpa.backtest.snapshot import Snapshot, save_snapshot
from pyfpa.memory.corrections import Correction, load_corrections, save_correction
from pyfpa.memory.experiments import ExperimentCheck
from pyfpa.memory.intake import load_intake
from pyfpa.memory.paths import apply_override
from pyfpa.memory.retrieval import build_memory_index
from pyfpa.memory.workspace import Workspace
from pyfpa.research.epochs import evaluate_challenger
from pyfpa.research.objective import MetricObjective, ResearchObjective


@pytest.mark.parametrize("predicted,actual,weights", [
    ({"revenue": 1}, {"revenue": 1}, {"revenue": 1, "ebitda": 1}),
    ({"revenue": 1, "ebitda": 1}, {"revenue": 1, "ebitda": 0}, {"revenue": 1, "ebitda": 1}),
    ({"revenue": 1, "ebitda": 1}, {"revenue": 1, "ebitda": 1}, {"revenue": 2, "ebitda": -1}),
])
def test_scoring_refuses_incomplete_evidence_or_negative_weights(predicted, actual, weights):
    with pytest.raises(ValueError):
        score_forecast(predicted, actual, weights=weights)


@pytest.mark.parametrize("k", [0, -1])
def test_persistence_requires_positive_window(k):
    with pytest.raises(ValueError, match="k"):
        persistent_miss([], k=k)


def test_history_writes_are_exclusive(tmp_path):
    correction = Correction(slug="example", type="context", target="example", date="2026-09-12")
    save_correction(correction, tmp_path)
    with pytest.raises(FileExistsError):
        save_correction(correction, tmp_path)
    save_correction(correction, tmp_path, overwrite=True)
    snapshot = Snapshot(label="example", created="2026-09-12", assumptions={}, predicted={})
    path = tmp_path / "snapshot.yaml"
    save_snapshot(snapshot, path)
    with pytest.raises(FileExistsError):
        save_snapshot(snapshot, path)


def test_malformed_correction_reports_its_path(tmp_path):
    path = tmp_path / "broken.md"
    path.write_text("---\ntype: context\n", encoding="utf-8")
    with pytest.raises(ValueError, match="broken.md"):
        load_corrections(tmp_path)


def test_objective_and_checks_must_be_unambiguous():
    with pytest.raises(ValueError):
        ResearchObjective(metrics=[])
    objective = ResearchObjective(metrics=[MetricObjective(name="error", weight=1)])
    with pytest.raises(ValueError, match="unique"):
        evaluate_challenger(objective, {"error": 2}, {"error": 1}, [
            ExperimentCheck(name="check", result="fail"), ExperimentCheck(name="check", result="pass"),
        ])


def test_payroll_rejects_reversed_role_window():
    with pytest.raises(ValueError):
        Role(name="Example", annual_salary=100, start_month="2026-09", end_month="2026-08")


@pytest.mark.parametrize("months", [pd.period_range("2026Q1", periods=2, freq="Q"), pd.PeriodIndex(["2026-01", "2026-01"], freq="M")])
def test_payroll_requires_unique_months(months):
    with pytest.raises(ValueError, match="monthly|unique"):
        payroll_forecast([], months)


def test_reconciliation_cannot_hide_missing_accounts_or_zero_denominator():
    for model, actual in [({"extra": 1}, {}), ({}, {"missing": 1})]:
        with pytest.raises(ValueError, match="accounts|line"):
            reconcile(model, actual)
    result = reconcile({"line": 1}, {"line": 0})
    assert pd.isna(result.loc["line", "variance_pct"])
    assert not result.loc["line", "within_tolerance"]


def test_empty_workspace_is_not_ready(tmp_path):
    (tmp_path / ".fpa").mkdir()
    assert not Workspace.open(tmp_path).is_ready()


@pytest.mark.parametrize("text", ["---\nfacts: []", "---\n- not a mapping\n---\n"])
def test_bad_intake_has_a_contextual_error(tmp_path, text):
    path = tmp_path / "intake.md"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="intake.md"):
        load_intake(path)


def test_memory_index_skips_invalid_utf8(tmp_path):
    (tmp_path / "good.md").write_text("# Fabricated café", encoding="utf-8")
    (tmp_path / "bad.md").write_bytes(b"\xff\xfe")
    index = build_memory_index(tmp_path)
    assert [entry.path for entry in index.entries] == ["good.md"]


def test_empty_wildcard_is_not_a_successful_override():
    with pytest.raises(ValueError, match="empty|match"):
        apply_override({"channels": []}, "channels[*].cogs_pct", 0.5)


def test_expected_totals_reject_duplicate_accounts():
    from pyfpa.cli_commands.lineage import _expected_from_json

    with pytest.raises(ValueError, match="duplicate expected account"):
        _expected_from_json('{"revenue": 10, "revenue": 20}')
