from pathlib import Path

import pytest

pytest.importorskip("formulas")

import subprocess  # noqa: E402
import sys  # noqa: E402

from pyfpa.config.loader import load_config  # noqa: E402
from pyfpa.excel.model_workbook import model_to_excel  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DRILL = REPO / "examples" / "keldagrim-forge" / "drill.py"
CONFIG = REPO / "examples" / "keldagrim-forge" / "config.yaml"


def _run_drill(tmp_path, mutate=None):
    cfg = load_config(CONFIG)
    path = tmp_path / "submission.xlsx"
    model_to_excel(cfg, path)
    if mutate is not None:
        from openpyxl import load_workbook
        wb = load_workbook(path)
        mutate(wb)
        wb.save(path)
    return subprocess.run(
        [sys.executable, str(DRILL), str(path)],
        capture_output=True, text=True, cwd=REPO, timeout=300,
    )


def _labels(model):
    return {model.cell(row=r, column=1).value: r for r in range(2, model.max_row + 1)}


def test_drill_passes_on_a_faithful_workbook(tmp_path):
    result = _run_drill(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "structure: PASS" in result.stdout
    assert "numbers: PASS" in result.stdout
    assert "verdict: PASS" in result.stdout


def test_drill_fails_when_a_driver_is_typed_over_a_formula(tmp_path):
    def mutate(wb):
        model = wb["Model"]
        model.cell(row=_labels(model)["revenue"], column=3, value=420000.0)

    result = _run_drill(tmp_path, mutate=mutate)
    assert result.returncode == 1
    assert "structure: FAIL" in result.stdout
    assert "verdict: FAIL" in result.stdout


def test_drill_fails_when_the_numbers_diverge(tmp_path):
    # a wrong formula holds the structure together (the self-checks still tie)
    # but the engine comparison catches the divergence
    def mutate(wb):
        model = wb["Model"]
        row = _labels(model)["revenue"]
        model.cell(row=row, column=3, value=f"=B{row}*1.5")

    result = _run_drill(tmp_path, mutate=mutate)
    assert result.returncode == 1
    assert "structure: PASS" in result.stdout
    assert "numbers: FAIL" in result.stdout


def test_drill_fails_when_a_check_row_is_broken(tmp_path):
    def mutate(wb):
        model = wb["Model"]
        checks = [r for label, r in _labels(model).items()
                  if isinstance(label, str) and label.startswith("check_")]
        model.cell(row=checks[0], column=3, value="=123")

    result = _run_drill(tmp_path, mutate=mutate)
    assert result.returncode == 1
    assert "numbers: FAIL" in result.stdout
    assert "non-zero" in result.stdout
