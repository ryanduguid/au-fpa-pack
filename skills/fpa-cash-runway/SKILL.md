---
name: fpa-cash-runway
description: Use when answering "when do we run out of cash", building a 13-week cash forecast, sizing a credit line, or analysing near-term liquidity and payment timing in openfpa.
---

# Cash runway (operate)

## Overview

Build the 13-week direct-method cash forecast - the operator's near-term liquidity view. Schedule the known weekly receipts and disbursements, show the **raw** cash position (no automatic LOC draws), and report the trough and first negative week.

**Core principle:** Show the unfinanced position. A visible shortfall is the whole point - it sizes the credit line.

## When to use

- 'When do we run out of money?' / runway questions
- Sizing or stress-testing a working-capital line
- Lumpy near-term cash events (inventory buys, tax, payroll cadence)

## Workflow

1. **Discover the company command.** Run
   `openfpa entrypoint-list <company-root> --kind cash`. Use the registered cash
   workflow when one exists.
2. **Build the schedule** as a `Cash13Config`: `opening_cash`, `weeks` (default 13), and `receipts`/`disbursements` lists of `WeeklyFlow(name, amount, start_week, recurrence)`. Recurrence is `once`, `weekly`, `biweekly`, `monthly` or `quarterly`. A `monthly` or `quarterly` flow also takes an `anchor_date` and needs the config's `window_start`, the first day of week 1: it recurs every 1 or 3 months from `anchor_date` on that day of month, or on the month's last day when that is earlier (the 31st falls on 28 or 29 February), and each date lands in the week that contains it. Dates before week 1, outside `start_week` to `end_week` or past the horizon are dropped. Take BAS settlements from `gst_weekly_flows` (**fpa-au-gst-bas**) rather than a `quarterly` flow, so they keep their BAS due dates. Model what you actually know: AR collections on their expected weeks, payroll on its cadence, inventory POs on their due dates, quarterly tax.
3. **Forecast**:
   ```python
   import pyfpa
   from pyfpa.io.loaders import load_cash13_config
   weekly = pyfpa.cash13_forecast(load_cash13_config("examples/ridgeline/cash13.yaml"))
   runway = pyfpa.runway_summary(weekly)
   # {'min_cash': -146000.0, 'min_week': 7, 'first_negative_week': 3, 'negative_weeks': [3, 6, 7, 8, 11]}
   ```
4. **Interpret** (see **fpa-cfo-judgment**): a negative `min_cash` means 'needs a draw of at least this much,' not "insolvent." `first_negative_week` is the deadline to act, and `negative_weeks` names every week that ends below zero, so a short dip reads apart from a long one. Size the credit line to the trough plus a buffer.
   With an approved overdraft or facility, set `facility_limit` (and optionally `headroom_buffer`) on the config: the forecast adds a `headroom` column, and `pyfpa.runway_summary(weekly, cfg.headroom_buffer)` adds `min_headroom`, `first_headroom_breach_week` and `headroom_breach_weeks`. The limit is capacity only, so `ending_cash` stays the raw position; take the limit from the facility document, not from memory.
5. **Report**: trough amount + week, first-negative week, the weeks below zero, and the recommended line size / action.

## Statutory deferral guardrail

Never present deferring tax, super or payroll as a source of cash without stating what it costs and that it may not be available. This applies to any scenario, recommendation or line of a briefing that stops, delays or defers a tax payment, a super contribution or wages.

- **Tax:** GIC runs from the due date, compounds daily and has not been deductible since 1 July 2025. A payment plan does not change the due date.
- **Payment plan:** a payment plan is a scenario only. The base case keeps statutory dates, and a plan the ATO hasn't accepted must not be assumed. In the scenario, show the cost with `payment_plan_estimate` (`pyfpa.au`), label it an estimate, and put its `payment_plan_weekly_flows` in place of the tax's own flow.
- **No estimate:** `payment_plan_estimate` refuses a date outside `gic.yaml`, which starts on 1 January 2026 and ends at the last GIC rate the ATO has published. When it does, state that the cost can't be estimated yet, and why, give no figure, and still state the other consequences here.
- **ATO approval:** the ATO decides whether to accept a payment plan, so never describe one as agreed or available until it has. A plan needs an up-front payment and every new liability paid on time, and a default can make the whole balance payable at once.
- **Directors:** a director's personal liability does not wait for a notice. If the company's PAYG withholding, GST or super guarantee charge is still unpaid at the end of its due day, a director owes a penalty equal to the unpaid amount then, and a new director 30 days after appointment (Taxation Administration Act 1953 Schedule 1 s 269-20). The 21 days after a director penalty notice restrict only starting recovery proceedings (s 269-25). If the company pays in that time, or in limited cases enters administration or winding up, the penalty is remitted (s 269-30). The restriction does not cover applying a director's own credits against the penalty (ss 8AAZL and 8AAZLB), so the Act allows recovery by offset earlier, although the ATO says it gives a notice first.
- **Super:** for earnings paid from 1 July 2026, the general rule is that the fund must receive super within 7 business days after payday. Longer periods apply: 20 business days for the first contribution to a particular fund, whether that is a new starter or an existing employee switching funds; out-of-cycle payments; exceptional circumstances the ATO determines; and overlapping due dates (Superannuation Guarantee (Administration) Act 1992 ss 6(1) and 18C(2)). Super not received by the end of the period that applies brings the super guarantee charge, which adds interest and an administrative uplift of up to 60% to the unpaid super. The GIC estimate does not cover it.
- **Payroll:** wages are not a funding source. Deliberately underpaying staff can be a criminal offence, so take legal advice before any change to when staff are paid.

State these consequences beside the option and leave the decision with a person, advised by a registered tax agent.

## Common mistakes

- Smoothing monthly numbers into weeks instead of scheduling the real lumpy items - the lumps are the signal.
- Auto-covering the shortfall with a draw and hiding the gap. Don't; show it.

## Next

Feed `runway` into **fpa-board-briefing** for the writeup.
