# Lumbridge trial: leave Tutorial Island without help

This is an independent usability and accounting review of a synthetic case.
No OSRS knowledge is needed. Varrock and Falador are the two service lines;
the Grand Exchange reference means customer collections.

Use a fresh copy of `lumbridge.xlsx`, its source files and this guide.
Keep the answer key closed until you have recorded your results.
You do not need a Xero login, client data, macros or an AI agent.

## First run

If you received the workbook, open it in desktop Excel and enable automatic
calculation. Do not enable macros or external links. If you are reproducing
from source, follow the two commands in the example README first.

Record your Excel version, operating system, start time and whether you
used the supplied workbook or rebuilt it. Record any help you need.

1. Find the October to December revenue, profit before income tax and
   December closing cash. Identify which amounts are forecasts.
2. Find the lowest daily closing cash balance and the date it occurs.
   Explain why looking only at December cash could miss a funding problem.
3. Find invoice OPEN-V in `data/invoices.csv`. Trace its amount and receipt
   date into the workbook.
4. Change the receipt-delay control from 0 to 45 calendar days. Record the
   lowest daily balance, first negative date and October closing cash.
   State whether profit changed and explain the difference.
5. Identify the outstanding December GST, supplier and PAYG withholding
   balances. Explain why gross wages and net employee bank payments differ.
6. Check the profit-to-cash reconciliation for all three months. Explain
   how non-cash leave, customer debtors and tax payments enter the bridge.
7. Recommend one action for the owner before approving discretionary
   equipment spending. A dragon pickaxe is the fictional equipment upgrade.
8. Restore the delay to zero, save your trial copy, close and reopen it.
   Confirm the original results return.

The workbook's only supported scenario control is `Assumptions!B2`.
Blank cells in January's closing-cash column are intentional: future
invoice dates support receivables, but January payments are outside the forecast.
The README states the model's limits and source assumptions.

## Record your findings

| Item | Reviewer entry |
| --- | --- |
| Reviewer and date | |
| Excel version and operating system | |
| Started / finished | |
| Used supplied workbook or rebuilt | |
| Steps completed without help | |
| Help requested and exact obstacle | |
| Base quarterly revenue / pre-tax profit | |
| Base December cash / lowest daily cash and date | |
| Late-case lowest daily cash and date / first negative date | |
| Late-case October cash / change in profit | |
| December GST / supplier / PAYG balances | |
| Reconciliation differences | |
| Owner action and supporting evidence | |
| Incorrect or unsupported assumption found | |
| Save and reopen result | |

Use the answer key only after completing this table. Record differences
against the key instead of replacing your original answers.

The trial passes only when the reviewer reproduces the figures, explains
the profit/cash difference and identifies the liabilities and owner action
without unrecorded help. Report elapsed time as an observation; it is not
evidence of time saved against another workflow.

Return the completed table and any issues to Ryan through a channel he
chooses. Nothing in this guide submits a report automatically.
