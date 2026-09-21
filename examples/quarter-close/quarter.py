"""A fabricated quarter: stable documents, successive balances and forecast snapshots."""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
import runpy
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

from pyfpa.backtest.score import score_forecast
from pyfpa.backtest.snapshot import Snapshot, load_snapshot, save_snapshot

EXAMPLES = Path(__file__).resolve().parents[1]
INVOICE_CASH = runpy.run_path(str(EXAMPLES / "lumbridge-services/models/generated/invoice_cash.py"))["invoice_cash"]
SUPPLIER_CASH = runpy.run_path(str(EXAMPLES / "creditor-cash/supplier_cash.py"))["supplier_cash"]
HEADER = "ReportDate,Tenant,Section,AccountID,AccountName,AccountCode,Debit,Credit,YTDDebit,YTDCredit".split(",")


def amount(value):
    import re
    if not isinstance(value, str) or not re.fullmatch(r"-?\d{1,12}(?:\.\d{1,2})?", value):
        raise ValueError("Quarter amounts must be bounded decimal strings")
    return Decimal(value)


def calculate(document: dict) -> list[dict]:
    if set(document) != {"schema_version", "entity", "currency", "opening_cash", "opening_equity", "documents", "settlements", "plans", "controls"} or document["schema_version"] != "quarter-case.v1":
        raise ValueError("Unexpected quarter case")
    if not isinstance(document["entity"], str) or not document["entity"].strip() or document["currency"] != "AUD":
        raise ValueError("A named entity and AUD are required")
    if document["entity"].lstrip().startswith(("=", "+", "-", "@")) or any(char in document["entity"] for char in "\r\n\t"):
        raise ValueError("Entity must be plain single-line text, without a spreadsheet formula prefix")
    cutoffs = sorted(document["controls"])
    if len(cutoffs) != 4 or set(document["plans"]) != set(cutoffs):
        raise ValueError("Opening and three month-end plans and controls are required")
    dates = [date.fromisoformat(value) for value in cutoffs]
    for index, when in enumerate(dates):
        if when.isoformat() != cutoffs[index] or when.day != calendar.monthrange(when.year, when.month)[1]:
            raise ValueError("Controls must use canonical month-end dates")
        if index and when.year * 12 + when.month != dates[index - 1].year * 12 + dates[index - 1].month + 1:
            raise ValueError("Quarter month ends must be consecutive")
    for plan in document["plans"].values():
        for value in plan.values():
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError("Plans must use canonical YYYY-MM-DD dates")
    documents, events = {}, set()
    for row in document["documents"]:
        fields = {"id", "book", "counterparty", "date", "due_date", "amount", "apply_to", "evidence"}
        if set(row) != fields or not row["id"] or row["id"] in documents or row["book"] not in {"AR", "AP"} or not row["evidence"]:
            raise ValueError("Documents require unique IDs, a book and evidence")
        for field in ("date", "due_date"):
            if date.fromisoformat(row[field]).isoformat() != row[field]:
                raise ValueError("Use canonical dates")
        if row["date"] > cutoffs[-1] or amount(row["amount"]) == 0 or not row["counterparty"]:
            raise ValueError("Document is outside the supported quarter")
        documents[row["id"]] = row
    for row in documents.values():
        if row["apply_to"]:
            target = documents.get(row["apply_to"])
            if not target or amount(row["amount"]) >= 0 or amount(target["amount"]) <= 0 or target["book"] != row["book"] or target["counterparty"] != row["counterparty"] or target["date"] > row["date"]:
                raise ValueError("A credit must link to its earlier invoice and counterparty")
        elif amount(row["amount"]) < 0:
            raise ValueError("Credits require explicit allocation")
    for row in document["settlements"]:
        if set(row) != {"id", "document_id", "date", "amount", "evidence"} or not row["id"] or row["id"] in events or not row["evidence"]:
            raise ValueError("Settlements require unique IDs and evidence")
        events.add(row["id"])
        target = documents.get(row["document_id"])
        if not target or amount(target["amount"]) <= 0 or not cutoffs[0] < row["date"] <= cutoffs[-1] or row["date"] < target["date"] or amount(row["amount"]) <= 0:
            raise ValueError("Settlement must name an issued invoice within the quarter")
        if date.fromisoformat(row["date"]).isoformat() != row["date"]:
            raise ValueError("Use canonical settlement dates")
    with localcontext() as context:
        context.prec = 60
        result = []
        for cutoff in cutoffs:
            known = {key: row for key, row in documents.items() if row["date"] <= cutoff}
            paid = {key: sum((amount(item["amount"]) for item in document["settlements"]
                             if item["document_id"] == key and item["date"] <= cutoff), Decimal(0)) for key in known}
            credits = {key: -sum((amount(row["amount"]) for row in known.values() if row["apply_to"] == key), Decimal(0)) for key in known}
            books = {"AR": [], "AP": []}
            overdue, net = [], {}
            for key, row in known.items():
                original = amount(row["amount"])
                settled = paid[key] + credits[key] if original > 0 else original
                remaining = original - settled
                if original > 0 and remaining < 0:
                    raise ValueError("Settlements and credits exceed their invoice")
                net[key] = remaining
                expected = document["plans"][cutoff].get(key, row["due_date"])
                if remaining and key not in document["plans"][cutoff]:
                    raise ValueError("Every outstanding invoice needs an explicit dated plan")
                invoice = {"id": key, "original": str(original), "settled": str(settled), "outstanding": str(remaining),
                           "due_date": row["due_date"], "expected_date": expected, "disputed": "0",
                           "apply_to": row["apply_to"], "evidence": row["evidence"]}
                if row["book"] == "AP":
                    invoice["supplier_id"] = row["counterparty"]
                books[row["book"]].append(invoice)
                if remaining and row["due_date"] < cutoff:
                    overdue.append({"id": key, "amount": str(remaining), "document_date": row["date"], "due_date": row["due_date"],
                                    "days_since_issue": (date.fromisoformat(cutoff) - date.fromisoformat(row["date"])).days,
                                    "days_overdue": (date.fromisoformat(cutoff) - date.fromisoformat(row["due_date"])).days})
            if set(document["plans"][cutoff]) != {key for key, value in net.items() if value}:
                raise ValueError("Plans must name exactly the outstanding population")
            ar = sum((net[key] for key in known if known[key]["book"] == "AR"), Decimal(0))
            ap = sum((net[key] for key in known if known[key]["book"] == "AP"), Decimal(0))
            receipts = sum((paid[key] for key in known if known[key]["book"] == "AR"), Decimal(0))
            payments = sum((paid[key] for key in known if known[key]["book"] == "AP"), Decimal(0))
            cash = amount(document["opening_cash"]) + receipts - payments
            profit = sum((amount(row["amount"]) * (1 if row["book"] == "AR" else -1)
                          for row in known.values() if row["date"] > cutoffs[0]), Decimal(0))
            equity = amount(document["opening_equity"]) + profit
            if cash + ar - ap - equity:
                raise ValueError("Trial balance does not balance")
            control = document["controls"][cutoff]
            if set(control) != {"cash", "AR", "AP", "evidence"} or not control["evidence"] or any(
                    amount(control[key]) != value for key, value in (("cash", cash), ("AR", ar), ("AP", ap))):
                raise ValueError("Quarter balances do not match independently supplied controls")
            ar_cash = INVOICE_CASH(books["AR"], control_balance=str(ar), cutoff=cutoff)
            payment_plan = [{"id": "PLAN-" + row["id"], "invoice_id": row["id"], "date": row["expected_date"],
                             "amount": row["outstanding"], "approved": True, "evidence": "Fabricated explicit quarter payment plan"}
                            for row in books["AP"] if amount(row["outstanding"]) > 0]
            ap_cash = SUPPLIER_CASH({"schema_version": "supplier-cash.v1", "entity": document["entity"],
                "currency": "AUD", "cutoff": cutoff, "control_balance": str(ap), "invoices": books["AP"], "payment_plan": payment_plan})
            future_dates = sorted(set(document["plans"][cutoff].values()))
            forecasts = {when: str(cash + sum((amount(row["amount"]) for row in ar_cash["cash"] if row["expected_date"] <= when), Decimal(0))
                                  - sum((amount(row["amount"]) for row in ap_cash["payments"] if row["date"] <= when), Decimal(0)))
                         for when in future_dates}
            current_date = date.fromisoformat(cutoff)
            year, month = (current_date.year + 1, 1) if current_date.month == 12 else (current_date.year, current_date.month + 1)
            horizon = date(year, month, calendar.monthrange(year, month)[1]).isoformat()
            within_horizon = [value for when, value in forecasts.items() if when <= horizon]
            prediction = within_horizon[-1] if within_horizon else str(cash)
            result.append({"cutoff": cutoff, "balances": {"cash": str(cash), "AR": str(ar), "AP": str(ap), "equity": str(equity)},
                           "customer_book": ar_cash, "supplier_book": ap_cash, "overdue": overdue, "forecast": forecasts,
                           "forecast_horizon": horizon, "predicted_month_end_cash": prediction,
                           "known_document_ids": sorted(known), "settlement_ids": sorted(row["id"] for row in document["settlements"] if row["date"] <= cutoff)})
        return result


