# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""Every 2026-27 activity statement date against lodgment-calendar.

lodgment-calendar has the same author and copies the same ATO tables, so this
catches a slip in either copy, not a misreading of the ATO. It leaves a date past
its holiday tables (30 June 2027) UNKNOWN with the nominal date kept, so those
rows compare the nominal date only.
"""

from datetime import date

import pandas as pd
import pytest
from lodgmentcalendar import Facts, due_dates
from lodgmentcalendar.holidays import COVERS_FROM, COVERS_TO, HOLIDAYS

from pyfpa.au.gst import (
    LodgmentChannel,
    monthly_activity_statement_due_date,
    monthly_activity_statement_nominal_due_date,
    quarterly_bas_due_date,
    quarterly_bas_nominal_due_date,
)
from pyfpa.au.rates import load_public_holidays

QUARTER_ENDS = [pd.Period(month, freq="M") for month in ("2026-09", "2026-12", "2027-03", "2027-06")]
MONTHS = list(pd.period_range("2026-07", "2027-06", freq="M"))
# Listed by the ATO, but regional areas replace the first 2 and the last 2 are part days.
NOT_STATUTORY_HOLIDAYS = {date(2026, 9, 28), date(2026, 11, 3), date(2026, 12, 24), date(2026, 12, 31)}


def _rows(cycle: str, channel: str, facts: Facts) -> list[dict]:
    return due_dates("bas", "company", "2026-27", channel, reporting_cycle=cycle, facts=facts)["obligations"]


def _assert_matches(row: dict, nominal: date, effective: date) -> None:
    assert row["nominal_due_date"] == nominal.isoformat(), row["period"]
    if row["status"] == "DETERMINED":
        assert row["due_date"] == effective.isoformat(), row["period"]
    else:
        assert effective > COVERS_TO, row["period"]


def test_the_holiday_list_holds_the_same_days_to_june_2027():
    ours = {day for day in load_public_holidays()["holidays"] if COVERS_FROM <= day <= COVERS_TO}
    assert ours == set(HOLIDAYS) - NOT_STATUTORY_HOLIDAYS


def test_original_quarterly_dates_match():
    rows = _rows("quarterly", "self", Facts(consolidated_head_company=False, lodges_electronically=False))
    assert len(rows) == 4
    for row, quarter_end in zip(rows, QUARTER_ENDS, strict=True):
        _assert_matches(row, quarterly_bas_nominal_due_date(quarter_end), quarterly_bas_due_date(quarter_end))


def test_monthly_dates_match():
    rows = _rows("monthly", "self", Facts())
    assert len(rows) == 12
    for row, month in zip(rows, MONTHS, strict=True):
        _assert_matches(
            row, monthly_activity_statement_nominal_due_date(month), monthly_activity_statement_due_date(month)
        )


AGENT_FACTS = Facts(
    consolidated_head_company=False,
    lodges_electronically=True,
    previous_statement_lodged_electronically=True,
    includes_monthly_payg_obligation=False,
)


@pytest.mark.parametrize("obligation", ["bas", "ias"])
@pytest.mark.parametrize("entity", ["company", "trust", "partnership", "individual", "smsf"])
def test_online_quarterly_dates_match(obligation, entity):
    facts = Facts(consolidated_head_company=False, lodges_electronically=True)
    rows = due_dates(obligation, entity, "2026-27", "self", reporting_cycle="quarterly", facts=facts)["obligations"]
    for row, quarter_end in zip(rows, QUARTER_ENDS, strict=True):
        _assert_matches(
            row,
            quarterly_bas_nominal_due_date(quarter_end, LodgmentChannel.ONLINE),
            quarterly_bas_due_date(quarter_end, LodgmentChannel.ONLINE),
        )


@pytest.mark.parametrize("channel", ["tax_agent", "bas_agent"])
@pytest.mark.parametrize("obligation", ["bas", "ias"])
def test_agent_quarterly_dates_match(channel, obligation):
    rows = due_dates(
        obligation, "company", "2026-27", channel, reporting_cycle="quarterly", facts=AGENT_FACTS
    )["obligations"]
    for row, quarter_end in zip(rows[:3], QUARTER_ENDS, strict=False):
        _assert_matches(
            row,
            quarterly_bas_nominal_due_date(quarter_end, LodgmentChannel.AGENT),
            quarterly_bas_due_date(quarter_end, LodgmentChannel.AGENT),
        )
    # Quarter 4 is UNKNOWN there and refused here, because the ATO has not confirmed it.
    assert rows[3]["status"] == "UNKNOWN"
    with pytest.raises(ValueError, match="no agent program date"):
        quarterly_bas_due_date(QUARTER_ENDS[3], LodgmentChannel.AGENT)


@pytest.mark.parametrize("channel", ["tax_agent", "bas_agent"])
def test_the_december_agent_date_matches(channel):
    facts = Facts(
        annual_turnover_up_to_10m=True,
        deferred_gst_registered=False,
        lodges_electronically=True,
        previous_statement_lodged_electronically=True,
    )
    rows = _rows("monthly", channel, facts)
    assert len(rows) == 12
    for row, month in zip(rows, MONTHS, strict=True):
        _assert_matches(
            row,
            monthly_activity_statement_nominal_due_date(month, december_agent_date=True),
            monthly_activity_statement_due_date(month, december_agent_date=True),
        )
