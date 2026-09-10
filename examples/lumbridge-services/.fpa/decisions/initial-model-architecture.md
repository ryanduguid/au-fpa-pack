# Lumbridge model architecture

**Status:** Approved for implementation of the proposed synthetic worked case.

On 10 September 2026, Ryan approved the proposed NSW business example,
verified workbook and independent trial preparation: "OK do that for me
please, make OSRS references". The business name, fixtures and financial
assumptions are author-created details within that scope. They are not
facts supplied by Ryan or evidence of professional accounting sign-off.

## Model

Use one company module at models/generated/lumbridge.py. Reuse the Xero
parser, NSW payroll kernel, cash13 engine, Excel toolkit and formula
verifier. Keep the kernel unchanged. A dated cash schedule is needed to
show the receipt-delay effect that a flat monthly working-capital ratio
would hide. No live connector or new dependency is needed.

The source registry and exact account mappings identify the six fabricated
files and two bundled payroll rate tables. The business profile records
the synthetic assumptions and planning question.

## Acceptance

The base and delayed cases must preserve revenue and pre-tax profit while
changing cash and receivables. Direct cash must reconcile to profit after
non-cash expenses, receivables, GST, loan principal and the tax instalment.
The workbook must calculate the same results, including dates and chart
values, and restore the base case after an input-edit trial.

Prepare a management briefing, trial guide and separate answer key. An
independent accountant must still complete the trial; native Excel and
Python checks do not establish forecast accuracy or client suitability.

On 11 September 2026 (Australia/Sydney), Ryan approved publishing the prepared example through
a pull request and merging after checks pass: "ok merge". Releases and
outreach remain outside this approval.

## Evidence for this initial example

The CFO question is whether a profitable quarter can still need short-term
funding. The hypothesis is that delaying OPEN-V by 45 days changes cash and
receivables while preserving service revenue and pre-tax profit.

The source registry identifies the six fabricated inputs and two bundled
rate tables. September 2026 supplies the opening balances and repeated
monthly P&L; invoices and payments cover the October to December forecast
and later debtor collections. The README records each financial assumption.
This is a new example, with no prior accepted company model or actual holdout.

The on-time and delayed cases both produce $180,000 quarterly revenue and
$35,957.55 profit before income tax. Minimum daily cash changes from $16,800
to ($25,160), and October closing cash changes from $32,040 to ($11,960).
December cash returns to $67,320 in both cases. All three monthly cash
reconciliation differences are zero. Tests in tests/test_lumbridge.py check
these results, delayed receipts beyond the horizon, source rejection and
all 21 monthly workbook lines. Native Excel also checked the 0, 45 and
100-day controls, chart values, invalid inputs and save/reopen behaviour.

The changed files comprise this example's data, model, memory and trial
documents, its regression tests, and links in the repository documentation.
The existing formula verifier needs formulas 1.3.0 or later for SUMIFS, so
the development dependency floor and lock metadata include that requirement.
Ryan's acceptance authorises this synthetic demonstration and its merge;
an independent accountant trial and professional sign-off remain pending.
