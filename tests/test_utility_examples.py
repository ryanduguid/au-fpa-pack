"""Independent arithmetic and missing-evidence checks for the utility examples."""
import copy
import hashlib
import json
import runpy
import shutil
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
LUMBRIDGE = ROOT / "examples/lumbridge-services"
GENERATED = LUMBRIDGE / "models/generated"


@pytest.fixture
def refresh_functions(monkeypatch):
    monkeypatch.syspath_prepend(str(GENERATED))
    return runpy.run_path(str(GENERATED / "recurring.py"))


@pytest.fixture
def data(tmp_path):
    target = tmp_path / "data"
    shutil.copytree(LUMBRIDGE / "data", target)
    return target


def invoke(functions, data):
    return functions["refresh"](data / "refresh-actuals.csv", data / "refresh-controls.json", data / "receipt-assumptions.csv")


def test_refresh_keeps_original_forecast_and_scores_closed_period(refresh_functions, tmp_path):
    output = tmp_path / "refresh"
    result = refresh_functions["run"](output)
    assert result["errors"]["cash_error"].tolist() == [-34000]
    assert result["observed"] == {"ending_cash": -1960, "receipts": 32000}
    assert result["future_cash"]["closing_cash"].tolist() == [49680, 67320]
    for name in ("xero_bs.csv", "invoices.csv", "payments.csv"):
        assert result["sources"][name] == hashlib.sha256((LUMBRIDGE / "data" / name).read_bytes()).hexdigest()
    remaining = result["future_items"].set_index("id")
    assert remaining.loc["OPEN-V", "receipts"] == 34000
    assert "OPEN-F" not in remaining.index
    assert result["base"]["monthly"]["Closing cash"].tolist() == [32040, 49680, 67320]
    original = (output / "original-forecast.yaml").read_bytes()
    assert (output / "original-scored.yaml").read_bytes() != original
    with pytest.raises(FileExistsError):
        refresh_functions["run"](output)
    assert (output / "original-forecast.yaml").read_bytes() == original


def test_changed_base_source_stops_refresh(refresh_functions, data, monkeypatch):
    namespace = refresh_functions["refresh"].__globals__
    original = namespace["forecast"]

    def change_source(*args, **kwargs):
        result = original(*args, **kwargs)
        path = data / "xero_bs.csv"
        path.write_bytes(path.read_bytes() + b"\n")
        return result

    monkeypatch.setitem(namespace, "forecast", change_source)
    with pytest.raises(ValueError, match="base forecast source changed"):
        invoke(refresh_functions, data)


@pytest.mark.parametrize("mutation", ["duplicate_bank_id", "unmapped", "future_actual", "overpaid", "wrong_category", "missing_amount"])
def test_invalid_actuals_stop_refresh(refresh_functions, data, mutation):
    path = data / "refresh-actuals.csv"
    frame = pd.read_csv(path)
    if mutation == "duplicate_bank_id":
        frame.loc[1, "transaction_id"] = frame.loc[0, "transaction_id"]
    elif mutation == "unmapped":
        frame.loc[0, "source_id"] = "unknown"
    elif mutation == "future_actual":
        frame.loc[0, "date"] = "2026-11-01"
    elif mutation == "overpaid":
        frame.loc[0, "receipts"] = 45000
    elif mutation == "wrong_category":
        frame.loc[0, "category"] = "Other"
    else:
        frame["receipts"] = frame["receipts"].astype(object)
        frame.loc[0, "receipts"] = ""
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError):
        invoke(refresh_functions, data)


@pytest.mark.parametrize("field,value", [("closing_cash", 0), ("closing_receivables", 0), ("complete_bank_population", False), ("currency", "USD")])
def test_independent_controls_are_required(refresh_functions, data, field, value):
    path = data / "refresh-controls.json"
    controls = json.loads(path.read_text())
    controls[field] = value
    path.write_text(json.dumps(controls))
    with pytest.raises(ValueError):
        invoke(refresh_functions, data)


def test_missing_timing_or_past_due_receipt_stops(refresh_functions, data):
    path = data / "receipt-assumptions.csv"
    frame = pd.read_csv(path)
    frame.loc[0, "expected_date"] = "2026-10-14"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="future expected date"):
        invoke(refresh_functions, data)


