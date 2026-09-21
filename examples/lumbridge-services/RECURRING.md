# Repeating the Lumbridge cash forecast

From the repository root:

```powershell
uv run --locked --extra dev python examples/lumbridge-services/models/generated/recurring.py --output path/to/new-run
```

The run writes 3 separate forecast records using the existing snapshot API: the original forecast, its closed-period score and the revised forecast. It refuses an existing output directory. The original bytes remain unchanged. This is a fabricated workflow demonstration, not a live forecast evaluation or promotion of a new champion.

The hypothesis is testable: replacing only the closed month's cash with independently reconciled actuals should preserve future unpaid items exactly once, while retaining the old forecast error. The example tests a partial receipt followed by a delay.

| October evidence | AUD |
| --- | ---: |
| Opening bank | 30,000 |
| OPEN-V partial receipt | 10,000 |
| OPEN-F receipt | 22,000 |
| Payments | (63,960) |
| Closing bank | (1,960) |
| Closing receivables control | 100,000 |

The prior forecast expected $66,000 receipts. The $34,000 miss remains in `errors.csv`. OPEN-V's outstanding $34,000 is expected on 28 November; the revised November closing cash is $49,680. The paid portion is removed from future cash. Expected dates, due dates, disputed amounts and supporting references stay separate from observed bank receipts. A disputed amount remains an outstanding ledger balance; its explicit forecast receipt is a planning assumption.

Sources are `refresh-actuals.csv`, `refresh-controls.json` and `receipt-assumptions.csv` under `data/`, alongside the original invoice and payment plans. Bank transaction IDs are unique, source IDs must match and cash direction/category must agree. The bank and receivables controls are independent supplied balances. Missing evidence, over-allocation and unresolved past-due payment plans stop the refresh. Source SHA-256 values are recorded in `review.json`.

The record also binds the 6 base forecast inputs, including the balance sheet,
invoices and payment plan. A changed base input during calculation stops the run.

The fixed example runs to December. It does not extend the sales plan automatically, infer missing transactions, change profit assumptions or claim a banking facility for a negative balance. The October negative balance identifies funding needed. Completion of a synthetic reconciliation does not establish actual forecast performance.

## Invoice book and operating bridge

`models/generated/invoice_cash.py` prepares opening-book cash from signed invoice and credit balances. Its test combines a $10,000 invoice, $4,000 settlement and a $500 credit: the ledger book is $5,500 and the forecast receives $5,500 once. Credit allocation requires an explicit invoice link. Due date and expected date are distinct. Add this opening-book cash once, separately from new projected sales.

`models/generated/operating_variance.py` demonstrates one supported decomposition. Jobs rise from 200 to 220 and price rises from $100 to $110. Volume contributes $2,000 and price contributes $2,200. Ledger revenue increases by $4,150, leaving an unexplained -$50 residual. The interaction belongs to price because price is measured at current volume. No inferred cause is assigned to the residual.

Run their independent arithmetic and adverse-input checks with:

```powershell
uv run --locked --extra dev pytest -q tests/test_utility_examples.py
```

Print both fabricated workpapers as JSON with:

```powershell
uv run --locked --extra dev python examples/lumbridge-services/models/generated/utility_demo.py
```
