"""Supplier planning preserves ledger facts and rejects unsupported allocations."""
import copy
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "examples/creditor-cash"
BUILD = runpy.run_path(str(ROOT / "supplier_cash.py"))["supplier_cash"]


def test_supplier_credit_and_partial_settlement_are_paid_once():
    result = BUILD(json.loads((ROOT / "example.json").read_text()))
    assert result["ledger_outstanding"] == {"P1": "4000", "C1": "-500"}
    assert result["payment_total"] == "3500"
    assert [row["amount"] for row in result["payments"]] == ["1000", "2500"]


@pytest.mark.parametrize("mutation", ["duplicate", "too_much", "too_little", "past", "unapproved", "cross_supplier", "missing_evidence", "control", "unallocated_credit"])
def test_bad_supplier_plans_fail(mutation):
    case = copy.deepcopy(json.loads((ROOT / "example.json").read_text()))
    if mutation == "duplicate":
        case["payment_plan"][1]["id"] = "PAY1"
    elif mutation == "too_much":
        case["payment_plan"][1]["amount"] = "2501"
    elif mutation == "too_little":
        case["payment_plan"].pop()
    elif mutation == "past":
        case["payment_plan"][0]["date"] = case["cutoff"]
    elif mutation == "unapproved":
        case["payment_plan"][0]["approved"] = False
    elif mutation == "cross_supplier":
        case["invoices"][1]["supplier_id"] = "OTHER"
    elif mutation == "missing_evidence":
        case["payment_plan"][0]["evidence"] = ""
    elif mutation == "control":
        case["control_balance"] = "4000"
    else:
        case["invoices"][1]["apply_to"] = ""
    with pytest.raises(ValueError):
        BUILD(case)
