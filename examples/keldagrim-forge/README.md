# Keldagrim Forge: the timed model drill

Keldagrim Forge is a fictional Hunter Valley metal fabricator. Its Anvil and
Blast furnace lines and its two lenders are Old School RuneScape references; no
game knowledge is needed. Every figure in [config.yaml](config.yaml) is
fabricated for practice. All amounts are AUD. Synthetic example. Forecasting
aid, not tax advice; a human approves the assumptions and any funding decision.

**Human decision (the point of the drill):** can the business service the
Dwarven Bank term loan if the Anvil line's largest receipt slips a month?

## The task

Build the monthly model workbook by hand in Excel from `config.yaml`, as a
timed exercise:

1. **Assumptions sheet.** Every editable driver as a named input cell or named
   input row, holding values, in blue font (`0000FF`). This is the only sheet
   a reviewer should ever need to edit.
2. **Model sheet.** Line labels in column A, one month per column from column B
   (the 12 months of FY2026-27, July 2026 to June 2027), and formulas in every
   calculation cell. Formula vocabulary: arithmetic, `^`, `SUM`, `MIN`, `MAX`
   and `IF` only.
3. **Check rows.** At least one row labelled `check_*` carrying self-checks
   that evaluate to zero while the model is intact (cash roll-forward, gross
   profit build, net income build are the usual three).

The workbook must reproduce these engine lines for every month: `revenue`,
`cogs`, `gross_profit`, `opex`, `ebitda`, `da`, `interest`, `pretax_income`,
`tax`, `net_income`, `wc_cash_impact`, `operating_cash_flow`, `capex`,
`principal`, `free_cash_flow`, `change_in_cash`, `ending_cash`.

For the stress run, model the Anvil line's largest receipt slipping a month as
[scenarios.yaml](scenarios.yaml) defines it: the $238,017 receipt moves from
the December 2026 working-capital cash impact to January 2027, and the cash
rows that derive from it follow. Score that workbook with
`--scenario receipt-delay`; the base scenario scores the undelayed build.

## Score it

From the repository checkout:

```bash
uv run --locked --extra dev python examples/keldagrim-forge/drill.py path/to/your.xlsx
uv run --locked --extra dev python examples/keldagrim-forge/drill.py path/to/your.xlsx --scenario receipt-delay
```

The drill runs `verify_structure` and `verify_workbook` against the engine and
prints one JSON document to stdout: structure, numbers, and any failure by line
and month, with the same scorecard in words on stderr. It reads your workbook
and computes locally. Record your own time; the drill records nothing.

For calibration, `model_to_excel` builds a passing workbook from the same
config in one call, and `tests/test_keldagrim_forge.py` shows the failure modes
the drill catches.
