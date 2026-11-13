from __future__ import annotations

import math

import numpy as np
import pandas as pd

from pyfpa.config._snapshot import _validated_snapshot
from pyfpa.config.schemas import EntityConfig, WorkingCapitalConfig

_DAYS_PER_MONTH = 30.0
# Dollars. A derived flow this close below zero is floating-point noise from the
# balance arithmetic, not a real negative receipt or payment.
_NEGATIVE_FLOW_TOLERANCE = 1e-6


def _refuse_impossible_flows(
    revenue: pd.Series, cogs: pd.Series, balances: pd.DataFrame
) -> None:
    """Raise if the balances imply a negative receipt, purchase or payment.

    A days-based balance tracks the month's own flow, so above 30 days a sharp
    rise in revenue or cost of sales, or a sharp fall in cost of sales against
    inventory days, moves the balance by more than the month's flow. Revenue and
    cost of sales are never negative in this kernel, so a negative derived flow
    can only mean the days assumption cannot follow that month.
    """
    flows = pd.DataFrame(
        {
            "customer receipts": revenue - balances["d_ar"],
            "purchases": cogs + balances["d_inventory"],
        },
        index=balances.index,
    )
    flows["supplier payments"] = flows["purchases"] - balances["d_ap"]
    for period, row in flows.iterrows():
        for flow, amount in row.items():
            if amount < -_NEGATIVE_FLOW_TOLERANCE:
                raise ValueError(
                    f"working capital implies negative {flow} of {amount:,.2f} in {period}: "
                    "the days-based balance moved by more than the month's flow"
                )


def _profile_receivables(wc: WorkingCapitalConfig, revenue: pd.Series, opening_ar: float) -> pd.DataFrame:
    """Receipts, bad debts, write-offs and the receivables they leave, by month.

    Receipts are the profile's shares of each month's revenue plus the opening
    profile's shares of the opening balance; shares that fall after the last
    forecast month stay in receivables. `bad_debt_share` of each month's revenue
    is expensed that month and written off `write_off_after_months` later, when
    gross receivables and the allowance fall together with no cash. Opening
    receivables carry no allowance.
    """
    values = revenue.to_numpy(dtype=float)
    months = len(values)
    receipts = np.zeros(months)
    for lag, share in enumerate((wc.collection_profile or [])[:months]):
        receipts[lag:] += share * values[: months - lag]
    for month, share in enumerate((wc.opening_ar_collection_profile or [])[:months]):
        receipts[month] += share * opening_ar
    bad_debts = values * wc.bad_debt_share
    write_offs = np.zeros(months)
    lag = wc.write_off_after_months or 0
    if lag < months:
        write_offs[lag:] = bad_debts[: months - lag]
    gross = opening_ar + np.cumsum(values - receipts - write_offs)
    allowance = np.cumsum(bad_debts - write_offs)
    return pd.DataFrame(
        {"receipts": receipts, "bad_debts": bad_debts, "write_offs": write_offs,
         "gross_ar": gross, "allowance": allowance, "ar": gross - allowance},
        index=revenue.index,
    )


def _replenished_inventory(cogs: pd.Series, target: pd.Series, opening: float) -> tuple[pd.Series, pd.Series]:
    """Purchases and closing stock when purchases top stock up to the target but never fall below nil."""
    purchases, closing = [], []
    stock = opening
    for used, wanted in zip(cogs, target, strict=True):
        bought = max(0.0, wanted - stock + used)
        stock = stock + bought - used
        purchases.append(bought)
        closing.append(stock)
    return pd.Series(purchases, index=cogs.index), pd.Series(closing, index=cogs.index)


