## Australian pack (fork extension)

For worked cash decisions, run the [Ridgeline scenario comparison](../examples/ridgeline/README.md).
It uses the existing weekly engine and defines each metric's unit, period and formula.

This fork adds an Australian localisation in `pyfpa/au/`, built on the
data-access-recipe and industry-pack paths in CONTRIBUTING:

- **Calendar** - 30 June financial years, `FY2027` / `Q1 FY2027` /
  `1H FY2027` labels, dd/mm/yyyy (`pyfpa.au.calendar`)
- **Payroll** - super guarantee, state payroll tax (all 8
  jurisdictions, effective-dated), workers comp, leave provisions,
  contractors (`pyfpa.au.payroll`)
- **Payroll settlement** - dated obligation, due and cash events for each
  payroll cost except leave provisions, which stay accruals, with month-end
  liabilities and 13-week flows derived from them; net wages fall due on each
  payday and the caller passes the due-date rule for every other cost
  (`pyfpa.au.payroll_settlement`)
  - PAYG withholding due dates under Taxation Administration Act 1953,
    Schedule 1, section 16-75 (`pyfpa.au.paygw`)
  - super guarantee due dates under Payday Super and the quarterly rules
    before it, on a business-day calendar the caller passes
    (`pyfpa.au.super_guarantee`)
  - payroll tax due dates for monthly lodgers in all eight jurisdictions
    (`pyfpa.au.payroll_tax`)
- **GST/BAS** - net GST from GST-exclusive series, monthly and
  quarterly settlement schedules, straight into the 13-week model
  (`pyfpa.au.gst`)
- **PAYG instalments** - quarterly payers' instalments by instalment rate or
  notified amount, due on the activity statement dates, or 21 days after a
  notice given once the quarter has ended (`pyfpa.au.payg_instalments`)
- **Xero** - report parser with tracking-category and GST-basis
  detection plus the full register/map/reconcile recipe
  (`pyfpa.io.xero_au`, [`docs/recipes/xero-au.md`](../docs/recipes/xero-au.md))
- **Accounting depreciation** - an opt-in charge read from a calculation-evidence
  file on disk, with the asset movement reconciled or refused and expense,
  purchases and tax kept apart (`pyfpa.au.depreciation`,
  [`docs/recipes/accounting-depreciation.md`](recipes/accounting-depreciation.md))
- **Economic drivers** - RBA cash rate and exchange rates, ABS CPI/WPI/
  retail/labour series, snapshotted with provenance
  (`pyfpa.au.drivers`, [`docs/recipes/au-drivers.md`](../docs/recipes/au-drivers.md))

Statutory rates are effective-dated YAML data files with official
source URLs, verified at revenue offices (2026-08-20). Simplifications
(grouping, QLD taper, WA diminishing threshold, surcharge tiers) are
documented in the module docstrings. Not tax software: forecast-grade
cash and P&L modelling only.

