"""Quarter controls are independent of source arithmetic and snapshots are immutable."""
import copy
import csv
import hashlib
import json
import runpy
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "examples/quarter-close"
MODULE = runpy.run_path(str(ROOT / "quarter.py"))


def test_three_closes_keep_balances_identity_age_and_old_forecasts(tmp_path):
    result = MODULE["run"](ROOT / "case.json", tmp_path / "run")
    assert [row["balances"]["cash"] for row in result["periods"]] == ["20000", "22000", "24500", "29500"]
    assert [row["error"] for row in result["forecast_errors"]] == ["-2000.0", "-1000.0", "2000.0"]
    last = result["periods"][-1]
    assert last["customer_book"]["cash"] == []
    assert last["supplier_book"]["payment_total"] == "2000"
    assert last["overdue"] == [{"id": "P3", "amount": "2000", "document_date": "2026-11-08", "due_date": "2026-11-30", "days_since_issue": 53, "days_overdue": 31}]
    assert last["forecast"] == {"2027-01-15": "27500"}
    for period, digest in result["snapshot_sha256"].items():
        assert hashlib.sha256((tmp_path / "run" / period / "forecast.yaml").read_bytes()).hexdigest() == digest
    for row in result["periods"]:
        b = row["balances"]
        assert Decimal(b["cash"]) + Decimal(b["AR"]) == Decimal(b["AP"]) + Decimal(b["equity"])
    with pytest.raises(FileExistsError):
        MODULE["run"](ROOT / "case.json", tmp_path / "run")


@pytest.mark.parametrize("mutation", ["duplicate_settlement", "overpay", "cross_credit", "control", "missing_plan", "old_plan", "extra_plan", "missing_document"])
def test_bad_quarter_evidence_is_refused(mutation):
    case = copy.deepcopy(json.loads((ROOT / "case.json").read_text()))
    if mutation == "duplicate_settlement":
        case["settlements"].append(case["settlements"][0])
    elif mutation == "overpay":
        case["settlements"][0]["amount"] = "10001"
    elif mutation == "cross_credit":
        case["documents"][4]["apply_to"] = "P1"
    elif mutation == "control":
        case["controls"]["2026-10-31"]["cash"] = "22001"
    elif mutation == "missing_plan":
        case["plans"]["2026-10-31"].pop("S1")
    elif mutation == "old_plan":
        case["plans"]["2026-10-31"]["S1"] = "2026-10-30"
    elif mutation == "extra_plan":
        case["plans"]["2026-12-31"]["S1"] = "2027-01-01"
    else:
        case["documents"].pop()
    with pytest.raises(ValueError):
        MODULE["calculate"](case)


def test_receipt_beyond_the_scored_month_is_not_pulled_forward():
    case = json.loads((ROOT / "case.json").read_text())
    case["plans"]["2026-09-30"]["S1"] = "2026-11-15"
    first = MODULE["calculate"](case)[0]
    assert first["forecast_horizon"] == "2026-10-31"
    assert first["predicted_month_end_cash"] == "14000"


def test_another_year_and_entity_preserve_the_cash_calculation(tmp_path):
    case = json.loads((ROOT / "case.json").read_text().replace("2026-", "2028-").replace("2027-", "2029-"))
    case["entity"] = "Fabricated Services, North"
    source = tmp_path / "case.json"
    source.write_text(json.dumps(case))
    output = tmp_path / "quarter"
    result = MODULE["run"](source, output)
    assert result["entity"] == case["entity"]
    assert result["periods"][-1]["cutoff"] == "2028-12-31"
    assert result["periods"][-1]["balances"]["cash"] == "29500"
    with (output / "2028-12-31/subledger.csv").open(newline="") as stream:
        assert all(row["Tenant"] == case["entity"] for row in csv.DictReader(stream))


@pytest.mark.parametrize("change", ["non_month_end", "gap", "blank_entity", "formula_entity"])
def test_invalid_period_configuration_fails(change):
    case = json.loads((ROOT / "case.json").read_text())
    if change == "blank_entity":
        case["entity"] = " "
    elif change == "formula_entity":
        case["entity"] = "=1+1"
    else:
        target = "2026-10-30" if change == "non_month_end" else "2027-01-31"
        for key in ("controls", "plans"):
            case[key][target] = case[key].pop("2026-10-31")
    with pytest.raises(ValueError):
        MODULE["calculate"](case)
