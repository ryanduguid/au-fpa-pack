"""Catch omitted liabilities, lost receipts and cash timing errors in the NSW case."""
import runpy
from pathlib import Path

import pandas as pd
import pytest

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "lumbridge-services"


def functions():
    path = EXAMPLE / "models" / "generated" / "lumbridge.py"
    assert path.exists(), "The approved Lumbridge worked example is missing"
    return runpy.run_path(str(path))


def test_profit_and_cash_reconcile_with_unpaid_tax_and_customer_balances():
    result = functions()["forecast"]()
    monthly = result["monthly"]
    assert monthly["Revenue"].tolist() == [60000, 60000, 60000]
    assert monthly["Profit before tax"].tolist() == pytest.approx([11985.85] * 3)
    # Monthly receipts 66,000 less 48,360 payments; October also settles 15,600 tax.
    assert monthly["Closing cash"].tolist() == pytest.approx([32040, 49680, 67320])
    assert monthly["Receivables"].tolist() == [66000] * 3
    assert monthly["GST payable"].tolist() == [4200, 8400, 12600]
    assert monthly["PAYG withholding payable"].tolist() == [5000] * 3
    assert monthly["Cash reconciliation difference"].abs().max() < 0.01
    assert result["weekly"]["ending_cash"].iloc[-1] == pytest.approx(67320)
    assert result["daily"]["ending_cash"].min() == 16800
    assert str(result["daily"]["ending_cash"].idxmin().date()) == "2026-10-07"


def test_delayed_receipt_changes_cash_and_receivables_without_changing_profit():
    forecast = functions()["forecast"]
    base, late = forecast(), forecast(delay_days=45)
    pd.testing.assert_series_equal(base["monthly"]["Profit before tax"], late["monthly"]["Profit before tax"])
    assert late["monthly"]["Closing cash"].iloc[0] == pytest.approx(base["monthly"]["Closing cash"].iloc[0] - 44000)
    assert late["monthly"]["Receivables"].iloc[0] == 110000
    assert late["daily"]["ending_cash"].min() == -25160
    assert str(late["daily"]["ending_cash"].idxmin().date()) == "2026-11-06"
    assert late["monthly"]["Cash reconciliation difference"].abs().max() < 0.01
    assert late["weekly"]["ending_cash"].iloc[-1] == base["weekly"]["ending_cash"].iloc[-1]
    beyond = forecast(delay_days=100)
    assert beyond["monthly"]["Receivables"].iloc[-1] == 110000
    assert beyond["weekly"]["ending_cash"].iloc[-1] == 23320
    with pytest.raises(ValueError, match="delay"):
        forecast(delay_days=-1)


def test_source_reconciliation_refuses_an_unmapped_account(tmp_path):
    import shutil

    data = tmp_path / "data"
    shutil.copytree(EXAMPLE / "data", data)
    with (data / "xero_pl.csv").open("a", encoding="utf-8") as handle:
        handle.write("999,Unexplained income,100,\n")
    with pytest.raises(ValueError, match="account"):
        functions()["forecast"](data=data)


def test_workbook_formulas_match_both_cash_scenarios(tmp_path):
    from pyfpa.excel.verify import verify_workbook

    api = functions()
    for delay in (0, 45):
        result = api["forecast"](delay_days=delay)
        path = tmp_path / f"case-{delay}.xlsx"
        api["export_workbook"](path, result)
        report = verify_workbook(path, result["monthly"])
        assert report.passed, report.failures
        assert report.lines_checked == len(result["monthly"].columns)
