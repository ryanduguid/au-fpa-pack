"""Regression cases from the continued repository review."""
from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from pyfpa.analysis.reconcile import reconcile
from pyfpa.au.calendar import fy_summary
from pyfpa.au.gst import BasCycle, GstAssumptions, _next_business_day, bas_schedule
from pyfpa.au.payroll import Role, payroll_forecast
from pyfpa.backtest.learn import persistent_miss
from pyfpa.backtest.score import extract_lines, score_forecast
from pyfpa.backtest.snapshot import Snapshot, save_snapshot
from pyfpa.cli_commands.lineage import _expected_from_json
from pyfpa.config.schemas import OpexLine
from pyfpa.memory.corrections import Correction, load_corrections, save_correction
from pyfpa.memory.experiments import ExperimentCheck
from pyfpa.memory.intake import load_intake
from pyfpa.memory.paths import apply_override
from pyfpa.memory.retrieval import _TOKEN, build_memory_index
from pyfpa.memory.workspace import Workspace, initialize_workspace
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


# --------------------------------------------------------------------------- #
# CodeRabbit CLI whole-repo scan, 16 September 2026
# --------------------------------------------------------------------------- #
def test_a_leading_partial_quarter_still_settles_its_months():
    # `len(amounts) < 3` dropped any short quarter, so a series starting mid-quarter
    # lost that quarter's BAS entirely and understated GST cash.
    months = pd.period_range("2026-08", periods=5, freq="M")  # Aug-Dec
    schedule = bas_schedule(
        pd.Series(1000.0, index=months), GstAssumptions(bas_cycle=BasCycle.QUARTERLY)
    )
    assert schedule["period_label"].tolist() == ["2027Q1", "2027Q2"]
    assert schedule["amount"].tolist() == pytest.approx([2000.0, 3000.0])


def test_a_trailing_open_quarter_is_still_excluded():
    months = pd.period_range("2026-07", periods=8, freq="M")  # Jul-Feb
    schedule = bas_schedule(
        pd.Series(6000.0, index=months), GstAssumptions(bas_cycle=BasCycle.QUARTERLY)
    )
    assert len(schedule) == 2


def test_a_weekend_bas_due_date_moves_to_the_monday():
    # The ATO allows lodgment and payment on the next business day, and these dates
    # drive cash timing, so a Sunday settlement landed in the wrong forecast week.
    assert _next_business_day(date(2027, 2, 27)) == date(2027, 3, 1)  # Saturday
    assert _next_business_day(date(2027, 2, 28)) == date(2027, 3, 1)  # Sunday
    assert _next_business_day(date(2027, 3, 1)) == date(2027, 3, 1)  # Monday


def test_fy_summary_rows_follow_the_calendar_from_an_unsorted_index():
    # groupby(sort=False) orders by first appearance, so an unsorted input gave rows
    # out of calendar order while the docstring promised calendar order.
    months = pd.period_range("2026-05", periods=6, freq="M")
    frame = pd.DataFrame({"revenue": [float(n) for n in range(6)]}, index=months)
    shuffled = frame.iloc[[3, 0, 5, 1, 4, 2]]
    for by in ("fy", "quarter", "half"):
        assert (
            fy_summary(shuffled, by=by).index.tolist()
            == fy_summary(frame, by=by).index.tolist()
        )
    assert fy_summary(shuffled).index.tolist() == ["FY2026", "FY2027"]


def test_scoring_without_gross_margin_does_not_need_a_revenue_column():
    # extract_lines read forecast_df["revenue"] before the loop, so a score set that
    # never mentions revenue still raised KeyError on a frame without it.
    frame = pd.DataFrame({"ebitda": [1.0, 2.0], "ending_cash": [10.0, 12.0]})
    assert extract_lines(frame, ["ebitda", "ending_cash"]) == {
        "ebitda": 3.0,
        "ending_cash": 12.0,
    }


def test_an_opex_line_cannot_be_negative():
    # Every other amount in the schema is bounded. A negative opex line reads as
    # income in the cash model rather than a cost.
    for field in ({"monthly_amount": -1.0}, {"pct_of_revenue": -0.1}):
        with pytest.raises(ValidationError):
            OpexLine(name="Rent", kind="fixed", **field)


def test_a_single_character_query_token_survives():
    # The token pattern required two characters, so "P&L" produced no tokens at all
    # and the query retrieved nothing.
    assert _TOKEN.findall("p&l") == ["p", "l"]


def test_expected_totals_reject_booleans_and_non_finite_numbers():
    # isinstance(x, (int, float)) is true for bool, and Python's json accepts the
    # NaN and Infinity literals, so none of these were rejected as totals.
    for payload in ('{"Sales": true}', '{"Sales": NaN}', '{"Sales": -Infinity}'):
        with pytest.raises(ValueError, match="finite numeric totals"):
            _expected_from_json(payload)
    assert _expected_from_json('{"Sales": 1}') == {"Sales": 1.0}


def test_reconciling_nothing_returns_an_empty_frame():
    # pd.DataFrame([]).set_index("line") raised KeyError, so two empty mappings
    # crashed instead of reporting that there was nothing to reconcile.
    frame = reconcile({}, {})
    assert frame.empty
    assert frame.index.name == "line"
    assert list(frame.columns) == [
        "model", "actual", "variance", "variance_pct", "within_tolerance",
    ]


def test_workers_comp_premium_includes_bonuses():
    # gross holds salary only, so any non-zero bonus_pct understated the premium
    # while the payroll tax base above already included bonuses.
    months = pd.period_range("2026-07", periods=1, freq="M")
    salaried = payroll_forecast(
        [Role(name="Fitter", annual_salary=120_000.0, jurisdiction="NSW")], months
    )
    bonused = payroll_forecast(
        [Role(name="Fitter", annual_salary=120_000.0, bonus_pct=0.10,
              jurisdiction="NSW")],
        months,
    )
    salary_only = salaried.loc[months[0], "workers_comp"]
    with_bonus = bonused.loc[months[0], "workers_comp"]
    assert bonused.loc[months[0], "bonuses"] == pytest.approx(120_000.0 / 12 * 0.10)
    assert with_bonus == pytest.approx(salary_only * 1.10)


def test_workspace_initialisation_refuses_a_linked_memory_directory(
    tmp_path, directory_link
):
    # mkdir(exist_ok=True) and the seed writes follow an existing link, so a planted
    # .fpa put the workspace outside company_root.
    company_root = tmp_path / "acme"
    company_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    directory_link(company_root / ".fpa", outside)
    with pytest.raises(ValueError, match="symlinks or reparse points"):
        initialize_workspace(company_root, business_name="Acme Pty Ltd")
    assert not (outside / "intake.md").exists()
