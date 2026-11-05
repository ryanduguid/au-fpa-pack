# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""Whole-of-state public holidays in the due-date roll.

Taxation Administration Act 1953 s 8AAZMB (payment) and Schedule 1 s 388-52
(lodgment, with the same business day test in Income Tax Assessment Act 1997
s 995-1) move a date to the first business day after it. A public holiday for
the whole of any State, the ACT or the NT is not a business day, so a holiday
in one State moves the date in every State.
"""

from datetime import date

import pandas as pd
import pytest

from pyfpa.au.gst import (
    _next_business_day,
    bas_schedule,
    gst_weekly_flows,
    quarterly_bas_due_date,
)
from pyfpa.au.paygw import paygw_due_rule
from pyfpa.au.rates import load_public_holidays

# Tables 1 and 2 of the ATO's 'Lodgment and payment dates on weekends or public
# holidays' (last updated 1 July 2026): each listed holiday and its first business day.
ATO_FIRST_BUSINESS_DAY = {
    date(2026, 8, 3): date(2026, 8, 4),
    date(2026, 9, 25): date(2026, 9, 28),
    date(2026, 9, 28): date(2026, 9, 29),
    date(2026, 10, 5): date(2026, 10, 6),
    date(2026, 11, 3): date(2026, 11, 4),
    date(2026, 12, 24): date(2026, 12, 29),
    date(2026, 12, 25): date(2026, 12, 29),
    date(2026, 12, 28): date(2026, 12, 29),
    date(2026, 12, 31): date(2027, 1, 4),
    date(2027, 1, 1): date(2027, 1, 4),
    date(2027, 1, 26): date(2027, 1, 27),
    date(2027, 3, 1): date(2027, 3, 2),
    date(2027, 3, 8): date(2027, 3, 9),
    date(2027, 3, 26): date(2027, 3, 30),
    date(2027, 3, 29): date(2027, 3, 30),
    date(2027, 4, 26): date(2027, 4, 27),
    date(2027, 5, 3): date(2027, 5, 4),
    date(2027, 5, 31): date(2027, 6, 1),
    date(2027, 6, 7): date(2027, 6, 8),
    date(2027, 6, 14): date(2027, 6, 15),
}


def test_the_december_2026_quarter_is_due_on_2_march_2027():
    # 28 February 2027 is a Sunday and Monday 1 March is Labour Day in WA.
    assert quarterly_bas_due_date(pd.Period("2026-12", freq="M")) == date(2027, 3, 2)


@pytest.mark.parametrize(
    ("due", "business_day"),
    [
        (date(2027, 3, 2), date(2027, 3, 2)),  # A business day stays put.
        (date(2027, 3, 1), date(2027, 3, 2)),  # A holiday in one State moves it.
        (date(2027, 2, 27), date(2027, 3, 2)),  # A weekend then a holiday.
        (date(2027, 3, 26), date(2027, 3, 30)),  # Good Friday to Easter Monday.
        (date(2026, 12, 25), date(2026, 12, 29)),  # The Christmas run.
        (date(2027, 8, 2), date(2027, 8, 3)),  # Picnic Day, past the ATO's tables.
        (date(2026, 2, 28), date(2026, 3, 3)),  # A weekend then Labour Day (WA), before July.
        (date(2026, 9, 25), date(2026, 9, 28)),  # The ATO's date for the Victorian holiday.
        (date(2026, 9, 28), date(2026, 9, 28)),  # King's Birthday is not for the whole of WA.
        (date(2026, 11, 3), date(2026, 11, 3)),  # Melbourne Cup is not for the whole of Victoria.
        (date(2026, 12, 24), date(2026, 12, 24)),  # Christmas Eve is a part day.
        (date(2026, 12, 31), date(2026, 12, 31)),  # New Year's Eve is a part day.
    ],
)
def test_a_due_date_moves_past_every_day_that_is_not_a_business_day(due, business_day):
    assert _next_business_day(due) == business_day


@pytest.mark.parametrize(("holiday", "first_business_day"), ATO_FIRST_BUSINESS_DAY.items())
def test_a_due_date_never_falls_after_the_atos_published_date(holiday, first_business_day):
    assert _next_business_day(holiday) <= first_business_day


def test_a_part_day_holiday_is_not_listed_in_any_year():
    # Only part of 24 and 31 December is a holiday, so neither is 'a day which is a
    # public holiday' under s 8AAZMB(2)(b); public_holidays.yaml gives the State Acts.
    assert not [day for day in load_public_holidays()["holidays"] if (day.month, day.day) in {(12, 24), (12, 31)}]


def test_a_series_from_january_2026_computes_and_the_window_drops_its_past_rows():
    series = pd.Series(100.0, index=pd.period_range("2026-01", "2026-06", freq="M"))
    schedule = bas_schedule(series)
    assert schedule["due_date"].tolist() == [date(2026, 4, 28), date(2026, 7, 28)]
    _, disbursements = gst_weekly_flows(schedule, "2026-07-06")
    assert [flow.name for flow in disbursements] == ["BAS 2026Q4"]


def test_a_payday_in_march_2026_has_a_withholding_due_date():
    assert paygw_due_rule("medium", deferred_bas_payer=False)(date(2026, 3, 13)) == date(2026, 4, 21)


def test_a_day_past_the_holiday_list_is_refused():
    # The last listed day is 31 August 2027, a Tuesday, so that date stands.
    assert _next_business_day(date(2027, 8, 31)) == date(2027, 8, 31)
    with pytest.raises(ValueError, match="verified only to 2027-08-31"):
        _next_business_day(date(2027, 9, 1))


def test_a_weekend_that_rolls_past_the_holiday_list_is_refused(monkeypatch):
    # The roll, not the starting date, decides: nobody has checked the Monday.
    import pyfpa.au.rates as rates

    raw = dict(rates.load_public_holidays(), reviewed_until=date(2027, 2, 28))
    monkeypatch.setattr(rates, "load_public_holidays", lambda: raw)
    with pytest.raises(ValueError, match="verified only to 2027-02-28"):
        _next_business_day(date(2027, 2, 27))


def test_a_day_before_the_holiday_list_is_refused():
    assert _next_business_day(date(2026, 1, 2)) == date(2026, 1, 2)
    with pytest.raises(ValueError, match="start on 2026-01-01"):
        _next_business_day(date(2025, 12, 31))
