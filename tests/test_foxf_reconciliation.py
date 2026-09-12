"""Regression guards for the Fox Factory real-company example.

Phase A reproduces known actual-driver mechanics; Phase B is the independent
FY2025 holdout; Phases C/D cover the forward forecast and sensitivity.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "foxfactory"
sys.path.insert(0, str(EXAMPLE))

requires_foxf_data = pytest.mark.skipif(
    not (EXAMPLE / "data" / "income_statement.csv").exists(),
    reason="Fox Factory EDGAR data not pulled (run examples/foxfactory/pull_edgar.py)",
)


@pytest.mark.parametrize("fy,prior", [("FY2024", "FY2023"), ("FY2025", "FY2024")])
@requires_foxf_data
def test_phase_a_reproduces_actual_driver_mechanics(fy, prior):
    import foxf_model as fm

    from pyfpa.analysis.reconcile import reconcile

    model = fm.phase_a_model(fy, prior)
    actual = fm.phase_a_actual(fy, prior)
    rec = reconcile(model, actual, tolerance=0.01)
    assert rec["within_tolerance"].all(), rec[["model", "actual", "variance_pct"]]
    # These target-year drivers are inputs, so this validates arithmetic, not forecasting.
    assert abs(rec.loc["adjusted_ebitda", "variance_pct"]) < 1e-9
    assert abs(rec.loc["operating_cash_flow_before_tax", "variance_pct"]) < 1e-6


@requires_foxf_data
def test_historical_holdout_rejects_broad_recovery_via_regression_guard():
    """Verify the research loop's verdicts are principled, not numerical artifacts.

    Broad recovery (epoch 001) multiplies the adjusted EBITDA error roughly
    twentyfold versus the champion. The improvement clamp bounds its SCORE
    contribution at -1.0 (so it no longer swamps the weighted average), but the
    max_metric_regression guard inspects the RAW regression and blocks
    eligibility: a challenger that makes a key metric far worse is not a better
    model, however the aggregate nets out. Refined (epoch 002) improves every
    metric and stays proposed.
    """
    import foxf_model as fm

    broad, refined = fm.historical_research_epochs()
    assert broad.status == "discarded"
    assert broad.evaluation.per_metric_improvement["adjusted_ebitda_error"] == pytest.approx(
        -1.0
    )  # clamped score contribution
    assert broad.evaluation.regression_guard_passed is False
    assert broad.evaluation.promotion_eligible is False
    assert refined.status == "proposed"
    assert refined.evaluation.regression_guard_passed is True
    assert refined.evaluation.promotion_eligible is True
    assert refined.evaluation.objective_gain > 0.50
    for metric, champion in refined.evaluation.champion_metrics.items():
        assert refined.evaluation.challenger_metrics[metric] < champion


@requires_foxf_data
def test_forecast_is_coherent():
    import foxf_model as fm

    forecast, segs = fm.build_forecast()
    assert len(forecast) == 24  # FY2026 + FY2027 monthly
    # forecast years are profitable (no impairment) and FCF-positive
    fy26 = forecast[forecast.index.year == 2026].sum()
    assert fy26["net_income"] > 0
    assert fy26["free_cash_flow"] > 0
    # segment net sales roll up to the consolidated forecast revenue
    from pyfpa.analysis.segments import roll_up_segments
    seg_sales = float(roll_up_segments(segs["FY2026"])["net_sales"])
    assert seg_sales == pytest.approx(float(fy26["revenue"]), rel=1e-9)


@requires_foxf_data
def test_forecast_year_boundary_uses_modeled_closing_working_capital():
    import foxf_model as fm

    forecast, _ = fm.build_forecast()
    wc = fm.wc_days("FY2025")
    dec = forecast.loc["2026-12"]
    jan = forecast.loc["2027-01"]
    dec_ar = dec["revenue"] * wc.dso_days / 30
    dec_ap = dec["cogs"] * wc.dpo_days / 30
    dec_inventory = dec["cogs"] * wc.dio_days / 30
    jan_ar = jan["revenue"] * wc.dso_days / 30
    jan_ap = jan["cogs"] * wc.dpo_days / 30
    jan_inventory = jan["cogs"] * wc.dio_days / 30
    expected = -(jan_ar - dec_ar) + (jan_ap - dec_ap) - (jan_inventory - dec_inventory)

    assert jan["wc_cash_impact"] == pytest.approx(expected)


def test_foxf_pipeline_is_registered_for_agent_discovery():
    from pyfpa.memory.entrypoints import load_entrypoint_registry

    registry = load_entrypoint_registry(EXAMPLE / ".fpa" / "models" / "entrypoints.yaml")
    entrypoint = next(item for item in registry.entrypoints if item.name == "foxf-pipeline")

    assert entrypoint.kind == "forecast"
    assert entrypoint.command == ["python3", "run_foxf.py"]
    assert "output/foxf-forecast.xlsx" in entrypoint.outputs
    assert (EXAMPLE / ".fpa" / "decisions" / "initial-model-architecture.md").exists()


def test_foxf_sources_and_mappings_are_registered():
    from pyfpa.memory.lineage import (
        load_mapping_registry,
        load_source_registry,
    )

    sources = load_source_registry(EXAMPLE / ".fpa" / "sources" / "registry.yaml")
    mappings = load_mapping_registry(EXAMPLE / ".fpa" / "mappings" / "registry.yaml")

    assert {source.source_id for source in sources.sources} == {
        "foxf-balance-sheet",
        "foxf-cash-flow",
        "foxf-income-statement",
        "foxf-quarterly",
        "foxf-segments",
    }
    assert all(source.kind == "public_filing" for source in sources.sources)
    assert all(source.currency == "USD" for source in sources.sources)
    assert any(
        mapping.source_id == "foxf-income-statement"
        and mapping.source_value == "net_sales"
        and mapping.target == "income_statement.net_sales"
        for mapping in mappings.mappings
    )
    assert any(
        mapping.source_id == "foxf-segments"
        and mapping.source_value == "PVG.net_sales"
        and mapping.target == "segments.PVG.net_sales"
        for mapping in mappings.mappings
    )


@requires_foxf_data
def test_foxf_income_statement_mapping_covers_every_source_row():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyfpa.cli",
            "reconcile-source",
            str(EXAMPLE),
            "--source-id",
            "foxf-income-statement",
            "--account-column",
            "line",
            "--amount-column",
            "FY2025",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1, result.stdout
    evidence = json.loads(result.stdout)["data"]
    assert evidence["unmapped"] == []
    assert evidence["duplicates"] == []
    assert evidence["expected_provided"] is False


@requires_foxf_data
def test_foxf_workspace_passes_agent_toolbelt_diagnostics():
    result = subprocess.run(
        [sys.executable, "-m", "pyfpa.cli", "doctor", str(EXAMPLE)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout


# --------------------------------------------------------------------------- #
# pull_edgar.py - a failed EDGAR fetch must abort, never blank a committed CSV.
# All offline: `_curl` is replaced, so no test here touches the network.
# --------------------------------------------------------------------------- #
def _fake_concept_doc(tag: str) -> bytes:
    """A well-formed companyconcept payload satisfying annual/instant/quarter."""
    import pull_edgar as pe

    rows = [
        {"form": "10-K", "fy": fy, "start": pe.FY_END[fy - 1], "end": pe.FY_END[fy],
         "val": 1_000_000 + fy}
        for fy in pe.FYS
    ]
    rows += [{"end": pe.FY_END[fy], "val": 2_000_000 + fy} for fy in (2022, *pe.FYS)]
    rows += [
        {"form": "10-Q", "fy": 2025, "fp": "Q1", "start": "2025-01-04", "end": "2025-04-04", "val": 300_000},
        {"form": "10-Q", "fy": 2026, "fp": "Q1", "start": "2026-01-03", "end": "2026-04-03", "val": 310_000},
    ]
    return json.dumps({"units": {"USD": rows}}).encode()


def test_curl_uses_fail_so_an_http_error_body_is_never_parsed_as_data(monkeypatch):
    import pull_edgar as pe

    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 22, b"", b"HTTP 403 from SEC")

    # Replace pull_edgar's own name for the module, not stdlib subprocess.run,
    # which other tests in this file call.
    monkeypatch.setattr(pe, "subprocess", SimpleNamespace(run=fake_run))
    with pytest.raises(RuntimeError, match="curl failed"):
        pe._curl("https://data.sec.gov/whatever")
    assert "--fail" in seen["argv"]


def test_a_throttled_concept_raises_instead_of_blanking_the_row(monkeypatch):
    import pull_edgar as pe

    def fake_curl(url: str) -> bytes:
        if "InventoryNet" in url:
            raise RuntimeError(f"curl failed for {url}: HTTP 403")
        return _fake_concept_doc(url)

    monkeypatch.setattr(pe, "_curl", fake_curl)
    with pytest.raises(RuntimeError, match="InventoryNet"):
        pe.pull_balance_sheet()


@requires_foxf_data
def test_main_leaves_committed_csvs_untouched_when_a_late_pull_fails(monkeypatch, tmp_path):
    import pull_edgar as pe

    data = tmp_path / "data"
    data.mkdir()
    for csv in sorted((EXAMPLE / "data").glob("*.csv")):
        shutil.copy(csv, data / csv.name)
    before = {p.name: p.read_bytes() for p in data.glob("*.csv")}

    def fake_curl(url: str) -> bytes:
        if "/Archives/" in url:  # segment footnote: last pull in the batch
            raise RuntimeError(f"curl failed for {url}: HTTP 403")
        return _fake_concept_doc(url)

    monkeypatch.setattr(pe, "_curl", fake_curl)
    monkeypatch.setattr(pe, "DATA", data)
    with pytest.raises(RuntimeError, match="curl failed"):
        pe.main()

    assert {p.name: p.read_bytes() for p in data.glob("*.csv")} == before
    assert not (data / "SOURCES.md").exists()


def test_quarter_selection_is_fixed_and_rejects_conflicting_facts(monkeypatch):
    import pull_edgar as pe

    rows = json.loads(_fake_concept_doc("sales"))["units"]["USD"]
    rows.append({"form": "10-Q", "fy": 2026, "fp": "Q2", "start": "2026-04-04", "end": "2026-07-03", "val": 999})
    monkeypatch.setattr(pe, "_concept", lambda tag: rows)
    assert pe.latest_quarter("sales") == ("2026-01-03", "2026-04-03", 310_000)
    rows.append({"form": "10-Q", "fy": 2026, "fp": "Q1", "start": "2026-01-03", "end": "2026-04-03", "val": 123})
    with pytest.raises(RuntimeError, match="expected one Q1"):
        pe.latest_quarter("sales")


def test_incomplete_segment_table_is_refused(monkeypatch):
    import pandas as pd
    import pull_edgar as pe

    table = pd.DataFrame([
        ["PVG | Operating Segments", "", "", "", "", ""],
        ["Net sales", "", "", "100", "100", "100"],
        ["Adjusted EBITDA", "", "", "20", "20", "20"],
    ])
    monkeypatch.setattr(pe, "_curl", lambda url: b"synthetic")
    monkeypatch.setattr(pd, "read_html", lambda html: [table])
    with pytest.raises(RuntimeError, match="per segment"):
        pe.pull_segments()


@requires_foxf_data
def test_phase_a_checks_engine_ebitda(monkeypatch):
    import foxf_model as fm

    from pyfpa.analysis.reconcile import reconcile

    engine = fm.cashflow_from_config

    def incorrect(config):
        frame = engine(config)
        frame["ebitda"] *= 2
        return frame

    monkeypatch.setattr(fm, "cashflow_from_config", incorrect)
    result = reconcile(fm.phase_a_model("FY2025", "FY2024"), fm.phase_a_actual("FY2025", "FY2024"))
    assert not result.loc["adjusted_ebitda", "within_tolerance"]


@requires_foxf_data
def test_static_workbook_verification_preserves_previous_export(tmp_path, monkeypatch):
    import foxf_model as fm
    import pandas as pd
    import run_foxf as runner

    forecast, segments = fm.build_forecast()
    _, timing, price = runner.phase_d(forecast)
    destination = tmp_path / "forecast.xlsx"
    runner.export_forecast_workbook(destination, forecast, segments, timing, price)
    before = destination.read_bytes()
    read_excel = pd.read_excel

    def corrupted(*args, **kwargs):
        frame = read_excel(*args, **kwargs)
        if kwargs["sheet_name"] == "Forecast (monthly)":
            frame.iloc[0, 0] += 1_000_000
        return frame

    monkeypatch.setattr(pd, "read_excel", corrupted)
    with pytest.raises(AssertionError):
        runner.export_forecast_workbook(destination, forecast, segments, timing, price)
    assert destination.read_bytes() == before


@requires_foxf_data
def test_historical_candidate_does_not_read_holdout_actuals(monkeypatch):
    import foxf_model as fm

    expected = fm.historical_candidate(revenue_reversion=0.5, margin_reversion=0.05)
    for name in ("income_statement", "balance_sheet", "cash_flow"):
        frame = getattr(fm, name)().filter(items=["FY2023", "FY2024"])
        monkeypatch.setattr(fm, name, lambda frame=frame: frame)
    segments_for_year = fm.segments_for_year

    def training_segments(year):
        assert year in {"FY2023", "FY2024"}
        return segments_for_year(year)

    monkeypatch.setattr(fm, "segments_for_year", training_segments)
    assert fm.historical_candidate(revenue_reversion=0.5, margin_reversion=0.05) == expected


@requires_foxf_data
def test_historical_checks_detect_broken_rollup(monkeypatch):
    import foxf_model as fm

    engine = fm.cashflow_from_config

    def broken(config):
        frame = engine(config)
        frame["ebitda"] *= 2
        return frame

    monkeypatch.setattr(fm, "cashflow_from_config", broken)
    for epoch in fm.historical_research_epochs():
        assert next(check.result for check in epoch.checks if check.name == "segment rollup") == "fail"
        assert not epoch.evaluation.promotion_eligible
