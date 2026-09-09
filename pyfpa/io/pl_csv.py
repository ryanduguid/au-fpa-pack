from __future__ import annotations

import csv
from math import isfinite
from pathlib import Path


def _parse_amount(raw: str | None) -> float:
    """Parse an accounting-style amount: $, thousands commas, (parens)=negative."""
    if raw is None:
        raise ValueError("missing amount field")
    s = raw.strip().replace("$", "").replace(",", "")
    if s in ("", "-"):
        return 0.0
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    value = float(s)
    if not isfinite(value):
        raise ValueError("amount must be finite")
    return -value if negative else value


def read_pl_csv(path: str | Path) -> dict[str, float]:
    """Parse a two-column (Account, Amount) P&L export into {account: amount}."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"P&L CSV not found: {p}")
    result: dict[str, float] = {}
    with p.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        if "Account" not in fields or "Amount" not in fields:
            raise ValueError(
                f"expected columns 'Account' and 'Amount', got {fields}"
            )
        for row in reader:
            account = (row["Account"] or "").strip()
            if not account:
                continue
            if account in result:
                raise ValueError(f"duplicate account in P&L CSV: {account!r}")
            result[account] = _parse_amount(row["Amount"])
    return result
