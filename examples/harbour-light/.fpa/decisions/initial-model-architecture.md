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
  every reconciliation row. The runner rejects verification failures.

## Amendment, 10 September 2026

Ryan approved correcting the leave and GST cash findings. These amendments
replace the original example's monthly GST exclusion and extend its workbook.
The opening GST settlement date is an explicit synthetic assumption.
