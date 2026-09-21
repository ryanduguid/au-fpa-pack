"""A hash-bound grant handoff cannot clear source findings or spend twice."""
import copy
import hashlib
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
BUILD = runpy.run_path(str(ROOT / "examples/restricted-cash/grant_cash.py"))["grant_cash"]
SOURCE = ROOT / "tests/fixtures/grant-workpaper.json"
PLAN = ROOT / "examples/restricted-cash/grant-plan.json"


def test_cash_handoff_preserves_the_acquittal_boundary():
    content = SOURCE.read_bytes()
    result = BUILD(content, hashlib.sha256(content).hexdigest(), json.loads(PLAN.read_text()))
    assert result["source_expenditure"] == "6300"
    assert result["known_unpaid_allocations"] == "3200"
    assert result["planned_commitment_cash"] == "200"
    assert result["unplanned_commitments"][0]["amount"] == "3000"
    assert result["forecast"]["closing_cash"] == "34800"
    assert result["forecast"]["restricted_allocation"] == "26700"
    assert result["forecast"]["available_under_assumptions"] == "8100"
    assert result["source_findings"] == json.loads(content)["findings"]
    assert result["workpaper_status"] == "REVIEW"


@pytest.mark.parametrize("mutation", ["hash", "entity", "period", "duplicate", "overpay", "unapproved", "missing", "restriction", "funding_date", "source_total"])
def test_invalid_grant_handoffs_stop(mutation):
    content = SOURCE.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    plan = copy.deepcopy(json.loads(PLAN.read_text()))
    if mutation == "hash":
        content += b" "
    elif mutation == "entity":
        plan["entity"] = "Different"
    elif mutation == "period":
        plan["start"] = "2027-07-02"
    elif mutation == "duplicate":
        plan["commitment_plans"].append(plan["commitment_plans"][0])
    elif mutation == "overpay":
        plan["commitment_plans"][0]["amount"] = "121"
    elif mutation == "unapproved":
        plan["commitment_plans"][0]["allocation_id"] = "A4"
    elif mutation == "missing":
        plan["funds"].pop()
    elif mutation == "restriction":
        plan["funds"][0]["opening_restricted"] = "15000"
    elif mutation == "funding_date":
        plan["funds"][0]["expected_receipts"][0]["date"] = "2028-01-01"
    else:
        workpaper = json.loads(content)
        workpaper["ledger_total"] = "6501"
        content = json.dumps(workpaper).encode()
        digest = hashlib.sha256(content).hexdigest()
    with pytest.raises(ValueError):
        BUILD(content, digest, plan)


def test_temporary_shortfall_survives_a_positive_closing_balance():
    content = SOURCE.read_bytes()
    plan = json.loads(PLAN.read_text())
    plan["opening_bank"] = "80"
    plan["funds"][0]["opening_restricted"] = "0"
    plan["funds"][1]["opening_restricted"] = "80"
    plan["funds"][0]["expected_receipts"][0]["date"] = "2027-09-30"
    result = BUILD(content, hashlib.sha256(content).hexdigest(), plan)
    assert result["forecast"]["closing_cash"] == "4880"
    assert result["forecast"]["status"] == "RECONCILED"
    assert result["liquidity"]["status"] == "SHORTFALL"
    assert result["liquidity"]["minimum_bank_cash"] == "-120"
    assert result["liquidity"]["first_shortfall_date"] == "2027-07-05"
    assert result["liquidity"]["minimum_fund_balances"]["G-A"] == "-120"
    assert result["source_findings"] == json.loads(content)["findings"]


def test_grant_shortfall_is_visible_even_when_bank_cash_is_positive():
    content = SOURCE.read_bytes()
    plan = json.loads(PLAN.read_text())
    plan["funds"][0]["opening_restricted"] = "0"
    result = BUILD(content, hashlib.sha256(content).hexdigest(), plan)
    assert result["liquidity"]["status"] == "SHORTFALL"
    assert result["liquidity"]["minimum_bank_cash"] == "29800"


def test_general_cash_requires_complete_dated_evidence():
    content = SOURCE.read_bytes()
    plan = json.loads(PLAN.read_text())
    plan["general_spend"] = "100"
    with pytest.raises(ValueError, match="dates must cover"):
        BUILD(content, hashlib.sha256(content).hexdigest(), plan)
    plan["general_cash_plan"] = [{"id": "GENERAL-1", "date": "2027-07-02", "kind": "payment", "amount": "100", "evidence": "Fabricated timing decision"}]
    result = BUILD(content, hashlib.sha256(content).hexdigest(), plan)
    assert result["forecast"]["closing_cash"] == "34700"
    assert result["liquidity"]["timeline"][-1]["bank_cash"] == "34700"
    plan["general_cash_plan"].append(plan["general_cash_plan"][0])
    with pytest.raises(ValueError, match="unique IDs"):
        BUILD(content, hashlib.sha256(content).hexdigest(), plan)


def test_same_day_receipts_are_netted_without_an_intraday_claim():
    content = SOURCE.read_bytes()
    plan = json.loads(PLAN.read_text())
    plan["opening_bank"] = "80"
    plan["funds"][0]["opening_restricted"] = "0"
    plan["funds"][1]["opening_restricted"] = "80"
    plan["funds"][0]["expected_receipts"][0]["date"] = "2027-07-05"
    result = BUILD(content, hashlib.sha256(content).hexdigest(), plan)
    assert result["liquidity"]["status"] == "NO_SHORTFALL"
    assert result["liquidity"]["minimum_bank_cash"] == "80"
