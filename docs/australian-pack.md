## Australian pack (fork extension)

This fork adds an Australian localisation in `pyfpa/au/`, built on the
data-access-recipe and industry-pack paths in CONTRIBUTING:

- **Calendar** - 30 June financial years, `FY2027` / `Q1 FY2027` /
  `1H FY2027` labels, dd/mm/yyyy (`pyfpa.au.calendar`)
- **Payroll** - super guarantee, state payroll tax (all 8
  jurisdictions, effective-dated), workers comp, leave provisions,
  contractors (`pyfpa.au.payroll`)
- **GST/BAS** - net GST from GST-exclusive series, monthly and
  quarterly settlement schedules, straight into the 13-week model
  (`pyfpa.au.gst`)
- **Xero** - report parser with tracking-category and GST-basis
  detection plus the full register/map/reconcile recipe
  (`pyfpa.io.xero_au`, [`docs/recipes/xero-au.md`](../docs/recipes/xero-au.md))
- **Economic drivers** - RBA cash rate and exchange rates, ABS CPI/WPI/
  retail/labour series, snapshotted with provenance
  (`pyfpa.au.drivers`, [`docs/recipes/au-drivers.md`](../docs/recipes/au-drivers.md))

Statutory rates are effective-dated YAML data files with official
source URLs, verified at revenue offices (2026-08-20). Simplifications
(grouping, QLD taper, WA diminishing threshold, surcharge tiers) are
documented in the module docstrings. Not tax software: forecast-grade
cash and P&L modelling only.

```python
from pyfpa.au import PayrollAssumptions, Role, payroll_forecast
from pyfpa.au.calendar import fy_month_range

frame = payroll_forecast(
    [Role(name="Engineer", annual_salary=150000, jurisdiction="VIC")],
    fy_month_range(2027),
)
```

Skills: `fpa-au-payroll`, `fpa-au-gst-bas`, `fpa-au-xero`, `fpa-au-drivers`.

Worked examples on this fork:

- [`examples/harbour-light/`](../examples/harbour-light/) - synthetic VIC
  wholesaler: Xero mapping, statutory payroll, quarterly BAS into 13-week cash,
  verified Excel.
- [`examples/arb/`](../examples/arb/) - ARB Corporation (ASX: ARB) from the FY2025
  Appendix 4E. Annual public proof, not a GST model.

Proposed upstream in
[JeffBrines/openfpa#14](https://github.com/JeffBrines/openfpa/issues/14).
This fork is not a claim to be upstream.
