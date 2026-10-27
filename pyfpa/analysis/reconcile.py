from __future__ import annotations

import math
from collections.abc import Mapping

import pandas as pd

_COLUMNS = ["model", "actual", "variance", "variance_pct", "within_tolerance"]


def reconcile(
    model: Mapping[str, float],
    actual: Mapping[str, float],
    *,
    tolerance: float = 0.01,
) -> pd.DataFrame:
    """Compare modelled versus actual line items.

    ``variance = model - actual``, ``variance_pct = variance / |actual|``
    (undefined when actual is 0), so its sign is the variance's: positive when
    the model is above the actual, also on a negative line such as a loss. A
    line is within tolerance when
    ``|variance_pct| <= tolerance``, or when both values are 0.
    Operands, absolute variance and defined percentages must be finite;
    unsupported arithmetic raises ValueError identifying the line.

    Parameters
    ----------
    model:
        Mapping of line-item name to modelled value.
    actual:
        Mapping of line-item name to actual value. Drives the output rows.
    tolerance:
        Fractional threshold for ``within_tolerance`` (default 1%).

    Returns
    -------
    pd.DataFrame
        Indexed by line-item name with columns
        ``model, actual, variance, variance_pct, within_tolerance``.
    """
    if set(model) != set(actual):
        raise ValueError(f"reconciliation line sets differ: {sorted(set(model) ^ set(actual))}")
    rows = []
    for line in actual:
        try:
            m = float(model[line])
            a = float(actual[line])
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"reconciliation {line!r} operands must be finite") from error
        if not math.isfinite(m) or not math.isfinite(a):
            raise ValueError(f"reconciliation {line!r} operands must be finite")
        variance = m - a
        if not math.isfinite(variance):
            raise ValueError(f"reconciliation {line!r} variance must be finite")
        variance_pct = (variance / abs(a)) if a else (0.0 if m == 0 else float("nan"))
        if a and not math.isfinite(variance_pct):
            raise ValueError(f"reconciliation {line!r} percentage must be finite")
        within = (m == a) if a == 0 else (abs(variance_pct) <= tolerance)
        rows.append({
            "line": line,
            "model": m,
            "actual": a,
            "variance": variance,
            "variance_pct": variance_pct,
            "within_tolerance": within,
        })
    if not rows:
        # An empty frame has no "line" column to index on, so build the shape
        # explicitly: nothing to reconcile is a valid result, not a KeyError.
        return pd.DataFrame(columns=_COLUMNS, index=pd.Index([], name="line"))
    return pd.DataFrame(rows).set_index("line")[_COLUMNS]
