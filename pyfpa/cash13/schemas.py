from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The weekly cash contract follows the entity config: an unrecognised key is a
# mistake, and every number must be finite. Accepting extras let a misspelt
# field fall back to its default with no word to the person who wrote it, and a
# NaN opening balance turned every ending_cash row into NaN.
_STRICT = ConfigDict(extra="forbid", allow_inf_nan=False)


class WeeklyFlow(BaseModel):
    """A scheduled cash flow. `amount` is a magnitude (>=0); whether it is a
    receipt or disbursement is determined by which list it lives in.

    `once`, `weekly` and `biweekly` count in weeks from `start_week`.
    `monthly` and `quarterly` recur every 1 or 3 months from `anchor_date`, on
    its day of month or the month's last day when that is earlier (the 31st
    falls on 30 April and on 28 or 29 February). Each date lands
    in the week that contains it, counted from the config's `window_start`.
    `start_week` and `end_week` bound the weeks every recurrence can land in."""

    model_config = _STRICT

    name: str
    amount: float = Field(ge=0)
    start_week: int = Field(ge=1)
    recurrence: Literal["once", "weekly", "biweekly", "monthly", "quarterly"] = "once"
    end_week: int | None = Field(default=None, ge=1)
    anchor_date: date | None = None

    @model_validator(mode="after")
    def _end_after_start(self) -> WeeklyFlow:
        if self.end_week is not None and self.end_week < self.start_week:
            raise ValueError("end_week must be >= start_week")
        return self

    @model_validator(mode="after")
    def _anchor_for_monthly_and_quarterly(self) -> WeeklyFlow:
        if (self.recurrence in ("monthly", "quarterly")) != (self.anchor_date is not None):
            raise ValueError("a monthly or quarterly flow needs an anchor_date, and no other flow takes one")
        return self


class Cash13Config(BaseModel):
    model_config = _STRICT

    opening_cash: float
    weeks: int = Field(default=13, ge=1, le=52)
    receipts: list[WeeklyFlow] = Field(default_factory=list)
    disbursements: list[WeeklyFlow] = Field(default_factory=list)
    # A magnitude: the approved overdraft or facility limit. Capacity only; the
    # forecast still draws nothing, so ending cash stays the raw position.
    facility_limit: float | None = Field(default=None, ge=0)
    headroom_buffer: float = Field(default=0.0, ge=0)
    # The first day of week 1: week n runs for 7 days from window_start plus
    # 7(n - 1) days, as gst_weekly_flows and settlement_weekly_flows count.
    # Monthly and quarterly flows need it to place their dates.
    window_start: date | None = None

    @model_validator(mode="after")
    def _buffer_needs_a_limit(self) -> Cash13Config:
        if self.headroom_buffer > 0 and self.facility_limit is None:
            raise ValueError("headroom_buffer needs a facility_limit")
        return self

    @model_validator(mode="after")
    def _dated_flows_need_a_window(self) -> Cash13Config:
        flows = [*self.receipts, *self.disbursements]
        if self.window_start is None and any(flow.anchor_date is not None for flow in flows):
            raise ValueError("monthly and quarterly flows need a window_start")
        return self
