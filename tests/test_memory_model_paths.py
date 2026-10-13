"""Refusal and fallback paths in the pyfpa.memory models and stores."""

import os
from pathlib import Path

import pytest
from openpyxl import Workbook

from pyfpa.memory.entrypoints import CompanyEntrypoint
from pyfpa.memory.experiments import (
    Experiment,
    ExperimentCheck,
    ExperimentDecision,
    load_experiment,
    load_experiments,
)
from pyfpa.memory.inspection import inspect_data_files
from pyfpa.memory.intake import (
    Intake,
    _split_frontmatter,
    load_intake,
    next_intake_questions,
    record_intake_fact,
)
from pyfpa.memory.lineage import (
    MappingRegistry,
    MappingRule,
    SourceRecord,
    profile_table,
    reconcile_account_table,
    required_text,
)
from pyfpa.memory.onboarding import (
    ArchitectureProposal,
    _replace_onboarding_text,
    is_seeded_business_profile,
    write_onboarding_outputs,
)
from pyfpa.memory.retrieval import (
    MemoryIndex,
    build_memory_index,
    load_memory_index,
    render_context_pack,
    search_memory,
)

# --- entrypoints ----------------------------------------------------------------

@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"description": "   "}, "description must not be empty"),
        ({"command": ["python", "  "]}, "command arguments must not be empty"),
    ],
)
def test_entrypoint_rejects_blank_text(changes, message):
    values = {
        "name": "monthly-forecast",
        "kind": "forecast",
        "description": "Run the monthly forecast.",
        "command": ["python", "forecast.py"],
        **changes,
    }
    with pytest.raises(ValueError, match=message):
        CompanyEntrypoint(**values)


# --- experiments --------------------------------------------------------------

def _experiment(**changes) -> dict:
    return {
        "slug": "collections-lag",
        "created": "2026-06-09",
        "hypothesis": "Collections lag tracks wholesale mix.",
        **changes,
    }


def _decision(outcome: str) -> ExperimentDecision:
    return ExperimentDecision.model_validate(
        {"outcome": outcome, "decided_by": "CFO", "decided_at": "2026-06-10"}
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"checks": [ExperimentCheck(name="holdout", result="pass")] * 2},
            "check names must be unique",
        ),
        (
            {"status": "accepted", "decision": _decision("rejected")},
            "experiment status must match decision outcome",
        ),
        (
            {"status": "accepted", "decision": _decision("accepted")},
            "accepted experiments require evidence",
        ),
        (
            {"status": "accepted", "decision": _decision("accepted"), "evidence": ["backtest"]},
            "accepted experiments require changed files",
        ),
        (
            {
                "status": "accepted",
                "decision": _decision("accepted"),
                "evidence": ["backtest"],
                "files_changed": ["model.py"],
            },
            "accepted experiments require checks",
        ),
    ],
)
def test_experiment_ratification_rules(changes, message):
    with pytest.raises(ValueError, match=message):
        Experiment(**_experiment(**changes))


def test_draft_and_rejected_experiments_need_no_evidence():
    draft = Experiment(**_experiment())
    rejected = Experiment(**_experiment(status="rejected", decision=_decision("rejected")))

    assert draft.decision is None  # nosec B101: pytest outcome assertion
    assert rejected.decision is not None  # nosec B101: pytest outcome assertion
    assert rejected.decision.outcome == "rejected"  # nosec B101: pytest outcome assertion


def test_missing_experiment_records(tmp_path):
    with pytest.raises(FileNotFoundError, match="experiment not found"):
        load_experiment(tmp_path / "absent.experiment.yaml")
    assert load_experiments(tmp_path / "absent") == []  # nosec B101: pytest outcome assertion


# --- inspection -----------------------------------------------------------------

def test_inspection_skips_hidden_and_non_data_files(tmp_path):
    (tmp_path / ".Balance Sheet.csv").write_text("account,amount\n", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"png")
    (tmp_path / "README.txt").write_text("setup notes", encoding="utf-8")
    (tmp_path / "Board Pack.md").write_text("board notes", encoding="utf-8")

    result = inspect_data_files(tmp_path)

    assert [item["path"] for item in result.files] == ["Board Pack.md"]  # nosec B101: pytest outcome assertion


# --- intake ---------------------------------------------------------------------

def test_text_without_frontmatter_is_all_notes():
    assert _split_frontmatter("\nPlain notes.\n") == ({}, "Plain notes.")  # nosec B101: pytest outcome assertion


def test_missing_intake_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError, match="intake not found"):
        load_intake(tmp_path / "intake.md")


def test_blank_intake_answer_is_refused():
    with pytest.raises(ValueError, match="intake answer must not be empty"):
        record_intake_fact(
            Intake(business_name="Acme"), key="revenue_model", answer="   ", source_type="user",
        )


