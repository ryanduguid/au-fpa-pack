"""One fabricated NFP cash forecast under explicitly supplied restrictions."""
from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path


def forecast(data: dict) -> dict:
    if set(data) != {"currency", "opening_cash", "general_receipts", "general_spend", "funds"} or data["currency"] != "AUD":
        raise ValueError("Expected one explicit AUD planning case")
    with localcontext() as context:
        context.prec = 60
        def money(value):
            if not isinstance(value, str):
                raise ValueError("Cash inputs must be decimal strings")
            amount = Decimal(value)
            if not amount.is_finite() or amount < 0:
                raise ValueError("Cash inputs must be finite and non-negative")
            return amount
        opening = money(data["opening_cash"])
        receipts, spend = money(data["general_receipts"]), money(data["general_spend"])
        funds, seen = [], set()
        for row in data["funds"]:
            if set(row) != {"id", "opening_restricted", "receipts", "spend", "renewal_date", "restriction_evidence", "allocation_evidence"} or not row["id"] or row["id"] in seen:
                raise ValueError("Unique funds and complete fields are required")
            seen.add(row["id"])
            if not row["restriction_evidence"] or not row["allocation_evidence"]:
                raise ValueError("Restrictions and allocation decisions need supplied evidence")
            date.fromisoformat(row["renewal_date"])
            start, received, paid = (money(row[key]) for key in ("opening_restricted", "receipts", "spend"))
            closing = start + received - paid
            if closing < 0:
                raise ValueError("Fund spend exceeds the supplied restricted cash allocation")
            receipts += received
            spend += paid
            funds.append({**row, "closing_restricted": str(closing)})
        opening_restricted = sum((money(row["opening_restricted"]) for row in funds), Decimal(0))
        if opening_restricted > opening:
            raise ValueError("Opening restricted allocations exceed total opening cash")
        closing = opening + receipts - spend
        restricted = sum((money(row["closing_restricted"]) for row in funds), Decimal(0))
        return {"currency": "AUD", "opening_cash": str(opening), "receipts": str(receipts),
                "spend": str(spend), "closing_cash": str(closing), "restricted_allocation": str(restricted),
                "available_under_assumptions": str(closing - restricted), "funds": funds,
                "status": "SHORTFALL" if closing < restricted else "RECONCILED",
                "scope": "Cash planning under supplied restrictions. No revenue recognition or acquittal conclusion."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).with_name("example.json"))
    args = parser.parse_args()
    print(json.dumps(forecast(json.loads(args.input.read_text(encoding="utf-8"))), indent=2))
