# Schedule withholding for payroll cash forecasts

`settlement_events` can take each role's Schedule 1 withholding, worked out by
the Australian Tax Calculators executable, instead of the average-rate
assumption, which remains available. No tax formula or rate table is duplicated
in this pack.

## Install the calculator

The calculator has no tagged release yet. Install it with
[Rust](https://rustup.rs/) 1.99 or later from the commit this recipe was checked
against:

```bash
cargo install --locked --git https://github.com/ryanduguid/australian-accounting --rev b07de6fd0a34fe69a5999dcf45753c1a22a6e3c3 australian-tax-calculators
```

That commit's executable reports `engine_version` 1.0.0. The adapter never
installs or downloads a calculator: you choose the executable and pin the
version it must report.

## Settle one month

```python
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

from pyfpa.au.payg_withholding import RolePay
from pyfpa.au.paygw import paygw_due_rule
from pyfpa.au.payroll import PayrollAssumptions, Role, payroll_forecast
from pyfpa.au.payroll_settlement import settlement_events
from pyfpa.io.native_tax import calculate_role_withholding

# A fabricated role on $60,000 a year: the frame holds $5,000.00 for July 2026.
months = pd.period_range("2026-07", periods=1, freq="M")
payroll = payroll_forecast([Role(name="Example role", annual_salary=60000)], months,
                           PayrollAssumptions(workers_comp_rate=0))
# This example settles wages and withholding only; super needs its own due rule.
payroll["super_guarantee"] = 0.0

payday = date(2026, 7, 31)
payments = [RolePay("Example role", payday, Decimal("5000.00"), "monthly", 2,
                    scope_confirmed=True)]
executable = Path(shutil.which("australian-tax-calculators") or "")
withholding = calculate_role_withholding(payments, executable=executable,
                                         engine_version="1.0.0")
events = settlement_events(
    payroll, [payday], role_withholding=withholding,
    due_rules={"payg_withholding": paygw_due_rule("medium", deferred_bas_payer=False)},
)
for event in events:
    print(event.component, event.due_date, event.amount)
```

Each result keeps the calculator's full JSON in `evidence_json`, with its
sources, source date and warnings: keep it with the forecast. A refusal, a
timeout, a missing executable, a different `engine_version` or a result without
that evidence stops the calculation rather than falling back to an average rate.

## Scope

Each role payment needs a distinct role and payday, an explicit scale and pay
period, earnings in whole cents and confirmed regular-pay scope. The adapter
sends scales 1, 2, 3, 5 and 6 with weekly, fortnightly or monthly pays. It
refuses scale 4 and quarterly pays, and sends no tax offsets, Medicare levy
adjustment or extra amount for 53 or 27 pays, although the calculator accepts
them. Bonuses, back payments, termination payments and study loans are outside
it too.

Settlement uses each payday's gross and withholding as given, so pays can
differ. A month's role pays must reconcile to the frame's gross wages within
half a cent a payment, and the frame's bonuses must be nil. `payroll_forecast`
holds a twelfth of each annual salary a month, so monthly pays reconcile to it
and weekly or fortnightly pays only to a frame holding the month's actual pays.
Repeated roles, undeclared or missing paydays, both modes at once and
unreconciled gross are refused. Super and the other payroll costs settle as
before.

These are forecast cash events, not a payroll calculation, lodgment or
compliance verdict. Use fabricated inputs for examples and keep private payroll
data local.
