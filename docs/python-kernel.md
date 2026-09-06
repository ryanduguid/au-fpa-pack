## Python kernel

The importable package is `pyfpa`. The distribution name is `au-fpa-pack`.

```python
import pyfpa

config = pyfpa.load_config("examples/ridgeline/config.yaml")
monthly = pyfpa.cashflow_from_config(config)

cash_config = pyfpa.load_cash13_config("examples/ridgeline/cash13.yaml")
weekly = pyfpa.cash13_forecast(cash_config)
runway = pyfpa.runway_summary(weekly)

print(pyfpa.to_briefing_md(monthly, title="My Company", runway=runway))
```

The base kernel includes:

- monthly P&L and indirect cash-flow modeling;
- 13-week direct-method cash forecasting;
- revenue, COGS, operating-expense, debt, tax, and working-capital primitives;
- reconciliation, segment, SKU, and divestiture analysis helpers;
- CSV ingestion and Markdown or Excel reporting: static value export via
  `forecast_to_excel`, and a live-formula model workbook via `model_to_excel`
  (named assumption cells, real formulas, verified against the engine in CI);
- forecast snapshots, scoring, and holdout backtests;
- workspace, intake, correction, experiment, retrieval, and research records;
- experimental cross-company prior and skill mining.

`EntityConfig` is a useful starting model, not a required ontology. A company
with cohorts, projects, contracts, fleets, stores, or complex inventory may need
a different generated model.

The `model_to_excel` function compiles an `EntityConfig` into a two-sheet workbook:
an Assumptions sheet of named, editable driver cells and a Model sheet where every
P&L and cash-flow line is a real formula referencing those names. The `verify_workbook`
function evaluates the workbook with a Python formula engine and compares every line
and month to `cashflow_from_config`, so the workbook is verified against the engine
before it is used. For cadences or layouts the kernel does not cover, compose
`pyfpa.excel.toolkit` in a company-specific exporter and verify it the same way.