def collection_profile_from_history(invoices: pd.DataFrame, receipts: pd.DataFrame) -> list[float]:
    """A `collection_profile` measured from fully paid invoices.

    `invoices` has columns invoice, issued_on and amount; `receipts` has invoice,
    received_on and amount, one row per payment, so part payments count in the
    months they arrived. The share at lag k is the money received k calendar
    months after the month of issue, over everything invoiced. Pass the result as
    `WorkingCapitalConfig.collection_profile`, or state a profile instead; nothing
    derives one unless the caller does. Receipts show no bad debts, so with
    `bad_debt_share` scale the shares to add up to 1 less it.

    Refuses an invoice that is not paid to the cent, which would leave its unpaid
    part out and overstate how fast customers pay: leave out invoices still open.
    """
    for frame, name, date_column in ((invoices, "invoices", "issued_on"), (receipts, "receipts", "received_on")):
        missing = {"invoice", date_column, "amount"} - set(frame.columns)
        if missing:
            raise ValueError(f"{name} needs columns invoice, {date_column} and amount; missing {sorted(missing)}")
        amounts = pd.to_numeric(frame["amount"], errors="coerce")
        if frame.empty or not (np.isfinite(amounts) & (amounts > 0)).all():
            raise ValueError(f"{name} must have rows, and each amount must be a finite number above 0")
        if frame[date_column].isna().any():
            raise ValueError(f"every {name} row needs a {date_column} date")
    if invoices["invoice"].duplicated().any():
        raise ValueError("each invoice must appear once in invoices")
    issued = pd.Series(pd.to_datetime(invoices["issued_on"]).to_numpy(), index=invoices["invoice"])
    unknown = sorted(set(receipts["invoice"]) - set(issued.index), key=str)
    if unknown:
        raise ValueError(f"receipts name invoices that are not in invoices: {unknown}")
    received = pd.to_datetime(receipts["received_on"])
    issued_for_receipt = issued.loc[receipts["invoice"]].to_numpy()
    if (received.to_numpy() < issued_for_receipt).any():
        raise ValueError("a receipt is dated before its invoice was issued")
    paid = receipts.groupby("invoice")["amount"].sum().reindex(invoices["invoice"], fill_value=0.0)
    unpaid = [invoice for invoice, owed, got in zip(invoices["invoice"], invoices["amount"], paid, strict=True)
              if abs(float(owed) - float(got)) >= 0.005]
    if unpaid:
        raise ValueError(f"invoices not paid to the cent: {unpaid}; leave out invoices still open")
    lags = (received.dt.to_period("M") - pd.PeriodIndex(issued_for_receipt, freq="M")).map(lambda offset: offset.n)
    by_lag = receipts["amount"].astype(float).groupby(lags.to_numpy()).sum()
    # Over the money received, which matches the invoices to the cent, so the shares add up to 1.
    total = math.fsum(by_lag)
    return [float(by_lag.get(lag, 0.0)) / total for lag in range(int(by_lag.index.max()) + 1)]


def working_capital_from_config(
    cfg: EntityConfig, revenue_df: pd.DataFrame, cogs_df: pd.DataFrame
) -> pd.DataFrame:
    """AR/AP/inventory balances and their cash impact (rising AR/inventory uses
    cash; rising AP frees cash). First-period delta is versus opening balances.

    Receivables follow `dso_days` or, when given, `collection_profile`.
    Opening balances are assumed to sit at the modelled steady state of the days
    models. If a supplied opening balance diverges from the day-count-implied
    balance, the full gap flows through month 1 as a one-time working-capital
    cash impact. Under a collection profile, opening receivables are collected by
    `opening_ar_collection_profile` instead. With `bad_debt_share`, `ar` is net of
    the bad-debt allowance and the frame adds receipts, bad_debts, write_offs,
    gross_ar and allowance. With `inventory_basis` "replenishment", purchases
    top stock up to the days target but never below nil, excess stock carries
    forward and the frame adds purchases.

    Raises ValueError when the balances imply negative customer receipts,
    purchases or supplier payments in any month, naming the first such month
    and flow.
    """
    cfg = _validated_snapshot(cfg)
    idx = revenue_df.index
    wc = cfg.working_capital
    opening = cfg.opening_balances

    receivables = None
    if wc.collection_profile is not None:
        receivables = _profile_receivables(wc, revenue_df["total"], opening.ar)
        ar = receivables["ar"]
    else:
        assert wc.dso_days is not None  # The validated snapshot requires one receivables model.
        ar = revenue_df["total"] * (wc.dso_days / _DAYS_PER_MONTH)
    ap = cogs_df["total"] * (wc.dpo_days / _DAYS_PER_MONTH)
    inventory = cogs_df["total"] * (wc.dio_days / _DAYS_PER_MONTH)
    purchases = None
    if wc.inventory_basis == "replenishment":
        purchases, inventory = _replenished_inventory(cogs_df["total"], inventory, opening.inventory)

    df = pd.DataFrame({"ar": ar, "ap": ap, "inventory": inventory}, index=idx)
    df = df.assign(
        d_ar=df["ar"].diff().fillna(df["ar"] - opening.ar),
        d_ap=df["ap"].diff().fillna(df["ap"] - opening.ap),
        d_inventory=df["inventory"].diff().fillna(df["inventory"] - opening.inventory),
    )
    _refuse_impossible_flows(revenue_df["total"], cogs_df["total"], df)
    df = df.assign(
        wc_cash_impact=(-df["d_ar"] + df["d_ap"] - df["d_inventory"])
    )
    if receivables is not None and wc.bad_debt_share:
        df = df.join(receivables.drop(columns="ar"))
    if purchases is not None:
        df = df.assign(purchases=purchases)
    return df
