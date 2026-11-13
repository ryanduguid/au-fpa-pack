from __future__ import annotations

import math
from fractions import Fraction
from numbers import Integral

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

_CASH_COLUMNS = [
    "revenue", "gross_profit", "opex", "ebitda", "da", "interest",
    "pretax_income", "tax", "net_income", "capex",
    "operating_cash_flow", "free_cash_flow", "change_in_cash",
]


def _finite(value: float | Fraction, name: str) -> float:
    try:
        if math.isfinite(value):
            result = float(value)
            if result or value == 0:
                return result
    except (TypeError, ValueError, OverflowError):
        pass
    raise ValueError(f"{name} must be finite and within the supported numeric range")


def _exact(value: float | Fraction, name: str) -> Fraction:
    _finite(value, name)
    # Preserve integral residuals and avoid fixed-width numpy integer arithmetic.
    return Fraction(int(value)) if isinstance(value, Integral) else Fraction(value)


def _finite_columns(frame: pd.DataFrame) -> None:
    for column in (*_CASH_COLUMNS, "wc_cash_impact", "principal", "ending_cash", "bad_debts", "cogs"):
        if column in frame.columns:
            frame[column] = [_finite(value, column) for value in frame[column]]


class Carveout(BaseModel):
    """Monthly contribution of the unit being divested (positive numbers)."""
    model_config = ConfigDict(allow_inf_nan=False)

    revenue: float = Field(ge=0)
    gross_profit: float = Field(ge=0)
    opex: float = Field(ge=0)
    da: float = Field(default=0.0, ge=0)
    capex: float = Field(default=0.0, ge=0)


def divest(
    forecast: pd.DataFrame,
    carve_out: Carveout,
    *,
    sale_month: int,
    proceeds: float,
    annual_rate: float,
    tax_rate: float,
) -> pd.DataFrame:
    """Return a NEW forecast with ``carve_out`` divested after ``sale_month``
    full months, using ``proceeds`` to pay down debt.

    ``sale_month`` is the number of months the unit is **retained** before the
    sale closes: the unit contributes for forecast months 1..``sale_month`` and
    is removed from the following month onward (0-based index ``sale_month``).
    So ``sale_month=6`` means "sold 6 months out" - 6 months of contribution,
    then gone. In post-sale months, interest is reduced by
    ``proceeds * annual_rate / 12`` (debt paid down with the sale proceeds).

    The input ``forecast`` is **never mutated** - a deep copy is taken
    immediately and all writes go to that copy.

    Assumptions (documented):
    - Working-capital impact of the carve-out is held constant.
    - Bad debts, where the forecast carries them, stay at the source amounts,
      like the receivables behind them, and still come off EBITDA.
    - One-time proceeds are excluded from FCF (FCF is operating only).
    - Opening balances (debt principal) unchanged.
    - ``ending_cash`` is rebuilt from cumulative ``change_in_cash``.

    Tax is recomputed month by month at ``tax_rate``, so a forecast carrying an
    income-year tax provision (``tax_paid``, from ``income_tax``) is refused:
    its provision and payment schedule would not survive the recalculation.
    """
    if "tax_paid" in forecast.columns:
        raise ValueError(
            "divest recomputes tax month by month and cannot follow an income-year tax "
            "provision (income_tax); run the divestiture on a forecast without income_tax"
        )
    out = forecast.copy(deep=True)
    _finite_columns(out)
    carve_out = Carveout.model_validate(carve_out.model_dump())
    tax_rate = _finite(tax_rate, "tax_rate")
    n = len(out.index)
    if not 0 <= sale_month <= n:
        raise ValueError("sale_month must be within the forecast horizon")
    monthly_interest_saved = _finite(
        _exact(proceeds, "proceeds") * _exact(annual_rate, "annual_rate") / 12,
        "monthly interest saved",
    )
    opening_cash = _finite(
        float(forecast["ending_cash"].iloc[0])
        - float(forecast["change_in_cash"].iloc[0]),
        "opening cash",
    )

    for i in range(n):
        if i < sale_month:
            continue
        label = out.index[i]
        row = out.loc[label]

        gross_profit = row["gross_profit"] - carve_out.gross_profit
        opex = row["opex"] - carve_out.opex
        da = row["da"] - carve_out.da
        capex = row["capex"] - carve_out.capex
        bad_debts = row["bad_debts"] if "bad_debts" in out.columns else 0.0
        ebitda = gross_profit - opex - bad_debts
        interest = max(0.0, row["interest"] - monthly_interest_saved)
        pretax = ebitda - da - interest   # EBIT (= EBITDA - D&A) less interest
        tax = max(0.0, pretax) * tax_rate
        net_income = pretax - tax
        ocf = net_income + da + row["wc_cash_impact"]
        fcf = ocf - capex
        change_in_cash = fcf - row["principal"]

        updates = {
            "revenue": row["revenue"] - carve_out.revenue,
            "gross_profit": gross_profit, "opex": opex, "da": da, "ebitda": ebitda,
            "interest": interest, "pretax_income": pretax, "tax": tax,
            "net_income": net_income, "capex": capex, "operating_cash_flow": ocf,
            "free_cash_flow": fcf, "change_in_cash": change_in_cash,
        }
        for col in _CASH_COLUMNS:
            out.at[label, col] = float(updates[col])
        # The kernel forecast carries cogs too; the sold unit's cogs is its
        # revenue less gross profit, so revenue - cogs = gross_profit still holds.
        if "cogs" in out.columns:
            out.at[label, "cogs"] = float(
                row["cogs"] - (carve_out.revenue - carve_out.gross_profit)
            )

    out["ending_cash"] = out["change_in_cash"].cumsum() + opening_cash
    _finite_columns(out)
    return out


def net_debt_to_ebitda(
    forecast: pd.DataFrame,
    *,
    debt_balance: float,
    cash: float = 0.0,
) -> float:
    """Net-debt / annualized-EBITDA derived from the forecast's EBITDA column.

    Returns ``inf`` for an empty forecast or exactly zero EBITDA. Missing or
    non-finite evidence and unsupported monetary amounts or ratios are refused.
    Annualisation accumulates exact float values before rounding once, so a
    representable annual amount survives intermediate sum/multiply overflow.
    """
    net_debt = _finite(_exact(debt_balance, "debt_balance") - _exact(cash, "cash"), "net debt")
    if not len(forecast):
        return float("inf")
    total = sum(
        (_exact(value, "ebitda") for value in forecast["ebitda"]),
        Fraction(),
    )
    annualized = total * Fraction(12, len(forecast))
    if not annualized:
        return float("inf")
    ebitda = _finite(annualized, "annualized EBITDA")
    leverage = _finite(net_debt / ebitda, "leverage")
    if not leverage and net_debt:
        raise ValueError("leverage is below the supported numeric range")
    return leverage
