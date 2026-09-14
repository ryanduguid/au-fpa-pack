from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The weekly cash contract follows the entity config: an unrecognised key is a
# mistake. Accepting extras let a misspelt field fall back to its default with
# no word to the person who wrote it.
_STRICT = ConfigDict(extra="forbid")


class WeeklyFlow(BaseModel):
    """A scheduled cash flow. `amount` is a magnitude (>=0); whether it is a
    receipt or disbursement is determined by which list it lives in."""

    model_config = _STRICT

    name: str
    amount: float = Field(ge=0)
    start_week: int = Field(ge=1)
    recurrence: Literal["once", "weekly", "biweekly"] = "once"
    end_week: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _end_after_start(self) -> WeeklyFlow:
        if self.end_week is not None and self.end_week < self.start_week:
            raise ValueError("end_week must be >= start_week")
        return self


class Cash13Config(BaseModel):
    model_config = _STRICT

    opening_cash: float
    weeks: int = Field(default=13, ge=1, le=52)
    receipts: list[WeeklyFlow] = Field(default_factory=list)
    disbursements: list[WeeklyFlow] = Field(default_factory=list)
