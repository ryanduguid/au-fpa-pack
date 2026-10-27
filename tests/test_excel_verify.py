import pytest

pytest.importorskip("formulas")

from pyfpa.config.schemas import EntityConfig
from pyfpa.excel.model_workbook import model_to_excel
from pyfpa.excel.verify import verify_workbook
from pyfpa.models.cashflow import cashflow_from_config


def _simple_cfg():
    return EntityConfig.model_validate({
        "name": "T", "start_month": "2026-01", "horizon_months": 6, "tax_rate": 0.0,
        "channels": [{"name": "A", "annual_revenue": 120_000.0, "growth_rate": 0.0,
                      "seasonality": [1.0] * 12, "cogs_pct": 0.5}],
        "opex": [], "debt": [],
        "working_capital": {"dso_days": 0.0, "dpo_days": 0.0, "dio_days": 0.0},
        "opening_balances": {"cash": 0.0},
    })


def test_verify_passes_on_faithful_workbook(tmp_path):
    cfg = _simple_cfg()
    path = tmp_path / "m.xlsx"
    model_to_excel(cfg, path)
    report = verify_workbook(path, cashflow_from_config(cfg))
    assert report.passed, report.failures


def test_verify_fails_on_corrupted_formula(tmp_path):
    from openpyxl import load_workbook
    cfg = _simple_cfg()
    path = tmp_path / "m.xlsx"
    model_to_excel(cfg, path)
    wb = load_workbook(path)
    model = wb["Model"]
    labels = {model.cell(row=r, column=1).value: r for r in range(2, model.max_row + 1)}
    model.cell(row=labels["gross_profit"], column=3, value="=1234567")
    wb.save(path)
    report = verify_workbook(path, cashflow_from_config(cfg))
    assert not report.passed
    assert any("gross_profit" in f for f in report.failures)


def test_missing_formulas_dependency_message():
    import builtins

    import pyfpa.excel.verify as v
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "formulas":
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        with pytest.raises(RuntimeError, match="pip install formulas"):
            v._load_formulas()
    finally:
        builtins.__import__ = real_import


def test_verify_fails_cleanly_on_excel_error_cell(tmp_path):
    # an errored cell (#DIV/0!) must produce a failing report, never a crash
    from openpyxl import load_workbook
    cfg = _simple_cfg()
    path = tmp_path / "m.xlsx"
    model_to_excel(cfg, path)
    wb = load_workbook(path)
    model = wb["Model"]
    labels = {model.cell(row=r, column=1).value: r for r in range(2, model.max_row + 1)}
    model.cell(row=labels["gross_profit"], column=3, value="=1/0")
    wb.save(path)
    report = verify_workbook(path, cashflow_from_config(cfg))
    assert not report.passed
    assert any("error" in f.lower() for f in report.failures)


def test_verify_fails_when_a_required_output_is_missing(tmp_path):
    # F070: renaming a required line used to remove it from the comparison, so a
    # workbook missing that output still reported passed.
    from openpyxl import load_workbook
    cfg = _simple_cfg()
    path = tmp_path / "m.xlsx"
    model_to_excel(cfg, path)
    expected = cashflow_from_config(cfg)
    wb = load_workbook(path)
    model = wb["Model"]
    labels = {model.cell(row=r, column=1).value: r for r in range(2, model.max_row + 1)}
    row = labels["ending_cash"]
    model.cell(row=row, column=1, value="ending_cash_renamed")
    for m in range(len(expected.index)):
        model.cell(row=row, column=2 + m, value=-1_000_000.0)
    wb.save(path)
    report = verify_workbook(path, expected)
    assert not report.passed
    assert any("ending_cash: required output missing" in f for f in report.failures)


def test_verify_fails_when_a_check_row_is_non_zero(tmp_path):
    # a check_ row is the workbook's own tie-out: a non-zero month fails the
    # verification even when every engine line still matches
    from openpyxl import load_workbook
    cfg = _simple_cfg()
    path = tmp_path / "m.xlsx"
    model_to_excel(cfg, path)
    wb = load_workbook(path)
    model = wb["Model"]
    rows = [
        r for r in range(2, model.max_row + 1)
        if isinstance(model.cell(row=r, column=1).value, str)
        and model.cell(row=r, column=1).value.startswith("check_")
    ]
    model.cell(row=rows[0], column=3, value="=123")
    wb.save(path)
    report = verify_workbook(path, cashflow_from_config(cfg))
    assert not report.passed
    assert any("check" in f and "non-zero" in f for f in report.failures)


