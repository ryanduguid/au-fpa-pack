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

On 11 September 2026, Ryan approved publishing the prepared example through
a pull request and merging after checks pass: "ok merge". Releases and
outreach remain outside this approval.