def run(source: Path, output: Path) -> dict:
    content = source.read_bytes()
    document = json.loads(content)
    periods = calculate(document)
    output.mkdir(parents=True, exist_ok=False)
    previous, snapshot_hashes = None, {}
    errors = []
    for index, period in enumerate(periods):
        cutoff = period["cutoff"]
        directory = output / cutoff
        directory.mkdir()
        balances = {"090": amount(period["balances"]["cash"]), "620": amount(period["balances"]["AR"]),
                    "800": -amount(period["balances"]["AP"]), "900": -amount(period["balances"]["equity"])}
        with (directory / "trial-balance.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(HEADER)
            for code, value in balances.items():
                movement = value - previous[code] if previous else Decimal(0)
                writer.writerow([cutoff, document["entity"], "Assets" if code in {"090", "620"} else "Equity" if code == "900" else "Liabilities",
                                 code, {"090": "Bank", "620": "Receivables", "800": "Payables", "900": "Equity"}[code], code,
                                 max(movement, 0), max(-movement, 0), max(value, 0), max(-value, 0)])
        with (directory / "subledger.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["Tenant", "AccountID", "SubledgerBalance"])
            for code in ("620", "800"):
                writer.writerow([document["entity"], code, balances[code]])
        (directory / "workpaper.json").write_text(json.dumps(period, indent=2), encoding="utf-8")
        next_value = period["predicted_month_end_cash"]
        snapshot = Snapshot(label=f"Quarter forecast at {cutoff}", created=cutoff,
                            assumptions={"dated_cash": period["forecast"], "scope": "Known invoices only; no future sales or purchases"},
                            predicted={"ending_cash": float(next_value)})
        path = directory / "forecast.yaml"
        save_snapshot(snapshot, path)
        snapshot_hashes[cutoff] = hashlib.sha256(path.read_bytes()).hexdigest()
        if index:
            old_path = output / periods[index - 1]["cutoff"] / "forecast.yaml"
            old = load_snapshot(old_path)
            observed = {"ending_cash": float(period["balances"]["cash"])}
            scored = old.model_copy(update={"score": score_forecast(old.predicted, observed, weights={"ending_cash": 1.0})})
            save_snapshot(scored, directory / "previous-scored.yaml")
            errors.append({"month_end": cutoff, "predicted": str(old.predicted["ending_cash"]), "actual": period["balances"]["cash"],
                           "error": str(amount(period["balances"]["cash"]) - Decimal(str(old.predicted["ending_cash"])))})
        previous = balances
    for cutoff, digest in snapshot_hashes.items():
        if hashlib.sha256((output / cutoff / "forecast.yaml").read_bytes()).hexdigest() != digest:
            raise ValueError("An original forecast changed")
    summary = {"schema_version": "quarter-result.v1", "entity": document["entity"], "currency": "AUD",
               "source_sha256": hashlib.sha256(content).hexdigest(), "snapshot_sha256": snapshot_hashes, "forecast_errors": errors,
               "periods": periods, "scope": "Fabricated closed quarter and known-invoice cash only. No new sales, tax or funding assumptions."}
    (output / "quarter.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).with_name("case.json"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.input, args.output)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(1, f"Quarter case: {exc}\n")
    print("QUARTER RECONCILED")