def test_matching_evidence_strengthens_an_inferred_fact():
    intake = record_intake_fact(
        Intake(business_name="Acme"),
        key="revenue_model",
        answer="Wholesale and online",
        source_type="local_file",
        sources=["pnl.csv"],
        confidence=0.6,
    )
    intake = record_intake_fact(
        intake,
        key="revenue_model",
        answer="wholesale and ONLINE",
        source_type="external",
        sources=["website", "pnl.csv"],
        confidence=0.9,
    )

    fact = intake.facts[0]
    assert len(intake.facts) == 1  # nosec B101: pytest outcome assertion
    assert fact.status == "inferred"  # nosec B101: pytest outcome assertion
    assert fact.answer == "Wholesale and online"  # nosec B101: pytest outcome assertion
    assert fact.confidence == 0.9  # nosec B101: pytest outcome assertion
    assert fact.sources == ["pnl.csv", "website"]  # nosec B101: pytest outcome assertion


# --- lineage ---------------------------------------------------------------------

def test_required_text_refuses_blank():
    with pytest.raises(ValueError, match="value must not be empty"):
        required_text("  ")


def test_source_record_refuses_blank_period():
    with pytest.raises(ValueError, match="periods must not contain empty values"):
        SourceRecord(
            source_id="gl-actuals",
            kind="local_file",
            location="exports/pnl.csv",
            entity="Acme Pty Ltd",
            currency="aud",
            periods=["2026-01", " "],
            extraction_method="manual export",
        )


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"source_value": " ", "target": "revenue"}, "source_value must not be empty"),
        ({"source_value": "Sales", "target": " "}, "mapped rules require a target"),
    ],
)
def test_mapping_rule_refuses_incomplete_rules(values, message):
    with pytest.raises(ValueError, match=message):
        MappingRule(source_id="gl-actuals", **values)


def test_profile_table_requires_the_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="source file not found"):
        profile_table(tmp_path / "absent.csv")


def test_profile_table_reads_tsv(tmp_path):
    path = tmp_path / "pnl.tsv"
    path.write_text("Account\tAmount\nSales\t10\nSales\t10\nRent\t\n", encoding="utf-8")

    profile = profile_table(path)

    assert profile["rows"] == 3  # nosec B101: pytest outcome assertion
    assert profile["columns"] == ["Account", "Amount"]  # nosec B101: pytest outcome assertion
    assert profile["empty_by_column"] == {"Account": 0, "Amount": 1}  # nosec B101: pytest outcome assertion
    assert profile["duplicate_rows"] == 1  # nosec B101: pytest outcome assertion


def test_profile_table_reads_xlsx(tmp_path):
    path = tmp_path / "pnl.XLSX"
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None  # nosec B101: pytest outcome assertion
    for row in (("Account", "Amount"), ("Sales", 10), ("Rent", None)):
        sheet.append(row)
    workbook.save(path)

    profile = profile_table(path)

    assert profile["rows"] == 2  # nosec B101: pytest outcome assertion
    assert profile["columns"] == ["Account", "Amount"]  # nosec B101: pytest outcome assertion
    assert profile["empty_by_column"] == {"Account": 0, "Amount": 1}  # nosec B101: pytest outcome assertion


def test_profile_table_refuses_unsupported_suffix(tmp_path):
    path = tmp_path / "pnl.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="source-profile supports CSV, TSV, XLS, XLSM, and XLSX"):
        profile_table(path)


def test_reconcile_refuses_non_csv(tmp_path):
    with pytest.raises(ValueError, match="reconcile-source currently supports CSV files"):
        reconcile_account_table(
            tmp_path / "pnl.tsv",
            source_id="gl-actuals",
            mappings=MappingRegistry(),
            account_column="Account",
            amount_column="Amount",
        )


def test_reconcile_requires_named_columns(tmp_path):
    path = tmp_path / "pnl.csv"
    path.write_text("Account,Value\nSales,10\n", encoding="utf-8")

    with pytest.raises(ValueError, match="expected columns 'Account' and 'Amount'"):
        reconcile_account_table(
            path,
            source_id="gl-actuals",
            mappings=MappingRegistry(),
            account_column="Account",
            amount_column="Amount",
        )


# --- onboarding -------------------------------------------------------------------

def _ready_intake() -> Intake:
    intake = Intake(business_name="Acme")
    while questions := next_intake_questions(intake):
        for question in questions:
            intake = record_intake_fact(
                intake,
                key=question.key,
                answer=f"Known {question.key}",
                source_type="user",
                sources=["CFO interview"],
            )
    return intake


def _proposal(summary: str = "Build a driver-based monthly forecast.") -> ArchitectureProposal:
    return ArchitectureProposal(summary=summary)


