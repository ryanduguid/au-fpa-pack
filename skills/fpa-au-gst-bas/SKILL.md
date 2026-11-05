---
name: fpa-au-gst-bas
description: Use when forecasting cash for a GST-registered Australian entity - net GST positions, BAS settlement timing (monthly or quarterly), GST-free and input-taxed categories, 13-week cash impacts.
---

# Australian GST and BAS cash timing

Use when forecasting cash for a GST-registered Australian entity. GST
collections and BAS settlements create material cash swings that a
naive P&L-to-cash bridge misses entirely.

## Workflow

1. Establish facts (intake): BAS cycle (quarterly default; monthly
   mandatory at $20m+ GST turnover), share of GST-free or input-taxed
   revenue, share of purchases without input tax credits, whether a
   tax/BAS agent lodges (extensions).
2. Compute the monthly net GST position from GST-EXCLUSIVE series:

   ```python
   from pyfpa.au import BasCycle, GstAssumptions, bas_schedule, monthly_gst

   gst = monthly_gst(revenue_ex_gst, purchases_ex_gst,
                     GstAssumptions(bas_cycle=BasCycle.QUARTERLY))
   schedule = bas_schedule(gst["net_gst"])
   ```

3. Feed the 13-week model:

   ```python
   from pyfpa.au import gst_weekly_flows

   receipts, disbursements = gst_weekly_flows(schedule, window_start="2026-10-01")
   config.receipts.extend(receipts)
   config.disbursements.extend(disbursements)
   ```

4. Reconcile: management P&L (GST-exclusive) versus bank cash (GST-inclusive).
   Receipts in the cash model should run ~1.1x taxable revenue. That uplift is
   the output GST collected, and it is a reconciliation check, not the BAS
   settlement. The settlement is the net position: output GST less the input
   tax credits on GST-bearing purchases. Take it from the `net_gst` amount in
   `schedule`, or a purchase-heavy entity's BAS payment is overstated.

## Due dates

The quarterly cycle is 28 Oct / 28 Feb / 28 Apr / 28 Jul, and monthly is the
21st of the following month. A due date that is not a business day moves to the
next business day. A weekend is not a business day, and nor is a public holiday
for the whole of any state or territory: it moves the date in every state, so
the December 2026 quarter is due on 2 March 2027 because 1 March is Labour Day in
WA. Christmas Eve and New Year's Eve are part-day holidays and do not move a date.
The ATO's table publishes 29 December 2026 and 4 January 2027 for them, as guidance
with no stated basis for a part day, so cite the later date only as the ATO's and
not as the statutory one. `schedule` shows the date the rule names as `nominal_due_date` and the
effective date as `due_date`; forecast cash on `due_date`. Holidays come from the
dated list in `public_holidays.yaml`, and a date outside its span raises.
Agent lodgment program extensions are NOT modelled; forecasting on the
standard dates is conservative for payments. If the company relies on agent
extensions for cash, override due dates in a generated company skill.

## Pitfalls

- Never apply 10% to a GST-inclusive number; divide by 11 to extract
  GST from inclusive amounts.
- Wages and super carry no GST; do not run payroll through
  `monthly_gst` purchases.
- A quarter is only scheduled when all 3 months exist in the series;
  partial trailing quarters are dropped, not prorated.
- Refund positions (heavy capex) return as receipts; check the refund
  is plausible before banking it in week 4.

## Calculator comparison

Use a simple add/remove-GST calculator to check amount arithmetic only.
Match the rate and inclusive/exclusive basis, then compare output GST,
purchase credits and net settlement separately. Taxable sales and creditable
purchases have independent evidence and proportions: a GST-free sale does
not by itself establish that purchase credits are nil. Keep input-taxed
treatment and any exceptions subject to review.

Use fabricated all-taxable, GST-free, input-taxed and mixed scenarios from
`docs/australian-pack.md` before a company-specific comparison. Record each
component and rounding stage; keep full working precision until the required
rounding point. A matching amount does not establish registration, attribution
to a tax period or the actual BAS due date. Confirm those separately before
using a settlement in the cash forecast.
