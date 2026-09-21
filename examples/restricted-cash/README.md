# Restricted cash planning

Run `uv run --locked --extra dev python examples/restricted-cash/restricted_cash.py` from the repository root. The JSON case is wholly fabricated and all amounts are AUD.

Opening cash is $100,000, including $80,000 assigned to 2 supplied funding restrictions. General receipts add $5,000. Programme payments use $10,000 and general payments use $12,000. Closing bank cash is $83,000, the remaining restricted allocation is $70,000, and cash available for general use under these assumptions is $13,000.

The same bank account can hold both allocations. Fund names never determine restrictions. Each fund needs a restriction reference, an allocation reference and an explicit renewal date. Renewal is displayed as planning evidence; no renewal receipt is invented. Every supplied payment is counted once. Allocations beyond opening cash or spend beyond the supplied fund allocation fail.

A negative available balance is shown as SHORTFALL. This is cash planning, not an income-recognition, liability or grant-acquittal conclusion. Change the reviewed JSON inputs to examine another case; the calculation remains in the generated example, outside the shared kernel.