def _no_check(path: Path) -> None:
    return None


def _temporaries(directory: Path) -> list[Path]:
    return sorted(directory.glob(".onboarding-*.tmp"))


def test_profile_title_without_a_business_name_is_not_a_seed():
    assert is_seeded_business_profile("# Business Profile\n") is False  # nosec B101: pytest outcome assertion


def test_replacement_refuses_a_destination_that_stops_being_regular(tmp_path, monkeypatch):
    path = tmp_path / "business-profile.md"
    path.write_text("previous", encoding="utf-8")
    directory_stat = os.stat(tmp_path)
    monkeypatch.setattr(os, "fstat", lambda descriptor: directory_stat)

    with pytest.raises(ValueError, match="onboarding output is not a regular file"):
        _replace_onboarding_text(path, "replacement", _no_check)

    monkeypatch.undo()
    assert path.read_text(encoding="utf-8") == "previous"  # nosec B101: pytest outcome assertion


@pytest.mark.parametrize("close_fails", [False, True])
def test_replacement_closes_the_temporary_descriptor_when_fdopen_fails(
    tmp_path, monkeypatch, close_fails,
):
    path = tmp_path / "business-profile.md"
    path.write_text("previous", encoding="utf-8")
    real_close = os.close
    closed: list[int] = []
    failing = False

    def broken_fdopen(descriptor, *args, **kwargs):
        nonlocal failing
        failing = close_fails
        raise OSError("simulated fdopen failure")

    def tracking_close(descriptor):
        real_close(descriptor)
        closed.append(descriptor)
        if failing:
            raise OSError("simulated close failure")

    monkeypatch.setattr(os, "fdopen", broken_fdopen)
    monkeypatch.setattr(os, "close", tracking_close)

    with pytest.raises(OSError, match="simulated fdopen failure"):
        _replace_onboarding_text(path, "replacement", _no_check)

    monkeypatch.undo()
    assert len(closed) == 2  # nosec B101: pytest outcome assertion
    assert path.read_text(encoding="utf-8") == "previous"  # nosec B101: pytest outcome assertion
    assert _temporaries(tmp_path) == []  # nosec B101: pytest outcome assertion


def test_replacement_ignores_a_failed_temporary_cleanup(tmp_path, monkeypatch):
    path = tmp_path / "business-profile.md"
    path.write_text("previous", encoding="utf-8")

    def broken_unlink(self, missing_ok=False):
        raise OSError("simulated unlink failure")

    monkeypatch.setattr(Path, "unlink", broken_unlink)

    _replace_onboarding_text(path, "replacement", _no_check)

    monkeypatch.undo()
    assert path.read_text(encoding="utf-8") == "replacement"  # nosec B101: pytest outcome assertion
    assert _temporaries(tmp_path) == []  # nosec B101: pytest outcome assertion


def test_overwrite_replaces_an_output_created_after_the_existence_check(tmp_path, monkeypatch):
    workspace = tmp_path / ".fpa"
    write_onboarding_outputs(_ready_intake(), workspace, _proposal("First proposal."))
    proposal_path = workspace / "decisions" / "initial-model-architecture.md"
    real_exists = Path.exists

    def racing_exists(self, *args, **kwargs):
        if self == proposal_path:
            return False
        return real_exists(self, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", racing_exists)

    write_onboarding_outputs(
        _ready_intake(), workspace, _proposal("Second proposal."), overwrite=True,
    )

    monkeypatch.undo()
    text = proposal_path.read_text(encoding="utf-8")
    assert "Second proposal." in text  # nosec B101: pytest outcome assertion
    assert "First proposal." not in text  # nosec B101: pytest outcome assertion


# --- retrieval -------------------------------------------------------------------

def test_missing_workspace_builds_an_empty_index(tmp_path):
    assert build_memory_index(tmp_path / "absent") == MemoryIndex()  # nosec B101: pytest outcome assertion


def test_missing_memory_index_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError, match="memory index not found"):
        load_memory_index(tmp_path / "index.yaml")


def test_search_refuses_a_limit_below_one():
    with pytest.raises(ValueError, match="memory search limit must be at least 1"):
        search_memory(MemoryIndex(), "cash", limit=0)


def test_search_without_query_tokens_finds_nothing(tmp_path):
    (tmp_path / "MEMORY.md").write_text("# Memory\n\ncash runway\n", encoding="utf-8")

    assert search_memory(build_memory_index(tmp_path), "!!! ???") == []  # nosec B101: pytest outcome assertion


def test_context_pack_without_hits_says_so():
    pack = render_context_pack("Explain cash runway", [])

    assert pack.endswith("No relevant memory found.\n")  # nosec B101: pytest outcome assertion
    assert "**Task:** Explain cash runway" in pack  # nosec B101: pytest outcome assertion
