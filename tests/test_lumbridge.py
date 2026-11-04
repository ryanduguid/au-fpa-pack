# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: FSL-1.1-ALv2

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


def test_the_shipped_workbook_follows_its_receipt_delay_control(tmp_path):
    """Change Assumptions!B2 in one exported file, as the README tells users to,
    and check both Model and Cash 13 weeks against the engine at that delay."""
    import formulas

    from pyfpa.excel.verify import verify_workbook

    api = functions()
    path = tmp_path / "lumbridge.xlsx"
    api["export_workbook"](path, api["forecast"](delay_days=0))
    model = formulas.ExcelModel().loads(str(path)).finish()
    columns = {"C": "receipts", "D": "disbursements", "E": "net_cash", "F": "ending_cash"}
    for delay in (0, 1, 44, 45, 46, 120):
        result = api["forecast"](delay_days=delay)
        report = verify_workbook(path, result["monthly"], inputs={"Assumptions!B2": delay})
        assert report.passed, (delay, report.failures)
        solution = model.calculate(inputs={f"'[{path.name}]ASSUMPTIONS'!B2": delay})
        assert solution[f"'[{path.name}]CASH 13 WEEKS'!B20"].value[0][0] == delay
        for week, (_, row) in enumerate(result["weekly"].iterrows(), start=2):
            for col, name in columns.items():
                got = solution[f"'[{path.name}]CASH 13 WEEKS'!{col}{week}"].value[0][0]
                assert float(got) == pytest.approx(row[name]), (delay, week, name)
    # The control must move the answer, or the loop above proves nothing.
    # Every spelling of the control must reach it, or an override could do nothing.
    for target in ("Assumptions!B2", "assumptions!$B$2", "'Assumptions'!b2"):
        late = verify_workbook(path, api["forecast"](delay_days=0)["monthly"], inputs={target: 45})
        assert not late.passed, target
    for target in ("Assumptions!Z99", "Assumptions!B2:B3", "Cash 13 weeks!B20", "Nowhere!B2"):
        with pytest.raises(ValueError, match="not an existing value cell"):
            verify_workbook(path, api["forecast"]()["monthly"], inputs={target: 1})


def test_each_workbook_check_fails_when_its_source_value_changes(tmp_path):
    """Change source cells, as an Excel user could, and require exactly the
    expected ties to fail and the status cell to name the first; unchanged, all pass."""
    import formulas
    from openpyxl import load_workbook

    from pyfpa.excel.verify import verify_workbook

    api = functions()
    path = tmp_path / "lumbridge.xlsx"
    result = api["forecast"]()
    monthly = result["monthly"]
    api["export_workbook"](path, result)
    wb = load_workbook(path)
    labels = {cell.value: cell.row for cell in wb["Model"]["A"] if cell.value}
    assert labels["Workbook checks"] == 27, "the README and reviewer key cite Model!B27"
    status = f"'[{path.name}]MODEL'!B{labels['Workbook checks']}"
    checks = [label for label, _ in sorted(labels.items(), key=lambda item: item[1]) if label.startswith("check_")]
    assert checks == ["check_cash_roll_forward", "check_direct_vs_indirect_cash", "check_gst_liability",
                      "check_receivables_open_invoices"]
    model = formulas.ExcelModel().loads(str(path)).finish()

    for delay in (0, 45, 120):
        report = verify_workbook(path, api["forecast"](delay_days=delay)["monthly"], inputs={"Assumptions!B2": delay})
        assert report.passed, (delay, report.failures)
        solution = model.calculate(inputs={f"'[{path.name}]ASSUMPTIONS'!B2": delay})
        assert solution[status].value[0][0] == "All checks pass", delay

    def row_of(sheet, column, text):
        return next(cell.row for cell in wb[sheet][column] if cell.value == text)

    september_30 = (pd.Timestamp("2026-09-30") - pd.Timestamp("1899-12-30")).days
    open_f = row_of("Cash dates", "A", "OPEN-F")
    perturbations = [
        # A receipt dated before the forecast drops out of every monthly window,
        # so its invoice also stops matching the receivables.
        ({f"Cash dates!B{open_f}": september_30}, {"check_cash_roll_forward", "check_receivables_open_invoices"}),
        # Interest expense moves profit but no dated payment.
        ({f"Sources!B{row_of('Sources', 'A', 'Interest expense')}": -300}, {"check_direct_vs_indirect_cash"}),
        # A part settlement leaves some opening GST in the liability.
        ({f"Cash dates!E{row_of('Cash dates', 'F', 'GST settlement')}": 12000}, {"check_gst_liability"}),
        # A missing customer receipt: receivables absorb it, so the profit bridge still ties.
        ({f"Cash dates!D{open_f}": 0}, {"check_receivables_open_invoices"}),
        # 2,000 of the opening bank balance misclassified as receivables; the balance sheet still balances.
        ({f"Sources!B{row_of('Sources', 'A', 'Business Bank Account')}": 28000,
          f"Sources!B{row_of('Sources', 'A', 'Accounts Receivable')}": 68000}, {"check_receivables_open_invoices"}),
        # Revenue overstated by 1,000 with no invoice behind it: receivables absorb it, so the other ties hold.
        ({f"Sources!B{row_of('Sources', 'A', 'Sales - Varrock maintenance')}": 41000}, {"check_receivables_open_invoices"}),
    ]
    assert set().union(*(failing for _, failing in perturbations)) == set(checks)
    for inputs, failing in perturbations:
        report = verify_workbook(path, monthly, inputs=inputs)
        failed = {failure.split()[0] for failure in report.failures if failure.startswith("check_")}
        assert failed == failing, (inputs, report.failures)
        solution = model.calculate(inputs={
            f"'[{path.name}]{target.rpartition('!')[0].upper()}'!{target.rpartition('!')[2]}": value
            for target, value in inputs.items()})
        first = next(check for check in checks if check in failing)
        assert solution[status].value[0][0] == f"{first} fails", inputs
