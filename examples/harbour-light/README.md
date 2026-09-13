# Harbour Light Pty Ltd

Synthetic Victorian lighting wholesaler for FY2027 (July 2026 to June 2027).
This is the Australian pack's Xero / payroll / GST worked example. It is not a
client. Numbers come from the committed Xero fixtures.

```bash
python3 examples/harbour-light/run_harbour.py
```

## What it proves

- Xero GST-exclusive P&L with North/South tracking annualises into `EntityConfig`
  channels.
- `payroll_forecast` for VIC roles ties gross wages and super to the Xero wage
  and super lines. Payroll tax in the fixture ($1,300) is **not** used: wages sit
  under Victoria's $1m threshold, so the kernel pays nil. That gap is the point
  of using statutory tables instead of copying the export.
- Leave provisions remain a P&L expense and are added back in monthly cash.
- GST collections, creditable purchases and BAS settlements reconcile in the
  monthly and 13-week models (September quarter due 28 October 2026).
- The example extends the standard workbook with leave and GST reconciliation
  rows. The exporter verifies every monthly output column before replacing
  the workbook; the runner then writes the briefing.

## Cash assumptions and reconciliation

The opening GST and GST Clearing liabilities total $3,850. This synthetic
example assumes both are paid on 28 July 2026. Opening receivables, payables
and inventory remain at their starting balances. GST on forecast sales and
purchases is assumed to move through the bank in the same month; overhead
and supplier payments are fully creditable, while the GST-free sales remain
untaxed. These assumptions require confirmation for another company.

Annual cash reconciles as follows:

| Movement | AUD |
| --- | ---: |
| Opening cash | $85,420.00 |
| Net loss | -$86,774.40 |
| Non-cash leave provisions added back | $46,886.40 |
| GST collected less GST paid on purchases | $38,520.00 |
| Opening and forecast BAS settlements | -$32,740.00 |
| June ending cash | $51,312.00 |

Opening GST of $3,850 plus $38,520 accrued less $32,740 settled leaves $9,630
payable in July 2027. The 13-week forecast starts from reconciled September
cash of $81,228 and ends with $60,312. It includes 7 fortnightly payroll
payments beginning in week 1. The monthly model spreads payroll evenly, so
the weekly and monthly closing balances differ with pay dates.

## What it does not do

- Monthly GST settlement (this entity is quarterly).
- Live Xero OAuth. Fixtures only.
- Franking, PAYG instalments, or grouping.
- A separate PAYG withholding settlement schedule, loan repayments or capital
  expenditure based on the opening balance sheet. The forecast is limited to
  the configured flows; positive cash does not establish funds available to spend.

See `.fpa/` for lineage, intake, and the registered `harbour-light-pipeline`
entrypoint. The separate `harbour-light-workbook` report runs
`python3 -m models.generated.harbour_excel` from this directory and uses the
same verification before delivery.
