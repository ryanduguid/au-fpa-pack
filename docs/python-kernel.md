## Python kernel

The importable package is `pyfpa`. The distribution name is `au-fpa-pack`.

The account-and-amount CSV readers refuse duplicate or unnamed column headings,
extra row fields and non-blank rows without an account. These cases can otherwise discard
or misassign amounts. Entirely blank rows and declared metadata columns remain
supported. Quote amounts that contain thousands separators, such as `"1,234"`.

```python
import pyfpa

config = pyfpa.load_config("examples/ridgeline/config.yaml")
monthly = pyfpa.cashflow_from_config(config)

cash_config = pyfpa.load_cash13_config("examples/ridgeline/cash13.yaml")
weekly = pyfpa.cash13_forecast(cash_config)
runway = pyfpa.runway_summary(weekly)

print(pyfpa.to_briefing_md(monthly, title="My Company", runway=runway))
```

Named scenarios change the declared 13-week flows instead of editing them. A
`FlowChange` scales every base flow of one name (`amount_factor`), pushes it
later (`delay_weeks`), or both; `add_receipts` and `add_disbursements` add new
flows. A name that matches no base flow is refused, so a misspelling cannot
leave a scenario identical to the base. A flow pushed past the horizon leaves
the forecast.

```python
scenarios = pyfpa.load_cash13_scenarios("examples/ridgeline/scenarios.yaml")
print(pyfpa.compare_scenarios(cash_config, scenarios))
```

`compare_scenarios` returns one row per scenario, base first, with the cash
trough (`min_cash`), its week, the first negative week and closing cash. It
compares declared assumptions; it does not say which scenario is likely.

The base kernel includes:

- monthly P&L and indirect cash-flow modelling
- 13-week direct-method cash forecasting, with named scenario comparison
- revenue, COGS, operating-expense, debt, tax, and working-capital primitives
- reconciliation, segment, SKU, and divestiture analysis helpers
- CSV ingestion and Markdown or Excel reporting: static value export via
  `forecast_to_excel`, and a live-formula model workbook via `model_to_excel`
  (named assumption cells, real formulas, verified against the engine in CI);
- forecast snapshots, scoring, and holdout backtests
- workspace, intake, correction, experiment, retrieval, and research records
- experimental cross-company prior and skill mining.

`EntityConfig` is a starting point; it does not prescribe every model. A company
with cohorts, projects, contracts, fleets, stores, or complex inventory may need
a different generated model.

The `model_to_excel` function compiles an `EntityConfig` into a 2-sheet workbook:
an Assumptions sheet of named, editable driver cells and a Model sheet where every
P&L and cash-flow line is a real formula referencing those names. The `verify_workbook`
function evaluates the workbook with a Python formula engine and compares every line
and month to `cashflow_from_config`, so the workbook is verified against the engine
before it is used. For cadences or layouts the kernel does not cover, compose
`pyfpa.excel.toolkit` in a company-specific exporter and verify it the same way.
