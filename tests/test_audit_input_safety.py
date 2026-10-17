"""Audit regressions for source preservation and finite forecasting inputs."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyfpa.cash13.schemas import Cash13Config, WeeklyFlow
from pyfpa.config.schemas import Channel
from pyfpa.models.revenue import revenue_from_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("alias", ["same", "relative", "source_link", "output_link", "hard_link"])
def test_export_keeps_source_configuration(tmp_path, run_cli, monkeypatch, alias):
    import pyfpa.excel.model_workbook as workbook

    assert run_cli("init", str(tmp_path)).returncode == 0
    config = tmp_path / "config.xlsx"
    original = (ROOT / "examples/ridgeline/config.yaml").read_bytes()
    config.write_bytes(original)
    source, output = config, config
    try:
        if alias == "relative":
            (tmp_path / "child").mkdir()
            output = tmp_path / "child" / ".." / config.name
        elif alias == "source_link":
            source = tmp_path / "source.yaml"
            source.symlink_to(config)
        elif alias == "output_link":
            output = tmp_path / "model.xlsx"
            output.symlink_to(config)
        elif alias == "hard_link":
            output = tmp_path / "model.xlsx"
            output.hardlink_to(config)
    except OSError as error:
        pytest.skip(f"File links unavailable: {error}")
    writes = []

    def unexpected_write(*args):
        writes.append(args)

    monkeypatch.setattr(workbook, "model_to_excel", unexpected_write)
    result = run_cli("model-export", str(tmp_path), "--config", str(source), "--out", str(output))
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["type"] == "export_failed"
    assert not writes
    assert config.read_bytes() == source.read_bytes() == original


def test_export_requires_workbook_suffix_before_writing(tmp_path, run_cli):
    assert run_cli("init", str(tmp_path)).returncode == 0
    output = tmp_path / "report.yaml"
    output.write_bytes(b"previous output")
    result = run_cli("model-export", str(tmp_path), "--config",
                     str(ROOT / "examples/ridgeline/config.yaml"), "--out", str(output))
    assert result.returncode == 1
    assert output.read_bytes() == b"previous output"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_monthly_and_weekly_reject_non_finite_inputs(value):
    with pytest.raises(ValidationError):
        Channel(name="Synthetic", annual_revenue=1200, seasonality=[value] + [1.0] * 11, cogs_pct=0.5)
    with pytest.raises(ValidationError):
        Cash13Config(opening_cash=value)
    with pytest.raises(ValidationError):
        WeeklyFlow(name="Synthetic", amount=value, start_week=1)


def test_finite_seasonality_retains_revenue(sample_config):
    revenue = revenue_from_config(sample_config)
    assert not revenue.isna().any().any()
    assert revenue["total"].sum() == pytest.approx(1200)


def test_seasonality_total_cannot_overflow_to_silent_zero_revenue():
    with pytest.raises(ValidationError, match="finite"):
        Channel(name="Synthetic", annual_revenue=1200, seasonality=[1e308] * 12, cogs_pct=0.5)
