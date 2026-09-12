import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "run_demo", REPO_ROOT / "examples/ridgeline/run_demo.py"
)


def _load_run_demo():
    assert _SPEC is not None and _SPEC.loader is not None
    module = importlib.util.module_from_spec(_SPEC)
    _SPEC.loader.exec_module(module)
    return module.run_demo


def test_run_demo_writes_artifacts(tmp_path):
    run_demo = _load_run_demo()
    result = run_demo(tmp_path)
    briefing = tmp_path / "briefing.md"
    excel = tmp_path / "forecast.xlsx"
    assert briefing.exists()
    assert excel.exists()
    # returned figures match the locked golden numbers
    assert result["revenue_total"] == 6_000_000
    assert result["runway_min_cash"] == -146_000
    assert result["runway_first_negative_week"] == 3
    # briefing file contains the headline and runway section
    text = briefing.read_text()
    assert "# Ridgeline Chair Co." in text
    assert "## 13-Week Cash Runway" in text


def test_demo_refuses_a_failed_formula_verification(tmp_path, monkeypatch):
    run_demo = _load_run_demo()
    monkeypatch.setitem(run_demo.__globals__, "verify_workbook", lambda *args: SimpleNamespace(passed=False, failures=["synthetic mismatch"]))
    with pytest.raises(ValueError, match="workbook verification failed"):
        run_demo(tmp_path)
