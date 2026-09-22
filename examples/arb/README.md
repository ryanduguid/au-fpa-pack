# ARB Corporation (ASX: ARB)

Public-company proof for the Australian pack. Vehicle 4WD aftermarket, 30 June
year, AUD, franked, Victorian parent. Source-traced to the FY2025 Appendix 4E.

```bash
python3 examples/arb/run_arb.py --output-dir <dir>   # replay into a scratch directory
python3 examples/arb/run_arb.py --replace-epochs     # regenerate the committed outputs
```

`run_arb.py` saves a research epoch per retrospective challenger and refuses to
overwrite one that already exists, which is the guard against losing research
history. This example ships its two epochs, so replaying over them needs
`--output-dir` or, to regenerate the committed files, `--replace-epochs`.

Every figure traces to [`data/SOURCES.md`](data/SOURCES.md).

## Four phases

**Phase A** reproduces FY2025 operating mechanics from actual drivers (sales
mix, materials as COGS, WC days, D&A, PPE capex). Gross profit is constructed.
This is arithmetic, not a forecast.

**Phase B** compares scenarios against FY2025 retrospectively. Both challengers
use FY2025 realised export growth of 16.4%, so neither passes the independent
holdout check. Both are discarded for promotion, including the export-led
scenario whose revenue fits within 0.1%. A separate period with inputs fixed
in advance is required to test forecasting accuracy.

**Phase C** forecasts FY2026 to FY2027 from the August 2025 4E view.

**Phase D** is a labelled Thai Baht / US-tariff sensitivity (+150bps COGS). It is
not a kernel FX engine.

## Where the engine strains

1. PDF transcription, not XBRL.
2. No channel EBITDA in the filing: allocated from consolidated EBIT + D&A.
3. Trade receivables used as AR, not the broader receivables line.
4. No FY2023 balance sheet in this 4E, so Phase A is FY2025 only.
5. Franking, associates (ORW), and acquisitions are outside the engine.
6. GST/BAS belongs to Harbour Light, not this annual public proof.
