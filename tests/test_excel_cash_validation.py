from pathlib import Path

import pytest
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from pyfpa.config.schemas import EntityConfig
from pyfpa.excel.model_workbook import model_to_excel
from pyfpa.excel.verify import verify_workbook
from pyfpa.models.cashflow import cashflow_from_config


def _config():
    return EntityConfig.model_validate({
        "name": "AUD cash bridge", "start_month": "2026-07", "horizon_months": 6,
        "tax_rate": 0.25,
        "channels": [{"name": "Services", "annual_revenue": 12_000, "growth_rate": 0,
                      "seasonality": [1] * 12, "cogs_pct": 0.4}],
        "opex": [{"name": "Rent", "kind": "fixed", "monthly_amount": 200}],
        "debt": [{"name": "Term", "kind": "term_loan", "opening_balance": 600,
                  "annual_rate": 0.12, "monthly_principal": 100}],
        "working_capital": {"dso_days": 0, "dpo_days": 0, "dio_days": 0},
        "opening_balances": {"cash": 5_000}, "da_monthly": 50, "capex_monthly": 75,
    })


@pytest.mark.parametrize("month", [0, 5])
@pytest.mark.parametrize("omitted", ["da", "tax", "capex", "principal"])
def test_direct_cash_check_detects_errors_propagating_through_the_profit_bridge(
    tmp_path, month, omitted
):
    cfg = _config()
    path = tmp_path / "model.xlsx"
    model_to_excel(cfg, path)
    expected = cashflow_from_config(cfg)
    book = load_workbook(path)
    try:
        sheet = book["Model"]
        rows = {sheet.cell(r, 1).value: r for r in range(2, sheet.max_row + 1)}
        column = get_column_letter(month + 2)
        owner = {"da": "operating_cash_flow", "tax": "operating_cash_flow",
                 "capex": "free_cash_flow", "principal": "change_in_cash"}[omitted]
        direction = -1 if omitted == "da" else 1
        cell = sheet.cell(rows[owner], month + 2)
        cell.value += f"{direction:+d}*{column}{rows[omitted]}"
        book.save(path)
    finally:
        book.close()
    difference = direction * expected[omitted].iloc[month]
    downstream = ["operating_cash_flow", "free_cash_flow", "change_in_cash"]
    for line in downstream[downstream.index(owner):]:
        expected.loc[expected.index[month], line] += difference
    expected.loc[expected.index[month]:, "ending_cash"] += difference
    # All requested outputs now match the corrupted chain. The independent
    # receipts/payments bridge must still detect the missing cash component.
    report = verify_workbook(path, expected)
    assert not report.passed
    assert report.failures
    assert all(f.startswith("check_direct_cash ") for f in report.failures)


@pytest.mark.parametrize("rel_tol", [float("nan"), float("inf"), -float("inf"), -0.01])
def test_verification_rejects_invalid_tolerance_before_opening_a_workbook(rel_tol):
    with pytest.raises(ValueError, match="finite and non-negative"):
        verify_workbook(Path("not-opened.xlsx"), cashflow_from_config(_config()), rel_tol=rel_tol)


@pytest.mark.parametrize("dimension", ["rows", "columns"])
def test_verification_rejects_empty_expected_data_before_opening_a_workbook(dimension):
    expected = cashflow_from_config(_config())
    empty = expected.iloc[:0] if dimension == "rows" else expected.iloc[:, :0]
    with pytest.raises(ValueError, match="expected.*empty"):
        verify_workbook(Path("not-opened.xlsx"), empty)


def test_zero_tolerance_remains_supported(tmp_path):
    cfg = _config()
    path = tmp_path / "model.xlsx"
    model_to_excel(cfg, path)
    report = verify_workbook(path, cashflow_from_config(cfg), rel_tol=0)
    assert report.passed, report.failures
