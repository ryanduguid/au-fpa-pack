"""A price and volume bridge with an independently supplied ledger residual."""
import re
from decimal import Decimal, localcontext


def revenue_bridge(rows: list[dict], prior_ledger: str, current_ledger: str) -> dict:
    with localcontext() as context:
        context.prec = 60
        if any(not isinstance(value, str) or not re.fullmatch(r"-?\d{1,15}(?:\.\d{1,2})?", value) for value in (prior_ledger, current_ledger)):
            raise ValueError("Ledger revenue requires bounded decimal strings with at most 2 places")
        prior, current = Decimal(prior_ledger), Decimal(current_ledger)
        if not prior.is_finite() or not current.is_finite():
            raise ValueError("Ledger revenue must be finite")
        seen = set()
        details = []
        for row in rows:
            if set(row) != {"service", "prior_units", "current_units", "prior_price", "current_price", "evidence"} or not row["service"] or row["service"] in seen or not row["evidence"]:
                raise ValueError("Unique services and operational evidence are required")
            seen.add(row["service"])
            if any(not isinstance(row[key], str) or not re.fullmatch(r"\d{1,15}(?:\.\d{1,6})?", row[key]) for key in ("prior_price", "current_price", "prior_units", "current_units")):
                raise ValueError("Prices and units require bounded non-negative decimal strings")
            p0, p1, q0, q1 = [Decimal(row[key]) for key in ("prior_price", "current_price", "prior_units", "current_units")]
            if any(not value.is_finite() or value < 0 for value in (p0, p1, q0, q1)):
                raise ValueError("Prices and volumes must be finite and non-negative")
            details.append({"service": row["service"], "volume": (q1 - q0) * p0,
                            "price": (p1 - p0) * q1, "prior_operating": p0 * q0,
                            "current_operating": p1 * q1, "evidence": row["evidence"]})
        if not details:
            raise ValueError("Operational evidence is required")
        volume = sum((row["volume"] for row in details), Decimal(0))
        price = sum((row["price"] for row in details), Decimal(0))
        observed = current - prior
        return {"observed": str(observed), "volume": str(volume), "price": str(price),
                "residual": str(observed - volume - price),
                "prior_ledger_difference": str(prior - sum((row["prior_operating"] for row in details), Decimal(0))),
                "current_ledger_difference": str(current - sum((row["current_operating"] for row in details), Decimal(0))),
                "details": [{key: str(value) for key, value in row.items()} for row in details],
                "method": "Volume at prior price; price at current volume. Residual is unexplained, not an inferred cause."}
