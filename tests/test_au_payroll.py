import pandas as pd
import pytest

from pyfpa.au.calendar import fy_month_range
from pyfpa.au.payroll import PayrollAssumptions, Role, payroll_forecast


@pytest.fixture
def months():
    return fy_month_range(2027)  # 2026-07 .. 2027-06


def test_single_role_gross_and_super(months):
    roles = [Role(name="Engineer", annual_salary=120000, jurisdiction="NSW")]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    assert frame.loc[months[0], "gross_wages"] == pytest.approx(10000.0)
    # SG 12% from 1 July 2025
    assert frame.loc[months[0], "super_guarantee"] == pytest.approx(1200.0)


def test_ineligible_contractor_gets_no_super_or_leave(months):
    roles = [Role(name="Contractor", annual_salary=120000, contractor=True, sg_eligible=False)]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    assert frame["super_guarantee"].sum() == 0.0
    assert frame["leave_provisions"].sum() == 0.0
    assert frame.loc[months[0], "gross_wages"] == pytest.approx(10000.0)


def test_labour_contractor_gets_super_without_leave(months):
    roles = [Role(name="Labour contractor", annual_salary=120000,
                  contractor=True, sg_eligible=True)]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    assert frame.loc[months[0], "super_guarantee"] == pytest.approx(1200.0)
    assert frame["leave_provisions"].sum() == 0.0
    assert frame.loc[months[0], "total_cash"] == pytest.approx(11400.0)


def test_contractor_requires_established_sg_eligibility():
    with pytest.raises(ValueError, match="sg_eligible"):
        Role(name="Unclassified contractor", annual_salary=120000, contractor=True)


def test_established_employee_exemption_omits_sg_but_keeps_leave(months):
    roles = [Role(name="Exempt employee", annual_salary=12000, sg_eligible=False)]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    assert frame["super_guarantee"].sum() == 0.0
    assert frame.loc[months[0], "leave_provisions"] == pytest.approx(93.9230769231)


def test_start_month_vacancy(months):
    roles = [
        Role(name="Hire", annual_salary=120000, start_month="2027-01"),
    ]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    assert frame.loc[pd.Period("2026-12", freq="M"), "gross_wages"] == 0.0
    assert frame.loc[pd.Period("2027-01", freq="M"), "gross_wages"] == pytest.approx(10000.0)


def test_end_month_departure(months):
    roles = [Role(name="Leaver", annual_salary=120000, end_month="2026-09")]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    assert frame.loc[pd.Period("2026-09", freq="M"), "gross_wages"] == pytest.approx(10000.0)
    assert frame.loc[pd.Period("2026-10", freq="M"), "gross_wages"] == 0.0


def test_below_threshold_pays_no_payroll_tax(months):
    # One modest salary sits under every jurisdiction's monthly threshold slice.
    roles = [Role(name="Solo", annual_salary=60000, jurisdiction="QLD")]
    frame = payroll_forecast(roles, months)
    assert frame["payroll_tax"].sum() == 0.0


@pytest.mark.parametrize(
    "annual_taxable_wages, annual_tax",
    [
        (600000, 0),
        (1500000, 0),
        (1501000, 222.9975),
        (1550000, 11756.25),
        (1600000, 24750),
        (1650000, 38981.25),
        (1700000, 54450),
        (2000000, 69300),
    ],
)
def test_sa_threshold_deduction_and_variable_rate(months, annual_taxable_wages, annual_tax):
    # SA Payroll Tax Act 2009, Schedule 1 clauses 2 and 5: a full-year,
    # ungrouped SA employer. Ten employees keep each salary below the SG cap.
    roles = [
        Role(name=f"Role {i}", annual_salary=annual_taxable_wages / 10 / 1.12,
             jurisdiction="SA")
        for i in range(10)
    ]
    frame = payroll_forecast(roles, months)
    assert frame["payroll_tax"].sum() == pytest.approx(annual_tax, abs=0.01)
    assert frame["payroll_tax"].iloc[0] == pytest.approx(annual_tax / 12, abs=0.01)


def test_sa_interstate_payroll_requires_apportionment(months):
    roles = [
        Role(name="Adelaide", annual_salary=150000, jurisdiction="SA"),
        Role(name="Sydney", annual_salary=150000, jurisdiction="NSW"),
    ]
    with pytest.raises(ValueError, match="SA interstate payroll tax"):
        payroll_forecast(roles, months)
    # An explicit no-payroll-tax forecast still supplies the other on-costs.
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    assert frame["payroll_tax"].sum() == 0.0
    assert frame["super_guarantee"].sum() > 0.0


@pytest.mark.parametrize("first, second", [("SA", "NSW"), ("NSW", "SA")])
def test_staggered_sa_interstate_payroll_requires_apportionment(months, first, second):
    roles = [
        Role(name="First half", annual_salary=2000000, jurisdiction=first,
             end_month="2026-12"),
        Role(name="Second half", annual_salary=2000000, jurisdiction=second,
             start_month="2027-01"),
    ]
    with pytest.raises(ValueError, match="SA interstate payroll tax"):
        payroll_forecast(roles, months)
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    assert frame["payroll_tax"].sum() == 0.0
    assert frame["gross_wages"].sum() == pytest.approx(2000000)


def test_above_threshold_pays_payroll_tax(months):
    # 40 x 150k in NSW: 6m salaries + 12% SG = 6.72m taxable wages incl super,
    # well above threshold.
    roles = [
        Role(name=f"Role {i}", annual_salary=150000, jurisdiction="NSW") for i in range(40)
    ]
    frame = payroll_forecast(roles, months)
    assert frame["payroll_tax"].sum() > 0.0


def test_unregistered_entity_pays_no_payroll_tax(months):
    roles = [
        Role(name=f"Role {i}", annual_salary=150000, jurisdiction="NSW") for i in range(40)
    ]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    assert frame["payroll_tax"].sum() == 0.0


def test_total_cash_excludes_leave_provisions(months):
    roles = [Role(name="Engineer", annual_salary=120000)]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    first = months[0]
    assert frame.loc[first, "total_cost"] - frame.loc[first, "total_cash"] == pytest.approx(
        frame.loc[first, "leave_provisions"]
    )
    assert frame.loc[first, "leave_provisions"] > 0


def test_bonus_attracts_super(months):
    base = [Role(name="NoBonus", annual_salary=120000)]
    bonused = [Role(name="Bonus", annual_salary=120000, bonus_pct=0.10)]
    plain = payroll_forecast(base, months, PayrollAssumptions(payroll_tax_registered=False))
    with_bonus = payroll_forecast(
        bonused, months, PayrollAssumptions(payroll_tax_registered=False)
    )
    assert with_bonus.loc[months[0], "bonuses"] == pytest.approx(1000.0)
    assert (
        with_bonus.loc[months[0], "super_guarantee"]
        > plain.loc[months[0], "super_guarantee"]
    )


def test_sg_rate_change_at_fy_boundary():
    # June 2025 (FY2025) to July 2025 (FY2026) crosses the 11.5% -> 12% step
    # on 1 July 2025.
    months = pd.period_range("2025-06", periods=2, freq="M")
    roles = [Role(name="Engineer", annual_salary=120000)]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    june = frame.loc[pd.Period("2025-06", freq="M"), "super_guarantee"]
    july = frame.loc[pd.Period("2025-07", freq="M"), "super_guarantee"]
    assert june == pytest.approx(10000 * 0.115)
    assert july == pytest.approx(10000 * 0.12)
