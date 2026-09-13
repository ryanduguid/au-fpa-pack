---
name: fpa-board-briefing
description: Use when producing a board deck, investor update, or CFO briefing from an openfpa forecast - turning model output into a board-ready narrative and exportable artefacts.
---

# Board briefing (operate)

## Overview

Turn forecast output into a board/investor-grade briefing: the headline numbers, the cash story, what changed, and the risks - as markdown and Excel. Make the operator look like they have a CFO.

**Core principle:** A board wants the story and the 3 things that matter, not a data dump.

## When to use

- Board decks, investor updates, lender packages
- 'Summarise the forecast for leadership'

## Workflow

1. **Discover the company command.** Run
   `openfpa entrypoint-list <company-root> --kind report`. Use a registered
   briefing workflow when one exists.
2. **Build the forecast** (monthly + optional runway):
   ```python
   import pyfpa
   from pyfpa.io.loaders import load_cash13_config
   monthly = pyfpa.cashflow_from_config(pyfpa.load_config("examples/ridgeline/config.yaml"))
   runway = pyfpa.runway_summary(pyfpa.cash13_forecast(load_cash13_config("examples/ridgeline/cash13.yaml")))
   ```
3. **Render the briefing**:
   ```python
   from pyfpa.io.reporting import to_briefing_md, forecast_to_excel
   md = to_briefing_md(monthly, title="Acme Inc.", runway=runway)
   forecast_to_excel(monthly, "forecast.xlsx")
   ```
   `to_briefing_md` emits a headline (revenue, EBITDA, net income, ending cash), an optional 13-week runway section, and a monthly table.
4. **Add the narrative** the renderer can't. `to_briefing_md` emits only the headline, the optional runway section, and the monthly table - it has no narrative slot. So author your own markdown *around* it: prepend a `## What changed` section (the 3 things that moved) and append `## Risks` (3 forward risks) and `## The ask` (for example, "approve a $200K line to bridge the spring build"). The rendered briefing is the data spine; you supply the story.
5. **Apply judgement** (see **fpa-cfo-judgment**): caveat any pre-close months, state whether cash is flash or GL, and check that source expenses map to the right model inputs. The kernel's `ebitda` is calculated before the separately supplied D&A, which is deducted before pre-tax income and added back in operating cash flow, so it is only as good as that mapping.
6. If the audience wants the model itself, produce the live-formula workbook via **fpa-excel-model** alongside the briefing.

## One-command demo

`python examples/ridgeline/run_demo.py` runs this whole path on the synthetic demo and writes `docs/demo/briefing.md` + `forecast.xlsx`.

## Common mistakes

- Leading with a table instead of the takeaway.
- Presenting a cash trough without the recommended action.