def invoice_rows():
    positive = {"id": "I1", "original": "10000", "settled": "4000", "outstanding": "6000",
                "due_date": "2026-09-20", "expected_date": "2026-11-15", "disputed": "1000",
                "apply_to": "", "evidence": "Fabricated invoice I1 and receipt R1"}
    credit = {**positive, "id": "CN1", "original": "-500", "settled": "0", "outstanding": "-500",
              "disputed": "0", "apply_to": "I1", "evidence": "Fabricated credit note"}
    return [positive, credit]


def test_partial_invoice_and_credit_note_reconcile_without_duplicate_cash():
    function = runpy.run_path(str(GENERATED / "invoice_cash.py"))["invoice_cash"]
    result = function(invoice_rows(), control_balance="5500", cutoff="2026-09-30")
    assert result["ledger_outstanding"] == {"I1": "6000", "CN1": "-500"}
    assert len(result["cash"]) == 1
    assert result["cash"][0]["amount"] == "5500"
    assert result["cash"][0]["disputed"] == "1000"


@pytest.mark.parametrize("mutation", ["overcredit", "duplicate", "wrong_balance", "infinite"])
def test_invoice_book_rejects_unsupported_allocations(mutation):
    function = runpy.run_path(str(GENERATED / "invoice_cash.py"))["invoice_cash"]
    rows = invoice_rows()
    control = "5500"
    if mutation == "overcredit":
        rows[1]["original"] = rows[1]["outstanding"] = "-7000"
        control = "-1000"
    elif mutation == "duplicate":
        rows[1]["id"] = "I1"
    elif mutation == "wrong_balance":
        control = "0"
    else:
        rows[0]["outstanding"] = "Infinity"
    with pytest.raises(ValueError):
        function(rows, control_balance=control, cutoff="2026-09-30")


def test_price_volume_bridge_retains_unexplained_ledger_residual():
    function = runpy.run_path(str(GENERATED / "operating_variance.py"))["revenue_bridge"]
    result = function([{"service": "Maintenance", "prior_units": "200", "current_units": "220",
                        "prior_price": "100", "current_price": "110", "evidence": "Fabricated job register"}],
                      "20000", "24150")
    assert result["volume"] == "2000"
    assert result["price"] == "2200"
    assert result["residual"] == "-50"
    assert sum(Decimal(result[key]) for key in ("price", "volume", "residual")) == Decimal(result["observed"])


@pytest.mark.parametrize("amount", ["1e100", "1.001", "100000000000000000000000000000000000000000000000000000000000001", 1.0])
def test_invoice_amount_precision_is_bounded(amount):
    function = runpy.run_path(str(GENERATED / "invoice_cash.py"))["invoice_cash"]
    rows = invoice_rows()
    rows[0]["original"] = amount
    with pytest.raises(ValueError):
        function(rows, control_balance="5500", cutoff="2026-09-30")


def nfp_case():
    path = ROOT / "examples/restricted-cash"
    return runpy.run_path(str(path / "restricted_cash.py"))["forecast"], json.loads((path / "example.json").read_text())


def test_nfp_available_cash_is_separate_from_total_bank():
    function, case = nfp_case()
    result = function(case)
    assert result["closing_cash"] == "83000"
    assert result["restricted_allocation"] == "70000"
    assert result["available_under_assumptions"] == "13000"


@pytest.mark.parametrize("mutation", ["no_evidence", "overallocated", "overspent", "duplicate", "missing"])
def test_nfp_rejects_unsupported_restrictions(mutation):
    function, case = nfp_case()
    if mutation == "no_evidence":
        case["funds"][0]["restriction_evidence"] = ""
    elif mutation == "overallocated":
        case["funds"][0]["opening_restricted"] = "100000"
    elif mutation == "overspent":
        case["funds"][0]["spend"] = "60000"
    elif mutation == "duplicate":
        case["funds"].append(copy.deepcopy(case["funds"][0]))
    else:
        case["funds"][0].pop("receipts")
    with pytest.raises(ValueError):
        function(case)


def test_advance_receipt_cannot_reduce_closed_receivables(refresh_functions, data):
    path = data / "refresh-actuals.csv"
    actuals = pd.read_csv(path)
    invoices = pd.read_csv(data / "invoices.csv")
    future = invoices[invoices["service_month"] == "2026-11"].iloc[0]
    actuals.loc[0, "source_id"] = future["id"]
    actuals.to_csv(path, index=False)
    with pytest.raises(ValueError, match="customer-deposit"):
        invoke(refresh_functions, data)
