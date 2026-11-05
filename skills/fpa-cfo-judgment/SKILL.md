---
name: fpa-cfo-judgment
description: Use when interpreting financial actuals, reviewing margins or cash, drawing conclusions from a P&L or balance sheet, or about to tell someone a number means something - the judgement layer that separates "AI that does maths" from "AI that thinks like a CFO."
---

# CFO judgement

## Overview

A forecast can add up and still misrepresent the business. Use these checks during any analysis, including a close, briefing, runway assessment or scenario.

Before reporting a figure, check what has not been recorded yet.

## The reflexes

| Trap | What a CFO checks |
|------|-------------------|
| **Pre-close months look great** | COGS and accruals post late. A high gross margin in a not-yet-closed month is usually unposted cost, not real profit. Exclude pre-close months from conclusions, or flag them loudly. |
| **A suspiciously profitable month** | Same root cause - almost always a timing/posting artefact. Reconcile before celebrating. |
| **Data seams** | When 2 ingestion sources or periods meet (for example, actuals → forecast handoff), look for double-counts and gaps at the boundary. |
| **Flash cash versus GL cash** | The bank balance and the GL cash rarely tie out intraday (in-flight deposits, uncleared cheques). Know which one you're quoting. |
| **Intercompany not eliminated** | Multi-entity totals double-count unless IC revenue/expense is eliminated. A 'profitable' entity may just be billing its sibling. |
| **Working-capital seam** | openfpa assumes opening AR/AP/inventory sit at the modelled steady state. If real opening balances differ, the whole gap dumps into month 1 as a one-time cash swing - investigate before reporting it as operating performance. |
| **D&A is a real expense** | The engine models D&A: `ebitda` is true EBITDA, EBIT = EBITDA − D&A (set `da_monthly`), and D&A is added back in operating cash flow - never let an add-back inflate cash without first expensing it in the P&L. |
| **Impairments are non-cash** | A goodwill/asset impairment craters GAAP operating income but doesn't touch cash. Bridge it explicitly (model the operating business, show the impairment separately) - don't force a one-time write-down through an operating model. |
| **Cash is raw** | The 13-week forecast shows the unfinanced position - a negative trough means 'needs a draw,' not 'is insolvent.' Say which. |
| **Known one-offs are flagged** | Read `.fpa/corrections/` for `type: context` notes (for example, 'Q3 was a one-time contract'); exclude them before attributing a forecast miss or quoting run-rate. |

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

## How to apply

1. Before stating a conclusion, run the relevant rows above against the number.
2. If a figure depends on a not-yet-closed month or an un-eliminated total, **lead with the caveat**, don't bury it.
3. When a result looks too good, assume a timing artefact until proven otherwise.

## Red flags - stop and reconcile

- 'Margin jumped this month' (is the month closed?)
- 'We're profitable' (intercompany eliminated? D&A included?)
- "We have $X in cash" (bank flash or GL? unfinanced or post-draw?)
- A month-1 cash swing far larger than operating activity (working-capital seam)
