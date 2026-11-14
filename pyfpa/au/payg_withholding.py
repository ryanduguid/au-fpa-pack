# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""Explicit regular payments and retained evidence for schedule-based forecasts.

Tax formulas belong to the Australian Tax Calculators engine. These records
do not establish eligibility or replace the operator's scope confirmation.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


def require_cents(amount: Decimal, name: str) -> None:
    if not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0:
        raise ValueError(f"{name} must be a finite Decimal of 0 or more")
    exponent = amount.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -2:
        raise ValueError(f"{name} must have at most 2 decimal places")


@dataclass(frozen=True)
class RolePay:
    role_name: str
    payday: date
    earnings: Decimal
    pay_period: str
    scale: int
    scope_confirmed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.role_name, str) or not self.role_name.strip():
            raise ValueError("role_name must be a non-empty label")
        if isinstance(self.payday, datetime) or not isinstance(self.payday, date):
            raise ValueError("payday must be a date")
        require_cents(self.earnings, "earnings")
        if self.pay_period not in ("weekly", "fortnightly", "monthly"):
            raise ValueError("pay_period must be weekly, fortnightly or monthly")
        if isinstance(self.scale, bool) or not isinstance(self.scale, int) or self.scale not in (1, 2, 3, 5, 6):
            raise ValueError("scale must be 1, 2, 3, 5 or 6")
        if self.scope_confirmed is not True:
            raise ValueError("regular-pay scope must be explicitly confirmed for each role")

    @property
    def year(self) -> str:
        start = self.payday.year - (self.payday.month < 7)
        return f"{start}-{(start + 1) % 100:02d}"


@dataclass(frozen=True)
class RoleWithholding:
    payment: RolePay
    withholding: Decimal
    evidence_json: str

    def __post_init__(self) -> None:
        require_cents(self.withholding, "withholding")
        if self.withholding > self.payment.earnings:
            raise ValueError("withholding cannot exceed the role's earnings")
        if not self.evidence_json.strip():
            raise ValueError("retain the calculator's JSON evidence, including warnings and sources")
