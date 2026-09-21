"""Reconcile a supplied invoice book before using its dated cash assumptions."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, localcontext


def invoice_cash(invoices: list[dict], *, control_balance: str, cutoff: str) -> dict:
    """Gross balances are ledger facts; expected dates and credit allocations are inputs."""
    with localcontext() as context:
        context.prec = 60
        close = date.fromisoformat(cutoff)
        rows = {}
        for record in invoices:
            expected = {"id", "original", "settled", "outstanding", "due_date", "expected_date", "disputed", "apply_to", "evidence"}
            if set(record) != expected or not isinstance(record["id"], str) or not record["id"] or record["id"] in rows:
                raise ValueError("Invoice fields and unique IDs are required")
            row = dict(record)
            for key in ("original", "settled", "outstanding", "disputed"):
                if not isinstance(row[key], str) or not re.fullmatch(r"-?\d{1,15}(?:\.\d{1,2})?", row[key]):
                    raise ValueError("Amounts require decimal strings with at most 15 integer digits and 2 places")
                row[key] = Decimal(row[key])
                if not row[key].is_finite():
                    raise ValueError("Amounts must be finite")
            if row["original"] - row["settled"] != row["outstanding"]:
                raise ValueError("Original less settled does not equal outstanding")
            if not 0 <= row["disputed"] <= abs(row["outstanding"]) or not row["evidence"]:
                raise ValueError("Disputed balance and evidence are required")
            if (row["original"] >= 0 and not 0 <= row["settled"] <= row["original"]) or (row["original"] < 0 and not row["original"] <= row["settled"] <= 0):
                raise ValueError("Settled amount must have the source sign and stay within the original")
            date.fromisoformat(row["due_date"])
            if date.fromisoformat(row["expected_date"]) <= close and row["outstanding"]:
                raise ValueError("Outstanding cash needs an expected date after cutoff")
            rows[row["id"]] = row
        if not isinstance(control_balance, str) or not re.fullmatch(r"-?\d{1,15}(?:\.\d{1,2})?", control_balance):
            raise ValueError("Control balance requires a bounded decimal string with at most 2 places")
        control = Decimal(control_balance)
        if not control.is_finite() or sum((r["outstanding"] for r in rows.values()), Decimal(0)) != control:
            raise ValueError("Outstanding invoice book does not equal the ledger control")
        cash = {key: row["outstanding"] for key, row in rows.items()}
        for key, row in rows.items():
            target = row["apply_to"]
            if target:
                if row["original"] >= 0 or target not in rows or rows[target]["original"] <= 0:
                    raise ValueError("Credit allocations require a known positive invoice")
                cash[target] += row["outstanding"]
                cash[key] = Decimal(0)
                if cash[target] < 0:
                    raise ValueError("Credit allocations exceed the target invoice")
        return {"control_balance": str(control), "ledger_outstanding": {key: str(row["outstanding"]) for key, row in rows.items()},
                "cash": [{"invoice_id": key, "expected_date": rows[key]["expected_date"], "amount": str(value),
                          "disputed": str(rows[key]["disputed"]), "evidence": rows[key]["evidence"]}
                         for key, value in cash.items() if value],
                "policy": "Opening book cash only. Do not add these invoices again through projected sales."}