SA uses a separate $1.5 million liability threshold and $600,000 deduction.
The rate rises linearly from 0% to 4.95% across $1.5 million to $1.7 million
of annualised wages, then stays at 4.95%. The forecast multiplies each
month's wages by 12 to choose the rate. This assumes an ungrouped SA-only
employer with a steady full-year wage run rate. Mixed SA/interstate wages
are refused; use an entity-specific calculator for apportionment, grouping
or part-year adjustments. This is not an annual reconciliation or a
statutory monthly return. See [RevenueSA](https://www.revenuesa.sa.gov.au/payrolltax/rates-and-thresholds)
and [*Payroll Tax Act 2009*, Schedule 1 clauses 2 and 5](https://www.legislation.sa.gov.au/_legislation-documents/lz/c/a/payroll-tax-act-2009/current/2009.22.auth.pdf).

```python
from pyfpa.au import PayrollAssumptions, Role, payroll_forecast
from pyfpa.au.calendar import fy_month_range

frame = payroll_forecast(
    [Role(name="Engineer", annual_salary=150000, jurisdiction="VIC")],
    fy_month_range(2027),
)
```

Skills: `fpa-au-payroll`, `fpa-au-gst-bas`, `fpa-au-xero`, `fpa-au-drivers`.

### Source reconciliation

CSV reconciliation requires finite expected controls and finite, non-negative
tolerances. Source totals, mapped totals, variances and relative variances must
also be finite. Overflow is refused before returning reconciliation evidence or
scaffolding a connector, including when every individual CSV amount is finite.
Ordinary arithmetic and the default half-cent absolute tolerance are unchanged.

### Forecast snapshots

Saved intake, corrections and experiments are revalidated before writing. Invalid
confidence, inconsistent experiment decisions, non-finite experiment metrics and
non-finite correction values are refused whilst preserving any existing destination.

Forecast predictions, score fitness, per-line errors and weights must be finite.
Snapshots are validated when created or loaded and revalidated before saving,
including after a caller changes a nested mapping or uses `model_copy`. Invalid
records are refused before a destination is opened. A scorecard build reports
`invalid_snapshot` and preserves its previous output. Selection through
`best_snapshot` and portfolio validation also report malformed saved records
rather than silently ignoring them. Older finite snapshots without recorded actual signs remain readable.

Research objectives and numeric epoch evidence must also be finite. Evaluation,
saving and promotion revalidate mutable inputs. Large finite weights retain their
relative influence without overflowing their total. Invalid saves preserve the
destination; existing holdout, hard-check and approval requirements still apply.

### Worked GST assumptions

GST-free sales and input-taxed sales both exclude output GST, but their
purchase-credit treatment can differ. Set `taxable_sales_pct` and
`creditable_purchases_pct` independently from reviewed transaction evidence.
A sales percentage does not establish a purchase-credit percentage.

These fabricated scenarios use monthly revenue of $12,000 and purchases of
$4,000, excluding GST, with the bundled 10% rate. The creditable share is an
explicit scenario assumption, with all other credit conditions assumed met.

| Scenario | Taxable sales share | Creditable purchases share | Output GST | Input GST | Net GST |
|---|---:|---:|---:|---:|---:|
| Taxable sales, fully creditable purchases | 100% | 100% | $1,200 | $400 | $800 |
| GST-free sales, fully creditable purchases | 0% | 100% | $0 | $400 | -$400 |
| Input-taxed sales, no credit entitlement | 0% | 0% | $0 | $0 | $0 |
| Mixed sales and independently reviewed purchases | 50% | 75% | $600 | $300 | $300 |

```python
import pandas as pd
from pyfpa.au.gst import GstAssumptions, bas_schedule, monthly_gst

months = pd.period_range("2026-07", periods=3, freq="M")
gst = monthly_gst(
    pd.Series(12000.0, index=months),
    pd.Series(4000.0, index=months),
    GstAssumptions(taxable_sales_pct=0.5, creditable_purchases_pct=0.75),
)
assert gst["net_gst"].tolist() == [300.0, 300.0, 300.0]
assert bas_schedule(gst["net_gst"])["amount"].tolist() == [900.0]
```

The Library's *GST / Claiming Input Tax Credits · Tax Invoices*, creditable-purpose
discussion, and *Accounting Basis · Tax Periods*, paragraph 7-000, prompted
these examples. Authority checked on 10 September 2026: [GST Act, compilation
dated 1 January 2026](https://www.legislation.gov.au/C2004A00446/2026-01-01/2026-01-01/text/original/epub/OEBPS/document_1/document_1.html),
ss 9-70, 11-5, 11-15, 11-25 and 11-30. Financial-supply exceptions and reduced
credits require separate assessment; the zero-credit example does not decide them.

On the cash basis, GST follows payment. GST on a sale belongs to the period in
which payment is received, and a GST credit to the period in which payment is
made, each only for the part paid. A business with aggregated turnover under
$10 million, among others, can choose this method. Pass the month's receipts and
its payments for all purchases, both excluding GST, to `monthly_gst` in place of
revenue and purchases: `taxable_sales_pct` and `creditable_purchases_pct` then
apply to them as they do to invoiced amounts, so do not filter the payments to
creditable purchases first. With `working_capital_from_config`, receipts are
revenue less `d_ar`; with `bad_debt_share` set, use the frame's `receipts`
column instead, because `d_ar` then also falls by the bad debts, which are
never received. Source: ATO, [Choosing an accounting method for GST](https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/accounting-for-gst-in-your-business/choosing-an-accounting-method)
(last updated 14 September 2026).

`monthly_gst` applies supplied proportions; it does not classify transactions or
attribute invoices and payments to tax periods. Reconcile cash-basis inputs before
using them. The schedule uses original BAS due dates unless
`GstAssumptions.lodgment_channel` says otherwise: `ONLINE` takes the 2-week
concession for quarters 1, 3 and 4 and `AGENT` the registered agent program date,
and `december_agent_date` takes 21 February for an eligible December monthly BAS.
`paygw_due_rule` and `payg_instalment_schedule` take the same flag with the `AGENT`
channel, so the withholding and instalments on that statement share its date.
A channel is your statement that the statement qualifies, so the default stays on
the original dates. Quarter 2 has no later date, and an agent date the ATO has not
confirmed (25 August 2027) raises. The schedule's `nominal_due_date` is the date
the rule names and `due_date` the effective date,
moved to the next business day: under Taxation Administration Act 1953 s 8AAZMB
for payment and Schedule 1 s 388-52 for lodgment, a weekend or a public holiday
for the whole of any State, the Australian Capital Territory or the Northern
Territory is not a business day, in any State. 28 February 2027 falls on a Sunday
and Monday 1 March is Labour Day throughout Western Australia, so that payment is
due on Tuesday 2 March. The holidays are the dated list in `public_holidays.yaml`,
which follows the ATO's tables. That includes Melbourne Cup, which regional areas
replace, and Christmas Eve and New Year's Eve, which are holidays for only part of
the day: a date on one moves to the ATO's 4 November, 29 December 2026 or 4 January
2027. The pack does not reproduce one row of those tables (last updated 1 July
2026, read 14 November 2026). They list WA King's Birthday on 28 September 2026,
moving to 29 September, but also give 28 September as the first business day
after 25 September. Karratha and Port Hedland held that holiday on 3 August 2026,
so it was not a public holiday for the whole of WA, and the list leaves it out:
25 September moves to the ATO's 28 September, and a date on 28 September stands,
a day before the ATO's 29 September. A day outside the list's span (1 January 2026 to 31 August 2027) raises, so a
schedule for a date before 2026 no longer computes. A refund on the due date is a forecast assumption, not a receipt
promise; `gst_weekly_flows(..., expected_receipt_on={period_label: date})` banks it on the date you expect instead. A period ending after `reviewed_until` in `gst_bas.yaml` (30 June 2027)
raises until the dates are re-checked. Explicit rate overrides must be finite and
non-negative. Zero remains available for scenario modelling; it does not establish
a GST exemption.

`fbt_schedule` and `fbt_weekly_flows` put the FBT left to pay with the return into
the 13-week forecast. A negative amount, a refund, stays in the schedule but reaches
the forecast only on an `expected_receipt_on` date from the caller, because a refund
depends on lodgment, ATO processing and offsets. The tax falls due on 21 May after the year ending 31 March, or
generally 25 June when a tax agent lodges electronically and has the employer on
its FBT client list by 21 May (`LodgmentChannel.AGENT`), moved to the next business
day. A year after `reviewed_until` in `fbt.yaml` (31 March 2027) raises. FBT
instalments sit on activity statements, so they take the BAS dates.

`payment_plan_estimate` shows what paying an ATO debt by instalments would cost, and
`payment_plan_weekly_flows` puts those payments in a 13-week scenario in place of
the tax's own flow. The base case keeps the statutory dates, because a plan the ATO
hasn't accepted must not be assumed. It is an estimate, not an ATO figure, and it
implies no ATO approval: the Commissioner decides whether to permit instalments, and an arrangement
does not change the due date (Taxation Administration Act 1953 Schedule 1 s 255-15).
GIC runs from the effective due date, on each day's closing balance, at the rates in
`gic.yaml`, each divided by the days in the calendar year. Each schedule row stands
at the end of its day, with that day's GIC included. A due date before that
table starts (1 January 2026) or a date past its `reviewed_until` (31 December 2026,
the end of the last quarter the ATO has published) raises, so a plan that runs longer
waits for the next rate: say the cost can't be estimated yet, and why. It does not cover super
guarantee charge debts or the remission on an interest-free plan.

### Comparing external calculators and policy models

Record the comparator URL or source revision, retrieval date, selected period,
inputs and exclusions. Match the component being checked to an implemented
calculation; a published parameter or advertised program is not evidence that
the model calculates it. Check the parameter's effective date and review horizon,
including whether a calendar-year label has been mapped to the Australian
financial year. Reperform threshold and effective-date boundaries against the
primary source before relying on agreement between models.

Compare a baseline and an alternative with the same inputs except for the
intended change. Reconcile the difference by component, and keep employer cost,
employee tax, household benefits, cash timing and accounting expense distinct.
For super projections, distinguish gross contributions from net investment
cashflows and nominal outcomes from inflation-adjusted outcomes. These are
different modelling contracts; this pack does not supply a personal tax or
tax-benefit microsimulation engine.

[CheckTax's methodology](https://checktax.com.au/methodology/) prompted clearer
component workings and scope disclosures. [PolicyEngine Australia's developer
guide](https://policyengine.github.io/policyengine-au/developer-guide.html)
prompted the parameter, assessment-unit and scenario checks. Both were inspected
on 17 October 2026 as secondary design references. Their code, tables and prose
were not imported; statutory values still require the relevant primary sources.

Worked examples on this fork:

- [`examples/lumbridge-services/`](../examples/lumbridge-services/) - synthetic
  NSW maintenance business: dated receipts, PAYG, super and GST cash, monthly
  commentary and a verified Excel receipt-delay scenario with OSRS references.

- [`examples/harbour-light/`](../examples/harbour-light/) - synthetic VIC
  wholesaler: Xero mapping, statutory payroll, quarterly BAS into 13-week cash,
  verified Excel.
- [`examples/arb/`](../examples/arb/) - ARB Corporation (ASX: ARB) from the FY2025
  Appendix 4E. Annual public proof, not a GST model.

### Cross-client reuse in an Australian practice

The portfolio loop can carry a prior or a generated skill from one client's
workspace into another's. That is a confidentiality decision before it is a
modelling one, so `pyfpa/portfolio` refuses to make it: a promotion needs a
`PromotionApproval` recorded against the exact candidate, with the purpose, the
contributing workspaces, the authorisation it rests on and a confidentiality
review. See [SECURITY.md](../SECURITY.md) for the mechanics and
[`skills/fpa-portfolio-learn`](../skills/fpa-portfolio-learn/SKILL.md) for the
workflow.

Two points worth stating plainly for practice use:

- "Nothing leaves your machine" describes network egress. It does not permit
  moving one client's information into another client's engagement file. Weigh
  the engagement terms, the confidentiality requirements in the APES 110 Code of
  Ethics and, for personal information, the Australian Privacy Principles.
- The recorded approval is an acknowledgement by the practitioner. It is not
  authentication, it is not legal proof of client consent, and it is not a
  substitute for advice on your obligations. The automated screen for ABNs,
  TFNs, contact details, bank details and client names assists that review and
  proves nothing.

Proposed upstream in
[JeffBrines/openfpa#14](https://github.com/JeffBrines/openfpa/issues/14).
This fork is not a claim to be upstream.

## Review model assumptions

Use `openfpa model-assumptions <workspace> --config <config.yaml>` to inspect
effective model inputs as JSON. Add `--previous-config <previous.yaml>` to show
changed, added and removed assumptions. The workspace must already be initialised.

Each input shows whether it was supplied or defaulted. An explicit zero remains
distinct from an omitted zero. Nested objects, line lists and tax payment maps also
have their own row, so an explicit empty object, an emptied list or a change from
null to an object is reported. Named channel, expense and debt lines stay aligned
when their order changes, and tax payment months are compared one by one. The
report describes receipts, inventory and income tax methods and flags entity,
horizon, start-month or method differences before treating the configurations as
comparable. Each file is read once, and its SHA-256 digest identifies the bytes
that were parsed.

Supplied inputs still need source evidence and approval. This command presents
configuration choices; it performs no forecast or statutory calculation. Review
the reported defaults and changed assumptions before running a scenario.
