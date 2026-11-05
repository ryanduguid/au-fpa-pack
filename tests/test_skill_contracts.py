# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_monthly_close_variance_drivers_sum_with_a_labelled_remainder() -> None:
    skill = (ROOT / "skills" / "fpa-monthly-close" / "SKILL.md").read_text(encoding="utf-8")
    step = next(line for line in skill.splitlines() if line.startswith("5. **Variance**"))

    assert "quantify it" in step
    assert "must sum to the variance" in step
    assert "label any remainder as unexplained" in step


@pytest.mark.parametrize("skill", ["fpa-cash-runway", "fpa-cfo-judgment"])
@pytest.mark.parametrize(
    "wording",
    [
        "Never present deferring tax, super or payroll as a source of cash without stating what it costs",
        "GIC runs from the due date, compounds daily",
        "`payment_plan_estimate`",
        "a payment plan is a scenario only",
        "The base case keeps statutory dates",
        "a plan the ATO hasn't accepted must not be assumed",
        "state that the cost can't be estimated yet, and why",
        "label it an estimate",
        "A payment plan does not change the due date",
        "the ATO decides whether to accept a payment plan",
        "personal liability does not wait for a notice",
        "The 21 days after a director penalty notice restrict only starting recovery proceedings",
        "recovery by offset earlier",
        "within 7 business days after payday",
        "20 business days for the first contribution to a particular fund",
        "out-of-cycle payments",
        "the super guarantee charge",
        "wages are not a funding source",
        "advised by a registered tax agent",
    ],
)
def test_both_cash_skills_carry_the_deferral_guardrail(skill: str, wording: str) -> None:
    text = " ".join((ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").split())
    assert wording in text


def test_readme_warns_against_the_unrelated_pyfpa_distribution() -> None:
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())

    assert "python -m pip install au-fpa-pack" in readme
    assert "Never install the PyPI distribution named `pyfpa`" in readme
