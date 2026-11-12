# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""PAYG withholding due dates for the payroll settlement model.

Taxation Administration Act 1953, Schedule 1, section 16-75 (checked 29
September 2026 on the ATO legal database):

- (2) a medium withholder pays a month's withholding by the 21st of the next
  month;
- (2A) a medium withholder that is a deferred BAS payer on that 21st pays by
  the 28th instead, and December's withholding by 28 February;
- (3) a small withholder pays a quarter's withholding by the 21st of the month
  after the quarter;
- (4) a small withholder that is a deferred BAS payer pays by 28 October,
  28 February, 28 April or 28 July.

A deferred BAS payer must notify the Commissioner of a BAS amount, does not
lodge monthly GST returns, and has BAS amounts other than medium or large
withholding and annual PAYG instalments (Income Tax Assessment Act 1997,
section 995-1). Its note gives the usual case: an entity that lodges quarterly
GST returns or pays GST by instalments. For a medium withholder the deferral
covers only the last month of each quarter: the ATO issues monthly statements
due on the 21st for the first two months and a quarterly statement due on the
28th for the third (ATO, "Activity statements", registered agent lodgment
program, last updated 1 July 2026).

The dates come from the activity statement rules in `gst_bas.yaml`, with their
next-business-day move and reviewed_until horizon, so PAYG withholding and GST
share one source. Large withholders, who pay within days of each payday, are
refused. The category and deferred status are the ones that apply to the
entity; a forecast whose withholding grows past a threshold does not change
them.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from pyfpa.au.gst import (
    LodgmentChannel,
    monthly_activity_statement_due_date,
    quarterly_bas_due_date,
)
from pyfpa.au.payroll_settlement import DueRule


def _quarter_end(payday: date) -> pd.Period:
    return pd.Period(payday, freq="Q-JUN").asfreq("M", how="end")


def _medium(payday: date, december_agent_date: bool = False) -> date:
    return monthly_activity_statement_due_date(pd.Period(payday, freq="M"), december_agent_date=december_agent_date)


def _medium_deferred(payday: date) -> date:
    month = pd.Period(payday, freq="M")
    if month == _quarter_end(payday):
        return quarterly_bas_due_date(month)
    return monthly_activity_statement_due_date(month)


def _small(payday: date, december_agent_date: bool = False) -> date:
    return monthly_activity_statement_due_date(_quarter_end(payday), december_agent_date=december_agent_date)


def paygw_due_rule(
    withholder: str,
    *,
    deferred_bas_payer: bool,
    channel: LodgmentChannel | str = LodgmentChannel.ORIGINAL,
    december_agent_date: bool = False,
) -> DueRule:
    """Due-date rule for PAYG withheld on a payday, for `due_rules["payg_withholding"]`.

    `withholder` is the entity's category, "small" or "medium"; see the module
    docstring for what makes it a deferred BAS payer. A `channel` other than
    ORIGINAL moves a small deferred withholder's quarterly statement; a medium
    withholder's statements carry a monthly obligation and keep their dates.
    `december_agent_date`, with the AGENT channel, states that the entity is
    eligible for the 21 February date of a December monthly BAS (see
    `gst_bas.yaml`), as `GstAssumptions.december_agent_date` does; the
    withholding on that statement takes its date. A deferred BAS payer lodges no
    monthly GST, so it cannot take that date.
    """
    channel = LodgmentChannel(channel)
    if withholder == "large":
        raise ValueError("large withholders pay within days of each payday; that timing is not modelled")
    if withholder not in ("small", "medium"):
        raise ValueError(f"unknown withholder category {withholder!r}; use 'small' or 'medium'")
    if december_agent_date and (deferred_bas_payer or channel is not LodgmentChannel.AGENT):
        raise ValueError(
            "december_agent_date applies only to a monthly GST statement lodged by an agent, "
            "so not to a deferred BAS payer")
    small_deferred = withholder == "small" and deferred_bas_payer
    if channel is not LodgmentChannel.ORIGINAL and not small_deferred and not december_agent_date:
        raise ValueError(
            "a lodgment channel applies only to a small withholder that is a deferred BAS payer, "
            "or with december_agent_date")
    if small_deferred:
        return lambda payday: quarterly_bas_due_date(_quarter_end(payday), channel)
    if withholder == "small":
        return lambda payday: _small(payday, december_agent_date)
    if deferred_bas_payer:
        return _medium_deferred
    return lambda payday: _medium(payday, december_agent_date)
