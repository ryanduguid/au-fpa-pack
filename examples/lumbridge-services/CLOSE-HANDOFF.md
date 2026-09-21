# Use the forecast opening balances in a close review

Generate a new input directory outside both repositories:

```powershell
python models/generated/close_handoff.py --output /local/demo/close-inputs
```

From the Monthly Close Controls component in Accounting Review Pipeline:

```powershell
uv run --locked close-control review --current /local/demo/close-inputs/current.csv --prior /local/demo/close-inputs/prior.csv --mapping /local/demo/close-inputs/mapping.csv --subledger /local/demo/close-inputs/subledger.csv --output /local/demo/close-pack
uv run --locked close-control view --pack-dir /local/demo/close-pack
```

The current trial balance uses the forecast's September balance sheet. Cash is
30000.00; the two opening invoices total 66000.00; payables of 13200.00 match
the October materials payment assumption. The handoff records source hashes.
Run [the recurring forecast](RECURRING.md) against those same sources to follow
opening cash through October actuals and the revised receipt schedule.

The August balance sheet is an explicitly constructed prior for this example.
It is not an observed export. The receivable tie uses invoice detail; the payable
tie uses an asserted opening balance and planned settlement, not independent
supplier statements. Retain these limits beside the close pack. The engine does not
approve accounting, and a close result does not approve the forecast assumptions.

Account IDs use `BS-` plus the source code because code 800 has different
meanings in the supplied balance sheet and profit and loss. The separate source
code remains text. No production component imports another component.

This bounded route reuses Lumbridge Services. It does not replace the pipeline's
Fabricated Firm proposal, migrate its entities or claim full ledger, payroll and
Power BI consistency across that proposed group.
