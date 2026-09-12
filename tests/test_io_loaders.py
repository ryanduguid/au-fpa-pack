from pathlib import Path

import pytest

import pyfpa
from pyfpa.cash13.schemas import Cash13Config
from pyfpa.io.loaders import load_cash13_config
from pyfpa.portfolio.manifest import load_portfolio
from pyfpa.research.objective import (
    MetricObjective,
    ResearchObjective,
    load_research_objective,
    save_research_objective,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_load_cash13_config():
    cfg = load_cash13_config(REPO_ROOT / "examples/ridgeline/cash13.yaml")
    assert isinstance(cfg, Cash13Config)
    assert cfg.weeks == 13
    assert len(cfg.receipts) == 4


def test_load_cash13_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_cash13_config(REPO_ROOT / "examples/nope.yaml")


def test_io_public_exports():
    for name in ["load_cash13_config", "read_pl_csv", "to_briefing_md",
                 "forecast_to_excel"]:
        assert hasattr(pyfpa, name), f"missing public export: {name}"


def _simulate_non_utf8_locale(monkeypatch):
    """Make an implicit `encoding=None` decode as cp1252, as a Windows box would.

    CPython reads the locale encoding in C, so patching `locale.getpreferredencoding`
    would not reach `Path.read_text`. Substituting the default at the call site is
    the same simulation and is deterministic on every runner.
    """
    original = Path.read_text

    def read_text(self, encoding=None, errors=None, **kwargs):
        return original(self, encoding=encoding or "cp1252", errors=errors, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)


def test_yaml_helpers_round_trip_non_ascii_under_a_non_utf8_locale(tmp_path, monkeypatch):
    """The research and portfolio stores must not depend on the platform encoding."""
    manifest = tmp_path / "portfolio.yaml"
    manifest.write_text(
        "library: lib\nclients:\n  - path: Ngô Café\n    type: café\n",
        encoding="utf-8",
    )
    _simulate_non_utf8_locale(monkeypatch)

    portfolio = load_portfolio(manifest)
    assert portfolio.clients[0].path == "Ngô Café"
    assert portfolio.clients[0].type == "café"

    objective_path = tmp_path / "objective.yaml"
    save_research_objective(
        ResearchObjective(metrics=[MetricObjective(name="écart moyen", weight=1.0)]),
        objective_path,
    )
    assert load_research_objective(objective_path).metrics[0].name == "écart moyen"
