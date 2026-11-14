# Schedule withholding for payroll cash forecasts

The existing `settlement_events` average-rate assumption remains available.
For an ordinary-pay scenario, supply explicit role payments to the local
Australian Tax Calculators executable, then pass the results to settlement.
No tax formula or rate table is duplicated in this pack.

```python
from datetime import date
from decimal import Decimal
from pathlib import Path

from pyfpa.au.payg_withholding import RolePay
from pyfpa.au.payroll_settlement import settlement_events
from pyfpa.io.native_tax import calculate_role_withholding

# A fabricated weekly payment. Use an existing binary whose origin you have
# verified, with the expected version taken from that binary's release/build.
payments = [RolePay("Example role", date(2026, 7, 3), Decimal("370.00"),
                    "weekly", 2, scope_confirmed=True)]
withholding = calculate_role_withholding(
    payments, executable=Path(r"C:\tools\australian-tax-calculators.exe"),
    engine_version="1.0.0",
)
# payroll is the existing monthly forecast frame. due_rules supplies the
# ordinary component due dates; no statutory calendar is inferred here.
events = settlement_events(payroll, [date(2026, 7, 3)],
                           due_rules=due_rules, role_withholding=withholding)
```

The native executable is an explicit prerequisite. This adapter does not install
one or assert that native version 1.0.0 has been released. The old Python
`austaxcalc` import API is not used. A local, reviewed native build can be tested
before a distribution is published; release and provenance checks remain separate.

The adapter sends money as decimal strings over stdin, selects the income year
from each pay date, verifies the returned engine/version/calculation/period and
retains the full JSON evidence in each result. Keep that evidence with the
forecast, including source dates and warnings. A calculator refusal, timeout or
invalid result stops the schedule calculation rather than falling back to an
average rate.

Each role/payment must have a distinct label and payday, an explicit scale and
pay period, earnings in whole cents and confirmed ordinary-pay scope. This
initial adapter supports the ordinary scales 1, 2, 3, 5 and 6 with weekly,
fortnightly or monthly pays. It excludes bonuses, back payments, termination,
study loans, Medicare variations, offsets and extra-pay adjustments. A newer
engine's additional options are not silently enabled. Use a separately reviewed
interface for those cases.

Schedule settlement uses the explicit gross and withholding for each payday,
allowing unequal payments. Their monthly gross must reconcile to the forecast
rounded to cents; the frame's bonuses must be zero. Repeated roles, undeclared
or missing paydays, incompatible modes and unreconciled gross are refused.
Super and other payroll cost settlement retain their existing treatment.

These are forecast cash events, not a payroll lodgment or compliance verdict.
Aggregated monthly earnings do not establish an employee's tax circumstances.
Use fabricated inputs for examples and keep private payroll data local.
