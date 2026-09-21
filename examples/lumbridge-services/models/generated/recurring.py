"""Repeat the fabricated Lumbridge cash forecast after a closed month."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import pandas as pd
from lumbridge import ROOT, forecast

from pyfpa.backtest.score import score_forecast
from pyfpa.backtest.snapshot import Snapshot, load_snapshot, save_snapshot


def refresh(actuals_path: Path, controls_path: Path, assumptions_path: Path) -> dict:
    base_paths = [actuals_path.parent / name for name in (
        "assumptions.json", "xero_pl.csv", "xero_bs.csv", "payroll.csv", "invoices.csv", "payments.csv")]
    source_bytes = {path: path.read_bytes() for path in (
        *base_paths, actuals_path, controls_path, assumptions_path)}
    base = forecast(data=actuals_path.parent)
    controls = json.loads(source_bytes[controls_path])
    if set(controls) != {"tenant", "currency", "closed_through", "closing_cash", "closing_receivables", "complete_bank_population", "bank_evidence", "receivables_evidence"}:
        raise ValueError("Unexpected bank control fields")
    if controls["tenant"] != "Lumbridge Services" or controls["currency"] != "AUD" or controls["complete_bank_population"] is not True:
        raise ValueError("Explicit matching identity and complete bank population are required")
    if not controls["bank_evidence"] or not controls["receivables_evidence"]:
        raise ValueError("Independent closing-balance evidence is required")
    close = pd.Timestamp(controls["closed_through"])
    if close != close.normalize() or not close.is_month_end or close.to_period("M") not in base["monthly"].index:
        raise ValueError("Close must be a forecast month end")
    start = pd.Timestamp(base["assumptions"]["forecast_start"])
    actuals = pd.read_csv(io.BytesIO(source_bytes[actuals_path]), dtype=str, keep_default_na=False)
    expected = {"transaction_id", "source_id", "date", "category", "receipts", "payments"}
    if set(actuals) != expected or actuals.empty:
        raise ValueError("Supply the complete actual bank transaction table")
    if actuals["transaction_id"].duplicated().any() or actuals[["transaction_id", "source_id", "category"]].eq("").any().any():
        raise ValueError("Actual bank IDs must be unique and linked")
    actuals["date"] = pd.to_datetime(actuals["date"], format="%Y-%m-%d")
    if not actuals["date"].between(start, close).all():
        raise ValueError("Actuals must cover only the closed forecast periods")
    for column in ("receipts", "payments"):
        if not actuals[column].str.fullmatch(r"\d{1,15}(?:\.\d{1,2})?").all():
            raise ValueError("Actual cash amounts require explicit cents or whole dollars")
        actuals[column] = pd.to_numeric(actuals[column])
        if not actuals[column].map(lambda x: 0 <= x < float("inf")).all():
            raise ValueError("Actual cash amounts must be finite and non-negative")
    if ((actuals["receipts"] > 0) == (actuals["payments"] > 0)).any():
        raise ValueError("Actuals must have exactly one positive cash side")
    ledger = base["ledger"].copy(deep=True)
    planned = ledger.set_index("id")
    if not set(actuals["source_id"]) <= set(planned.index):
        raise ValueError("Unmapped actual bank source ID")
    # A receipt can only reconcile an invoice billed by the closed month; later
    # service-month invoices are advances and must not reduce closed-period AR.
    future_receipts = actuals["receipts"].astype(float).gt(0) & actuals["source_id"].map(
        planned["date"].dt.to_period("M") > close.to_period("M"))
    if future_receipts.any():
        raise ValueError("Receipts cannot be mapped to invoices after the close")
    for row in actuals.itertuples():
        expected_row = planned.loc[row.source_id]
        if row.category != expected_row["category"] or bool(row.receipts) != bool(expected_row["receipts"]):
            raise ValueError("Actual category or cash direction does not match its source")
    receipts = actuals.groupby("source_id")["receipts"].sum()
    payments = actuals.groupby("source_id")["payments"].sum()
    # Plans and observed receipts stay separate; only remaining cash enters the refresh.
    for index, row in ledger.iterrows():
        ledger.loc[index, "receipts"] -= receipts.get(row["id"], 0)
        ledger.loc[index, "payments"] -= payments.get(row["id"], 0)
    if (ledger[["receipts", "payments"]] < -0.005).any().any():
        raise ValueError("Actual allocations exceed their source amount")
    assumptions = pd.read_csv(io.BytesIO(source_bytes[assumptions_path]), dtype=str, keep_default_na=False)
    if set(assumptions) != {"invoice_id", "due_date", "expected_date", "disputed_amount", "reason", "evidence"}:
        raise ValueError("Unexpected receipt assumption columns")
    invoice_ids = set(planned.index[planned["receipts"] > 0])
    if assumptions["invoice_id"].duplicated().any() or set(assumptions["invoice_id"]) != invoice_ids:
        raise ValueError("Receipt assumptions must cover each invoice exactly once")
    changes = []
    for row in assumptions.itertuples():
        due, expected_date = pd.Timestamp(row.due_date), pd.Timestamp(row.expected_date)
        dispute = float(row.disputed_amount)
        if pd.isna(due) or pd.isna(expected_date) or not 0 <= dispute <= planned.loc[row.invoice_id, "receipts"] or not row.reason or not row.evidence:
            raise ValueError("Receipt timing requires dates, bounded disputed amount, reason and evidence")
        selected = ledger["id"] == row.invoice_id
        remaining = float(ledger.loc[selected, "receipts"].iloc[0])
        if remaining > 0 and expected_date <= close:
            raise ValueError("Uncollected invoices need a future expected date")
        original_date = planned.loc[row.invoice_id, "date"]
        if expected_date != original_date:
            changes.append({"invoice_id": row.invoice_id, "previous_date": str(original_date.date()),
                            "expected_date": str(expected_date.date()), "remaining": remaining,
                            "disputed_amount": dispute, "reason": row.reason, "evidence": row.evidence})
        ledger.loc[selected, "date"] = expected_date
    future = ledger[(ledger["receipts"] > 0) | (ledger["payments"] > 0)].copy()
    if (future["date"] <= close).any():
        raise ValueError("Unpaid past-due payments need explicit revised payment assumptions")
    closing_cash = float(base["bs"]["Business Bank Account"] + actuals["receipts"].sum() - actuals["payments"].sum())
    invoices = pd.read_csv(io.BytesIO(source_bytes[actuals_path.parent / "invoices.csv"]))
    billed = invoices[invoices["service_month"] <= str(close.to_period("M"))]
    closing_ar = float(billed[["net", "gst"]].sum().sum() - actuals["receipts"].sum())
    for name, actual in (("closing_cash", closing_cash), ("closing_receivables", closing_ar)):
        control = float(controls[name])
        if not float("-inf") < control < float("inf") or abs(actual - control) > 0.005:
            raise ValueError(f"{name} does not reconcile to independent control")
    closed_months = base["monthly"].index[base["monthly"].index <= close.to_period("M")]
    closed = actuals.groupby(actuals["date"].dt.to_period("M"))[["receipts", "payments"]].sum().reindex(closed_months, fill_value=0)
    closed["closing_cash"] = base["bs"]["Business Bank Account"] + (closed["receipts"] - closed["payments"]).cumsum()
    errors = closed.copy()
    errors["receipt_error"] = errors["receipts"] - base["monthly"].loc[closed_months, "Customer receipts"]
    errors["payment_error"] = errors["payments"] - base["monthly"].loc[closed_months, "Cash payments"]
    errors["cash_error"] = errors["closing_cash"] - base["monthly"].loc[closed_months, "Closing cash"]
    future_months = base["monthly"].index[base["monthly"].index > close.to_period("M")]
    future_cash = future.groupby(future["date"].dt.to_period("M"))[["receipts", "payments"]].sum().reindex(future_months, fill_value=0)
    future_cash["closing_cash"] = closing_cash + (future_cash["receipts"] - future_cash["payments"]).cumsum()
    predicted = {"ending_cash": float(base["monthly"].loc[close.to_period("M"), "Closing cash"]),
                 "receipts": float(base["monthly"].loc[closed_months, "Customer receipts"].sum())}
    observed = {"ending_cash": closing_cash, "receipts": float(actuals["receipts"].sum())}
    if any(value == 0 for value in observed.values()):
        raise ValueError("Zero observed metrics require an explicit scoring treatment")
    score = score_forecast(predicted, observed, weights={"ending_cash": 0.5, "receipts": 0.5})
    if any(path.read_bytes() != source_bytes[path] for path in base_paths):
        raise ValueError("A base forecast source changed during the refresh")
    return {"base": base, "actuals": actuals, "future_items": future, "future_cash": future_cash,
            "errors": errors, "changes": changes, "controls": controls, "predicted": predicted,
            "observed": observed, "score": score,
            "sources": {path.name: hashlib.sha256(content).hexdigest()
                        for path, content in source_bytes.items()}}


def run(output: Path, data: Path = ROOT / "data") -> dict:
    result = refresh(data / "refresh-actuals.csv", data / "refresh-controls.json", data / "receipt-assumptions.csv")
    output.mkdir(parents=True, exist_ok=False)
    original = Snapshot(label="Original September forecast", created="2026-09-30",
                        assumptions=result["base"]["assumptions"], predicted=result["predicted"])
    original_path = output / "original-forecast.yaml"
    save_snapshot(original, original_path)
    original_bytes = original_path.read_bytes()
    scored = load_snapshot(original_path).model_copy(update={"score": result["score"]})
    save_snapshot(scored, output / "original-scored.yaml")
    save_snapshot(Snapshot(label="October refresh", created=result["controls"]["closed_through"],
                           assumptions={"original": original.assumptions, "receipt_changes": result["changes"]},
                           predicted={str(period): float(row["closing_cash"]) for period, row in result["future_cash"].iterrows()}),
                  output / "refreshed-forecast.yaml")
    if original_path.read_bytes() != original_bytes:
        raise ValueError("Original forecast was changed")
    for name in ("errors", "future_items", "future_cash"):
        result[name].to_csv(output / f"{name}.csv", index=True)
    summary = {"closed_through": result["controls"]["closed_through"], "actuals": result["observed"],
               "receipt_changes": result["changes"], "source_sha256": result["sources"],
               "original_sha256": hashlib.sha256(original_bytes).hexdigest(),
               "scope": "Fabricated cash refresh only; future profit assumptions are unchanged. No measured forecast improvement."}
    (output / "review.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output / "review.md").write_text(
        "# Cash forecast refresh\n\nThe original forecast is retained separately from its score and the revised forecast.\n\n"
        f"Closed through {result['controls']['closed_through']}. Receipts are ${result['observed']['receipts']:,.2f} "
        f"against ${result['predicted']['receipts']:,.2f} forecast. "
        f"Bank cash closes at ${result['observed']['ending_cash']:,.2f}, agreeing to the supplied control.\n\n"
        "See errors.csv for the closed-period miss, future_items.csv for unpaid amounts and dates, "
        "and future_cash.csv for the revised schedule. Receipt changes and supporting references are in review.json.\n\n"
        "These are fabricated records, not observed business results. Changed future sales, new costs or past-due payments need their own reviewed inputs.\n",
        encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new output directory")
    args = parser.parse_args()
    run(args.output)
    print("Recurring cash refresh reconciled; original forecast retained.")
