---
name: fpa-monthly-close
description: Use when running a month-end close, refreshing a forecast with the latest actuals, computing plan-vs-actual variance, or producing a "how did the month go" analysis in openfpa.
---

# Monthly close (operate)

## Overview

Update the model with the latest actuals and forecast forward from the last closed position. Alongside the variance table, explain what changed, why it changed and what it means for the forecast.

## When to use

- Month-end actuals are available
- 'How did we do versus plan?' / reforecast requests

## Workflow

1. **Discover the company command.** Run
   `openfpa entrypoint-list <company-root> --kind close`. Use a registered close
   command when one exists; otherwise build the workflow from the approved
   company architecture.
2. **Ingest the closed month's actuals** (see **fpa-configure-actuals**).
3. **Establish the freeze line**: closed months use actuals; the forecast resumes from the last closed balance. Never let a not-yet-closed month drive conclusions (see **fpa-cfo-judgment**).
4. **Recompute the forecast**: `pyfpa.cashflow_from_config(cfg)` after updating config with the new closed position.
5. **Variance**: compare actual versus plan for revenue, gross margin, EBITDA, and ending cash. For each material variance, state the *driver* (volume, price, cost ratio, timing).
6. **Pick a reforecast posture** and say which you used:
   - **Plan** - frozen forecast unchanged
   - **Latest estimate** - actuals for closed months, plan forward from the last closed balance
   - **Run-rate** - project the YTD actual pace forward
7. **Write the narrative**: the 3 things that moved, the 3 risks forward.

## Judgement checks (always)

- Is the 'closed' month actually closed, or are accruals/COGS still posting?
- Did any account move because of a one-time/timing item? Separate it from run-rate.
- Multi-entity: is intercompany eliminated before you total?

## Next

Close done → **fpa-cash-runway** (near-term liquidity), **fpa-board-briefing**
(the writeup), and **fpa-backtest-learn** (score the prior forecast). Persistent
or material misses feed **fpa-research-loop** for bounded challenger epochs.
