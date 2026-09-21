"""Turn reviewed grant cash assumptions into the existing restricted-cash forecast."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import runpy
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

FORECAST = runpy.run_path(str(Path(__file__).with_name("restricted_cash.py")))["forecast"]


def money(value):
    if not isinstance(value, str) or not re.fullmatch(r"-?\d{1,15}(?:\.\d{1,2})?", value):
        raise ValueError("Use bounded decimal strings with at most 2 places")
    return Decimal(value)


def dated_liquidity(plan: dict, allocations: dict, closing: dict) -> dict:
    """Measure end-of-day cash; same-day receipts and payments are netted."""
    events = []
    for fund in plan["funds"]:
        for receipt in fund["expected_receipts"]:
            events.append((receipt["date"], fund["id"], money(receipt["amount"])))
    for payment in plan["commitment_plans"]:
        events.append((payment["date"], allocations[payment["allocation_id"]]["grant_id"], -money(payment["amount"])))
    totals = {"receipt": Decimal(0), "payment": Decimal(0)}
    seen = set()
    for row in plan.get("general_cash_plan", []):
        if (set(row) != {"id", "date", "kind", "amount", "evidence"} or
                not isinstance(row["id"], str) or not row["id"].strip() or row["id"] in seen or
                row["kind"] not in totals or not isinstance(row["evidence"], str) or not row["evidence"].strip()):
            raise ValueError("General cash needs unique IDs, a receipt/payment kind and evidence")
        seen.add(row["id"])
        when, value = date.fromisoformat(row["date"]), money(row["amount"])
        if when.isoformat() != row["date"] or not plan["start"] <= row["date"] <= plan["end"] or value <= 0:
            raise ValueError("General cash must be positive and dated inside the forecast")
        totals[row["kind"]] += value
        events.append((row["date"], None, value if row["kind"] == "receipt" else -value))
    if totals != {"receipt": money(plan["general_receipts"]), "payment": money(plan["general_spend"])}:
        raise ValueError("General cash dates must cover the supplied receipts and spending exactly")
    bank = money(plan["opening_bank"])
    funds = {row["id"]: money(row["opening_restricted"]) for row in plan["funds"]}
    timeline = []

    def record(when, basis):
        available = bank - sum((max(value, Decimal(0)) for value in funds.values()), Decimal(0))
        timeline.append({"date": when, "basis": basis, "bank_cash": str(bank),
                         "available_cash": str(available),
                         "fund_balances": {key: str(value) for key, value in funds.items()},
                         "underfunded_grants": [key for key, value in funds.items() if value < 0]})

    record(plan["start"], "opening")
    for when in sorted({event[0] for event in events} | {plan["end"]}):
        for event_date, fund_id, value in events:
            if event_date == when:
                bank += value
                if fund_id is not None:
                    funds[fund_id] += value
        record(when, "end_of_day")
    if bank != money(closing["closing_cash"]) or sum(funds.values(), Decimal(0)) != money(closing["restricted_allocation"]):
        raise ValueError("Dated cash does not reconcile to the period-end forecast")
    shortfalls = [row for row in timeline if money(row["bank_cash"]) < 0 or money(row["available_cash"]) < 0 or row["underfunded_grants"]]
    return {"status": "SHORTFALL" if shortfalls else "NO_SHORTFALL",
            "first_shortfall_date": shortfalls[0]["date"] if shortfalls else None,
            "minimum_bank_cash": str(min(money(row["bank_cash"]) for row in timeline)),
            "minimum_available_cash": str(min(money(row["available_cash"]) for row in timeline)),
            "minimum_fund_balances": {key: str(min(money(row["fund_balances"][key]) for row in timeline)) for key in funds},
            "timeline": timeline, "scope": "Opening and end-of-day balances only; same-day flows are netted. Unplanned commitments remain excluded."}


def grant_cash(content: bytes, expected_sha256: str, plan: dict) -> dict:
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError("Grant workpaper digest does not match")
    workpaper = json.loads(content)
    fields = {"schema_version", "entity", "currency", "start", "end", "opening_bank", "general_receipts", "general_spend", "funds", "commitment_plans"}
    if set(plan) - {"general_cash_plan"} != fields or plan["schema_version"] != "grant-cash-plan.v1":
        raise ValueError("Unexpected grant cash plan")
    if workpaper["schema_version"] != 1 or workpaper["status"] not in {"REVIEW", "RECONCILED"}:
        raise ValueError("Unsupported grant workpaper")
    if plan["entity"] != workpaper["entity"] or plan["currency"] != workpaper["currency"] or plan["currency"] != "AUD":
        raise ValueError("Entity and currency must match the workpaper")
    start, end = date.fromisoformat(plan["start"]), date.fromisoformat(plan["end"])
    if (start.isoformat() != plan["start"] or end.isoformat() != plan["end"] or
            start.toordinal() != date.fromisoformat(workpaper["ledger_end"]).toordinal() + 1 or start > end):
        raise ValueError("Forecast must begin immediately after the workpaper period")
    with localcontext() as context:
        context.prec = 60
        movements = {row["grant_id"]: row for row in workpaper["funding_movements"]}
        if len(movements) != len(workpaper["funding_movements"]):
            raise ValueError("Duplicate source grant")
        allocations = {row["allocation_id"]: row for row in workpaper["allocation_evidence"]}
        if len(allocations) != len(workpaper["allocation_evidence"]):
            raise ValueError("Duplicate source allocation")
        if money(workpaper["ledger_total"]) != money(workpaper["allocated_total"]) + money(workpaper["unallocated_total"]):
            raise ValueError("Source ledger tie-out does not agree")
        outstanding, eligible = {}, {}
        for key, row in allocations.items():
            amount = money(row["amount"]) - money(row["cash_allocated"])
            if amount < 0:
                raise ValueError("Source cash exceeds allocated expenditure")
            outstanding[key] = amount
            if row["approved"] == "yes" and row["within_period"] == "yes" and row["evidence"].strip() and row["source_evidence"].strip():
                eligible[key] = amount
        paid = dict.fromkeys(allocations, Decimal(0))
        fund_spend = dict.fromkeys(movements, Decimal(0))
        seen = set()
        for row in plan["commitment_plans"]:
            if set(row) != {"id", "allocation_id", "date", "amount", "reviewed", "evidence"} or not row["id"] or row["id"] in seen:
                raise ValueError("Unique, complete commitment plan rows are required")
            seen.add(row["id"])
            key = row["allocation_id"]
            when = date.fromisoformat(row["date"])
            if key not in eligible or row["reviewed"] is not True or not row["evidence"].strip():
                raise ValueError("Plan only evidenced, approved, in-period allocations")
            if when.isoformat() != row["date"] or not start <= when <= end:
                raise ValueError("Commitment date is outside the forecast")
            value = money(row["amount"])
            if value <= 0:
                raise ValueError("Commitment cash must be positive")
            paid[key] += value
            fund_spend[allocations[key]["grant_id"]] += value
        if any(paid[key] != amount for key, amount in eligible.items()):
            raise ValueError("Plans must cover approved unpaid allocations exactly")
        funds, seen = [], set()
        for row in plan["funds"]:
            fields = {"id", "opening_restricted", "expected_receipts", "renewal_date", "restriction_evidence", "allocation_evidence", "reviewed"}
            if set(row) != fields or row["id"] in seen or row["id"] not in movements or row["reviewed"] is not True:
                raise ValueError("Each source grant needs one reviewed restriction decision")
            seen.add(row["id"])
            opening = money(row["opening_restricted"])
            if not 0 <= opening <= money(movements[row["id"]]["closing_cash_allocation"]):
                raise ValueError("Restricted opening exceeds the source cash allocation")
            receipts, receipt_ids = Decimal(0), set()
            for receipt in row["expected_receipts"]:
                if set(receipt) != {"id", "date", "amount", "evidence"} or not receipt["id"] or receipt["id"] in receipt_ids or not receipt["evidence"].strip():
                    raise ValueError("Expected funding needs unique IDs and evidence")
                receipt_ids.add(receipt["id"])
                when = date.fromisoformat(receipt["date"])
                value = money(receipt["amount"])
                if when.isoformat() != receipt["date"] or not start <= when <= end or value <= 0:
                    raise ValueError("Expected funding must be positive and inside the forecast")
                receipts += value
            funds.append({"id": row["id"], "opening_restricted": str(opening), "receipts": str(receipts),
                          "spend": str(fund_spend[row["id"]]), "renewal_date": row["renewal_date"],
                          "restriction_evidence": row["restriction_evidence"], "allocation_evidence": row["allocation_evidence"]})
        if seen != set(movements):
            raise ValueError("Restriction decisions must cover every grant")
        for key in ("opening_bank", "general_receipts", "general_spend"):
            if money(plan[key]) < 0:
                raise ValueError("Bank and general cash inputs must be non-negative")
        model_input = {"currency": "AUD", "opening_cash": plan["opening_bank"],
                       "general_receipts": plan["general_receipts"], "general_spend": plan["general_spend"], "funds": funds}
        unplanned = [{"allocation_id": key, "amount": str(amount - paid[key]),
                      "reason": "Source approval, period or evidence remains unresolved"}
                     for key, amount in outstanding.items() if amount != paid[key]]
        forecast = FORECAST(model_input)
        return {"schema_version": "grant-cash-handoff.v1", "entity": plan["entity"], "start": plan["start"], "end": plan["end"],
                "workpaper_sha256": expected_sha256, "workpaper_status": workpaper["status"],
                "source_findings": workpaper["findings"], "source_expenditure": workpaper["allocated_total"],
                "source_funding_movements": workpaper["funding_movements"],
                "known_unpaid_allocations": str(sum(outstanding.values(), Decimal(0))),
                "planned_commitment_cash": str(sum(paid.values(), Decimal(0))), "unplanned_commitments": unplanned,
                "planning_assumptions": plan, "forecast_input": model_input, "forecast": forecast,
                "liquidity": dated_liquidity(plan, allocations, forecast),
                "scope": "Cash scenario under supplied review decisions. Expected funding is not received funding. "
                         "Unresolved allocations remain outside planned cash and visible here. No eligibility or income conclusion."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workpaper", type=Path, required=True)
    parser.add_argument("--workpaper-sha256", required=True)
    parser.add_argument("--plan", type=Path, default=Path(__file__).with_name("grant-plan.json"))
    args = parser.parse_args()
    try:
        plan_bytes = args.plan.read_bytes()
        result = grant_cash(args.workpaper.read_bytes(), args.workpaper_sha256, json.loads(plan_bytes))
        result["plan_sha256"] = hashlib.sha256(plan_bytes).hexdigest()
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(1, f"Grant cash: {exc}\n")
    print(json.dumps(result, indent=2))