def test_verify_reports_a_non_numeric_check_result(tmp_path):
    # a check row that stops returning a number must fail cleanly, never crash
    from openpyxl import load_workbook
    cfg = _simple_cfg()
    path = tmp_path / "m.xlsx"
    model_to_excel(cfg, path)
    wb = load_workbook(path)
    model = wb["Model"]
    rows = [
        r for r in range(2, model.max_row + 1)
        if isinstance(model.cell(row=r, column=1).value, str)
        and model.cell(row=r, column=1).value.startswith("check_")
    ]
    model.cell(row=rows[0], column=3, value='="boom"')
    wb.save(path)
    report = verify_workbook(path, cashflow_from_config(cfg))
    assert not report.passed
    assert any("expected 0" in f for f in report.failures)


def test_verify_fails_when_the_expected_periods_do_not_match(tmp_path):
    # F070: months were compared by position, so a request for a different year
    # passed against an unchanged workbook.
    import pandas as pd
    cfg = _simple_cfg()
    path = tmp_path / "m.xlsx"
    model_to_excel(cfg, path)
    expected = cashflow_from_config(cfg)
    shifted = expected.copy()
    shifted.index = pd.period_range("2027-01", periods=len(expected.index), freq="M")
    report = verify_workbook(path, shifted)
    assert not report.passed
    assert any("workbook header" in f for f in report.failures)
    # Control: the same frame on its own periods still verifies.
    assert verify_workbook(path, expected).passed


def test_verify_accepts_datetime_month_headers(tmp_path):
    # A company exporter may write month start datetimes rather than period
    # strings; the period check must read both.
    from openpyxl import load_workbook
    cfg = _simple_cfg()
    path = tmp_path / "m.xlsx"
    model_to_excel(cfg, path)
    expected = cashflow_from_config(cfg)
    wb = load_workbook(path)
    model = wb["Model"]
    for m, period in enumerate(expected.index):
        model.cell(row=1, column=2 + m, value=period.start_time.to_pydatetime())
    wb.save(path)
    assert verify_workbook(path, expected).passed


def _labelled_rows(model):
    return {model.cell(row=r, column=1).value: r for r in range(2, model.max_row + 1)}


def test_verify_reports_a_blank_header_and_unevaluated_cells(tmp_path):
    # A blank header, a required line with no cells at all and a blank check
    # month each fail by name; none is skipped.
    from openpyxl import load_workbook
    cfg = _simple_cfg()
    path = tmp_path / "m.xlsx"
    model_to_excel(cfg, path)
    expected = cashflow_from_config(cfg)
    wb = load_workbook(path)
    model = wb["Model"]
    labels = _labelled_rows(model)
    model.cell(row=1, column=7).value = None
    model.cell(row=labels["check_cash_roll"], column=3).value = None
    model.cell(row=model.max_row + 1, column=1, value="extra_line")
    wb.save(path)
    expected["extra_line"] = 0.0
    report = verify_workbook(path, expected)
    assert not report.passed  # nosec B101: pytest outcome assertion
    assert "month 6: workbook header '' vs expected '2026-06'" in report.failures  # nosec B101: pytest outcome assertion
    assert any(f.startswith("extra_line month 1: cell not evaluated") for f in report.failures)  # nosec B101: pytest outcome assertion
    assert any(f.startswith("check_cash_roll month 2: cell not evaluated") for f in report.failures)  # nosec B101: pytest outcome assertion


@pytest.mark.parametrize("raw", [None, float("nan")])
def test_verify_reports_a_cell_that_evaluates_to_nothing(tmp_path, monkeypatch, raw):
    # The formulas engine can hand back None or NaN for a cell; that is a
    # failure, never a silent match.
    import types

    from openpyxl import load_workbook

    import pyfpa.excel.verify as v

    cfg = _simple_cfg()
    path = tmp_path / "m.xlsx"
    model_to_excel(cfg, path)
    row = _labelled_rows(load_workbook(path)["Model"])["gross_profit"]
    real = v._load_formulas()

    class Model:
        def loads(self, name):
            self.inner = real.ExcelModel().loads(name)
            return self

        def finish(self):
            self.inner.finish()
            return self

        def calculate(self, **kwargs):
            solution = dict(self.inner.calculate(**kwargs))
            solution[f"'[m.xlsx]MODEL'!C{row}"] = types.SimpleNamespace(value=[[raw]])
            return solution

    monkeypatch.setattr(v, "_load_formulas", lambda: types.SimpleNamespace(ExcelModel=Model))
    report = verify_workbook(path, cashflow_from_config(cfg))
    assert not report.passed  # nosec B101: pytest outcome assertion
    assert "gross_profit month 2: workbook returned NaN/None" in report.failures  # nosec B101: pytest outcome assertion
