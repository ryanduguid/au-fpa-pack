# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_monthly_close_variance_drivers_sum_with_a_labelled_remainder() -> None:
    skill = (ROOT / "skills" / "fpa-monthly-close" / "SKILL.md").read_text(encoding="utf-8")
    step = next(line for line in skill.splitlines() if line.startswith("5. **Variance**"))

    assert "quantify it" in step
    assert "must sum to the variance" in step
    assert "label any remainder as unexplained" in step


def test_readme_warns_against_the_unrelated_pyfpa_distribution() -> None:
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())

    assert "python -m pip install au-fpa-pack" in readme
    assert "Never install the PyPI distribution named `pyfpa`" in readme
