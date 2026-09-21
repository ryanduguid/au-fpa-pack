"""Canonical supplier balances and explicitly approved future payments."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import runpy
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

INVOICE_CASH = runpy.run_path(str(Path(__file__).parents[1] /
    "lumbridge-services/models/generated/invoice_cash.py"))["invoice_cash"]


def supplier_cash(document: dict) -> dict:
    fields = {"schema_version", "entity", "currency", "cutoff", "control_balance", "invoices", "payment_plan"}
    if set(document) != fields or document["schema_version"] != "supplier-cash.v1":
        raise ValueError("Expected supplier-cash.v1 fields")
    if not isinstance(document["entity"], str) or not document["entity"].strip() or document["currency"] != "AUD":
        raise ValueError("A named entity and AUD are required")
    cutoff = date.fromisoformat(document["cutoff"])
    if cutoff.isoformat() != document["cutoff"]:
        raise ValueError("Cutoff must use YYYY-MM-DD")
    rows = document["invoices"]
    if not isinstance(rows, list):
        raise ValueError("invoices must be a list")
    if not rows:
        if Decimal(document["control_balance"]) != 0 or document["payment_plan"]:
            raise ValueError("Empty supplier population requires zero control and no plan")
        return {"schema_version": "supplier-cash-result.v1", "entity": document["entity"],
                "currency": "AUD", "cutoff": document["cutoff"], "control_balance": "0",
                "ledger_outstanding": "0", "payments": [], "payment_total": "0",
                "invoice_evidence": [], "scope": "No supplier population."}
    suppliers, invoices = {}, []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("supplier_id"), str) or not row["supplier_id"].strip():
            raise ValueError("Every invoice needs an explicit supplier ID")
        suppliers[row["id"]] = row["supplier_id"]
        invoices.append({key: value for key, value in row.items() if key != "supplier_id"})
    for row in rows:
        if row["apply_to"] and suppliers.get(row["apply_to"]) != row["supplier_id"]:
            raise ValueError("Credits cannot be applied across suppliers")
    book = INVOICE_CASH(invoices, control_balance=document["control_balance"], cutoff=document["cutoff"])
    with localcontext() as context:
        context.prec = 60
        outstanding = {row["invoice_id"]: Decimal(row["amount"]) for row in book["cash"]}
        if any(value < 0 for value in outstanding.values()):
            raise ValueError("Unallocated supplier credits need a separate refund or allocation decision")
        allocated = dict.fromkeys(outstanding, Decimal(0))
        payments, seen = [], set()
        if not isinstance(document["payment_plan"], list):
            raise ValueError("payment_plan must be a list")
        for row in document["payment_plan"]:
            if not isinstance(row, dict) or set(row) != {"id", "invoice_id", "date", "amount", "approved", "evidence"}:
                raise ValueError("Unexpected payment-plan fields")
            if not isinstance(row["id"], str) or not row["id"].strip() or row["id"] in seen:
                raise ValueError("Payment IDs must be unique and non-empty")
            seen.add(row["id"])
            key = row["invoice_id"]
            if key not in outstanding or row["approved"] is not True or not isinstance(row["evidence"], str) or not row["evidence"].strip():
                raise ValueError("Each payment needs an outstanding invoice, approval and evidence")
            when = date.fromisoformat(row["date"])
            if when.isoformat() != row["date"] or when <= cutoff:
                raise ValueError("Payment dates must be canonical and after cutoff")
            if not isinstance(row["amount"], str) or not re.fullmatch(r"\d{1,15}(?:\.\d{1,2})?", row["amount"]):
                raise ValueError("Payment amounts require bounded decimal strings")
            amount = Decimal(row["amount"])
            if amount <= 0:
                raise ValueError("Payments must be positive")
            allocated[key] += amount
            payments.append({**row, "supplier_id": suppliers[key]})
        if allocated != outstanding:
            raise ValueError("Payment plans must cover each net outstanding invoice exactly once")
        return {"schema_version": "supplier-cash-result.v1", "entity": document["entity"], "currency": "AUD",
                "cutoff": document["cutoff"], "control_balance": book["control_balance"],
                "ledger_outstanding": book["ledger_outstanding"], "payments": payments,
                "payment_total": str(sum(allocated.values(), Decimal(0))),
                "invoice_evidence": rows,
                "scope": "Supplied opening payables and planning approvals only. No payment is executed. "
                         "Settled includes cash and applied credits; do not add this book again as new purchases."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).with_name("example.json"))
    args = parser.parse_args()
    try:
        content = args.input.read_bytes()
        result = supplier_cash(json.loads(content))
        result["source_sha256"] = hashlib.sha256(content).hexdigest()
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, f"Supplier cash: {exc}\n")
    print(json.dumps(result, indent=2))
