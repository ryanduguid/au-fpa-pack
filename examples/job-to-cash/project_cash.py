"""Consume the WIP example's files in the existing weekly cash kernel."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from pyfpa.cash13.forecast import cash13_forecast
from pyfpa.cash13.schemas import Cash13Config, WeeklyFlow


def project(pack: Path) -> dict:
    evidence = json.loads((pack / "job-to-cash.json").read_text(encoding="utf-8"))
    content = (pack / "cash-assumptions.csv").read_bytes()
    if evidence["currency"] != "AUD" or hashlib.sha256(content).hexdigest() != evidence["cash_assumptions_sha256"]:
        raise ValueError("Currency or cash assumption evidence does not match")
    rows = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    if set(rows) != {"id", "date", "receipt", "payment", "evidence"} or rows["id"].duplicated().any():
        raise ValueError("Expected unique dated cash assumption IDs")
    start = date.fromisoformat(evidence["as_at"]) + timedelta(days=1)
    receipts, payments, outside = [], [], []
    for row in rows.itertuples():
        when = date.fromisoformat(row.date)
        dr, cr = float(row.receipt), float(row.payment)
        if not all(math.isfinite(value) and value >= 0 for value in (dr, cr)) or (dr > 0 and cr > 0) or not row.evidence:
            raise ValueError("Cash assumptions require finite one-sided amounts and evidence")
        week = (when - start).days // 7 + 1
        if week < 1:
            raise ValueError("Cash assumptions precede the projection")
        if week > 13:
            outside.append({"id": row.id, "date": row.date, "receipt": dr, "payment": cr})
            continue
        if dr:
            receipts.append(WeeklyFlow(name=row.id, amount=dr, start_week=week))
        if cr:
            payments.append(WeeklyFlow(name=row.id, amount=cr, start_week=week))
    opening = float(evidence["cash_to_date"])
    if not math.isfinite(opening):
        raise ValueError("Cumulative project cash must be finite")
    frame = cash13_forecast(Cash13Config(opening_cash=opening, receipts=receipts, disbursements=payments))
    return {"contract_id": evidence["contract_id"], "start": start.isoformat(), "currency": "AUD",
            "weeks": frame.reset_index().to_dict("records"), "outside_horizon": outside,
            "source_sha256": evidence["cash_assumptions_sha256"],
            "scope": "Cumulative project receipts less payments, not an entity bank balance. Excludes unbilled and uncertified future receipts."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(project(args.pack), indent=2))
