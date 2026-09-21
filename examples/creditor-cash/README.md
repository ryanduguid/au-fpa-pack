# Supplier invoices to planned cash

Run from the au-fpa-pack checkout:

```powershell
uv run --locked python examples/creditor-cash/supplier_cash.py
```

The canonical JSON example keeps a $6,000 supplier invoice, $2,000 settlement and $500 credit separate. The $3,500 net balance agrees to the supplied payables control and is scheduled as $1,000 plus $2,500. No payment is executed.

Every invoice needs a supplier ID, original amount, settled amount, outstanding amount, due date, expected date and evidence. Positive invoices and negative credits follow the existing invoice-book calculation. Settled includes applied credits where the ledger has already allocated them; the supplied example leaves its credit unapplied in the ledger and links it explicitly for cash planning. Never apply a credit twice.

Payment plans require unique IDs, invoice links, future dates, positive amounts, evidence and an explicit approval input. They must cover each net payable exactly. Cross-supplier credit allocations, overpayments, missing plans, unapproved plans and mismatched controls stop the calculation. An unallocated credit needs its own allocation or refund decision.

This version supports one entity, AUD and an opening invoice book. It does not claim compatibility with a Xero, MYOB or other vendor export. New forecast purchases remain separate from these opening liabilities. Preserve the original evidence when changing a payment plan.
