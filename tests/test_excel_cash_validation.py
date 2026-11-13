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


def _large_config(scale=1_000_000):
    return EntityConfig.model_validate({
        "name": "AUD precision boundary", "start_month": "2026-07", "horizon_months": 24,
        "tax_rate": 0.25,
        "channels": [{"name": "Services", "annual_revenue": 1_234_567.89 * scale,
                      "growth_rate": 0.034, "seasonality": [1, 1, 1.5, 1, 1, 1, 1, 1, 1, 1, 1, 1.5],
                      "cogs_pct": 0.453}],
        "opex": [{"name": "Rent", "kind": "fixed", "monthly_amount": 7_890.12 * scale}],
        "debt": [{"name": "Loan", "kind": "term_loan", "opening_balance": 123_456.78 * scale,
                  "annual_rate": 0.074, "monthly_principal": 9_876.54 * scale}],
        "working_capital": {"dso_days": 12.5, "dpo_days": 14.3, "dio_days": 18},
        "opening_balances": {"cash": 1_000_000 * scale, "ar": 10_000 * scale,
                             "ap": 5_000 * scale, "inventory": 10_000 * scale},
        "da_monthly": 1_234.56 * scale, "capex_monthly": 4_567.89 * scale,
    })


def _cancellation_config():
    revenue = 12_000_000_000_123 / 12
    cogs = revenue * 0.4
    working_capital = -(revenue * 12.5 / 30 - 10_000) + (cogs * 14.3 / 30 - 5_000) - (cogs * 18 / 30 - 10_000)
    return EntityConfig.model_validate({
        "name": "AUD gross cash cancellation", "start_month": "2026-07", "horizon_months": 1,
        "tax_rate": 0,
        "channels": [{"name": "Services", "annual_revenue": revenue * 12,
                      "growth_rate": 0, "seasonality": [1] * 12, "cogs_pct": 0.4}],
        "opex": [{"name": "Cash costs", "kind": "fixed",
                  "monthly_amount": revenue - cogs + working_capital - 1_234.56}],
        "working_capital": {"dso_days": 12.5, "dpo_days": 14.3, "dio_days": 18},
        "opening_balances": {"cash": 1_000_000, "ar": 10_000, "ap": 5_000, "inventory": 10_000},
        "da_monthly": 789.01, "capex_monthly": 1_234.56,
    })


@pytest.mark.parametrize("scale", [1, 1_000, 1_000_000])
def test_correct_large_cash_forecasts_do_not_fail_due_to_roundoff(tmp_path, scale):
    cfg = _large_config(scale)
    path = tmp_path / "model.xlsx"
    model_to_excel(cfg, path)
    report = verify_workbook(path, cashflow_from_config(cfg))
    assert report.passed, report.failures


def test_correct_near_zero_net_cash_with_large_gross_flows_verifies(tmp_path):
    cfg = _cancellation_config()
    expected = cashflow_from_config(cfg)
    assert expected.revenue.iloc[0] > 1e12
    assert abs(expected.change_in_cash.iloc[0]) < 1e-4
    path = tmp_path / "model.xlsx"
    model_to_excel(cfg, path)
    report = verify_workbook(path, expected)
    assert report.passed, report.failures


@pytest.mark.parametrize("make_config", [_large_config, _cancellation_config])
def test_large_gross_flows_do_not_hide_a_propagated_cash_error(tmp_path, make_config):
    cfg = make_config()
    path = tmp_path / "model.xlsx"
    model_to_excel(cfg, path)
    expected = cashflow_from_config(cfg)
    book = load_workbook(path)
    try:
        sheet = book["Model"]
        rows = {sheet.cell(r, 1).value: r for r in range(2, sheet.max_row + 1)}
        sheet.cell(rows["operating_cash_flow"], 2).value += "+10000"
        book.save(path)
    finally:
        book.close()
    for line in ["operating_cash_flow", "free_cash_flow", "change_in_cash"]:
        expected.loc[expected.index[0], line] += 10_000
    expected["ending_cash"] += 10_000
    report = verify_workbook(path, expected)
    assert not report.passed
    assert report.failures
    assert all(f.startswith("check_direct_cash ") for f in report.failures)


@pytest.mark.parametrize("formula", ["=-1", "=1/0", '="unavailable"', "=TRUE()", None])
def test_verification_refuses_invalid_or_missing_cash_rounding_allowance(tmp_path, formula):
    cfg = _config()
    path = tmp_path / "model.xlsx"
    model_to_excel(cfg, path)
    book = load_workbook(path)
    try:
        sheet = book["Model"]
        rows = {sheet.cell(r, 1).value: r for r in range(2, sheet.max_row + 1)}
        if formula is None:
            sheet.cell(rows["direct_cash_rounding"], 1, "removed")
        else:
            sheet.cell(rows["direct_cash_rounding"], 2, formula)
        book.save(path)
    finally:
        book.close()
    report = verify_workbook(path, cashflow_from_config(cfg))
    assert not report.passed
    assert all("invalid direct cash rounding allowance" in f for f in report.failures)


@pytest.mark.parametrize("label,make_config,tolerance,difference", [
    ("check_direct_cash", _config, 0, 1e-12),
    ("check_gross_profit", _large_config, 1e-6, 0.001),
])
def test_rounding_allowance_preserves_exact_and_existing_check_tolerances(
    tmp_path, label, make_config, tolerance, difference
):
    cfg = make_config()
    path = tmp_path / "model.xlsx"
    model_to_excel(cfg, path)
    book = load_workbook(path)
    try:
        sheet = book["Model"]
        rows = {sheet.cell(r, 1).value: r for r in range(2, sheet.max_row + 1)}
        sheet.cell(rows[label], 2, f"={difference}")
        book.save(path)
    finally:
        book.close()
    report = verify_workbook(path, cashflow_from_config(cfg), rel_tol=tolerance)
    assert not report.passed
    assert len(report.failures) == 1
    assert report.failures[0].startswith(label + " ")
