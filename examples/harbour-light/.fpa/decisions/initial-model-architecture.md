# Initial Model Architecture

**Status:** Approved for the synthetic Harbour Light example.

## Objective

Prove the Australian pack on one company: Xero mapping, statutory payroll,
quarterly BAS into 13-week cash, and a verified live-formula workbook.

## Data Access

- Committed Xero Australia GST-exclusive fixtures.
- Tracking file is the channel source. Aggregated P&L is the lineage source
  (`reconcile-source` rejects duplicate account rows).

## Model Components

- North / South revenue channels, 30 June year, 30 percent company tax.
- Payroll from `payroll_forecast`, not from copying Xero wage on-cost lines
  except as a reconciling check.
- The company example adds leave provisions back to cash and reconciles GST
  accruals, opening liability and settlements in monthly and weekly cash.
  The generic monthly engine remains unchanged.

## Validation

- Fixture mapping totals.
- BAS due dates for FY2027.
- Independent leave and GST cash reconciliations.
- `verify_workbook` against the example's adjusted `monthly_forecast`, including
  every reconciliation row. The exporter verifies a temporary workbook before
  replacing the destination; the runner writes the briefing only after success.

## Amendment, 10 September 2026 (Australia/Sydney, UTC+10)

Ryan approved correcting the leave and GST cash findings. These amendments
replace the original example's monthly GST exclusion and extend its workbook.
The opening GST settlement date is an explicit synthetic assumption.


### Accepted correction evidence

The CFO question is whether the synthetic company runs out of cash after
reconciling non-cash leave and GST movements. The hypothesis is that keeping
leave expense in profit, adding its provision back to cash, and reconciling
GST collected, paid and settled will preserve annual profit while explaining
every change in the revised closing cash balance.

Evidence uses the registered July 2026 Xero P&L, tracking and balance-sheet
fixtures in `data/`, annualised over July 2026 to June 2027. The opening
balance-sheet amounts are modelling inputs, not a historical holdout. The
13-week window begins 1 October 2026. Payroll uses the existing Victorian
roles and statutory tables; this correction does not refresh those tables.

The changed company files are `harbour_model.py`, `run_harbour.py`,
`models/generated/harbour_excel.py`, `.fpa/models/entrypoints.yaml`,
`.fpa/business-profile.md`, this decision, `README.md` and `output/briefing.md`.
Repository-level evidence is in `tests/test_harbour_light.py` and the updated
root README. Leave and GST assumptions are stated in the company README.
The report command uses the existing Excel toolkit and verifier.

| Metric | Before | After |
| --- | ---: | ---: |
| Annual revenue | $1,332,000.00 | $1,332,000.00 |
| Annual net loss | -$86,774.40 | -$86,774.40 |
| June ending cash | -$1,354.40 | $51,312.00 |
| Week 13 ending cash | $33,180.40 | $60,312.00 |

The annual cash change is $46,886.40 of non-cash leave plus $5,780.00 of
net GST cash movement. Opening GST of $3,850.00 plus $38,520.00 accrued less
$32,740.00 settled leaves $9,630.00 payable. Tests independently check these
amounts, the Xero mappings, quarterly dates and weekly bank movements.
The workbook verifier compares all 27 output lines with the monthly model.

In the input-edit scenario, increasing opening GST by $1,000 raises July
settlements by $1,000 and lowers all monthly closing cash balances by $1,000;
the edited workbook still reconciles to the scenario. Corrupting a cash
formula fails verification before delivery. A failed replacement also leaves
an existing output file intact. No historical holdout is available for these
synthetic fixtures, and native Excel recalculation has not been tested.

Ryan accepted correcting the five reported defects with "OK action all of
those please" and subsequently authorised integration with "merge them
please" on 10 September 2026 in Sydney. Acceptance covers the reported cash
and evidence defects and their verification; it does not establish that this
synthetic forecast is suitable for a real company.
