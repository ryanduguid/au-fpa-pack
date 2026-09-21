"""Create close-control inputs from the same fabricated forecast opening balances."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from decimal import Decimal
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
HEADER = ["ReportDate", "Tenant", "Section", "AccountID", "AccountName", "AccountCode",
          "Debit", "Credit", "YTDDebit", "YTDCredit"]
# An explicit fabricated prior snapshot, constructed for this worked route.
# It is not an observed August export or an estimate of historical performance.
PRIOR = {"090": "62414.15", "620": "0", "710": "12200", "800": "0",
         "820": "-8400", "826": "-1000", "860": "-20000", "900": "-45214.15"}


def handoff(output: Path, data: Path = DATA) -> dict:
    sources = {name: (data / name).read_bytes() for name in ("xero_bs.csv", "invoices.csv", "payments.csv")}
    balances = list(csv.DictReader(io.StringIO(sources["xero_bs.csv"].decode())))
    if {row["Code"] for row in balances} != set(PRIOR) or len(balances) != len(PRIOR):
        raise ValueError("The handoff requires the exact reviewed Lumbridge balance-sheet mapping")
    current = {row["Code"]: Decimal(row["Amount"]) for row in balances}
    prior = {key: Decimal(value) for key, value in PRIOR.items()}
    if any(not value.is_finite() for value in current.values()) or sum(current.values()) != 0 or sum(prior.values()) != 0:
        raise ValueError("Both balance sheets must contain finite, balanced amounts")
    invoices = list(csv.DictReader(io.StringIO(sources["invoices.csv"].decode())))
    opening = [row for row in invoices if row["id"].startswith("OPEN-")]
    if {row["id"] for row in opening} != {"OPEN-V", "OPEN-F"} or len(opening) != 2:
        raise ValueError("Expected the two reviewed opening invoices")
    receivable = sum(Decimal(row["net"]) + Decimal(row["gst"]) for row in opening)
    payments = list(csv.DictReader(io.StringIO(sources["payments.csv"].decode())))
    settlement = [row for row in payments if row["date"] == "2026-10-07" and row["category"] == "Materials"]
    if receivable != current["620"] or len(settlement) != 1 or Decimal(settlement[0]["amount"]) != -current["800"]:
        raise ValueError("Opening receivables or the assumed payable settlement does not tie")
    output.mkdir(parents=True, exist_ok=False)
    for label, when, values in (("prior", "2026-08-31", prior), ("current", "2026-09-30", current)):
        with (output / f"{label}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(HEADER)
            for row in balances:
                code, value = row["Code"], values[row["Code"]]
                movement = value - prior[code] if label == "current" else Decimal(0)
                section = "Assets" if code in {"090", "620", "710"} else "Equity" if code == "900" else "Liabilities"
                writer.writerow([when, "Lumbridge Services", section, "BS-" + code, row["Account"], code,
                                 max(movement, 0), max(-movement, 0), max(value, 0), max(-value, 0)])
    (output / "mapping.csv").write_text("AccountID,ReviewGroup\n" + "".join(
        f"BS-{row['Code']},{row['Account']}\n" for row in balances), encoding="utf-8")
    (output / "subledger.csv").write_text(
        "Tenant,AccountID,SubledgerBalance\n"
        f"Lumbridge Services,BS-620,{receivable}\n"
        f"Lumbridge Services,BS-800,{current['800']}\n", encoding="utf-8")
    record = {"entity": "Lumbridge Services", "currency": "AUD", "as_at": "2026-09-30",
              "opening_cash": str(current["090"]), "opening_receivables": str(receivable),
              "opening_payables": str(current["800"]),
              "source_sha256": {name: hashlib.sha256(value).hexdigest() for name, value in sources.items()},
              "scope": "Fabricated closed balance-sheet handoff. Prior values are constructed assumptions. "
                       "The payable schedule is an asserted opening balance supported by a planned settlement, "
                       "not an independent supplier ledger. Account IDs use BS- to avoid the P&L code collision."}
    (output / "handoff.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(handoff(args.output), indent=2))
