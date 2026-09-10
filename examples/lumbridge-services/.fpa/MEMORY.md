# Lumbridge Services FP&A Memory

- `intake.md`: onboarding facts, evidence, confidence, and open questions
- `business-profile.md`: synthetic business assumptions derived from intake
- `sources/`: source inventory and data provenance
- `mappings/`: account and operational-data mappings
- `corrections/`: typed human corrections recorded by fpa-capture-correction, applied via pyfpa.apply_corrections
- `forecasts/`: immutable forecast snapshots and their scores, written by pyfpa.backtest
- `scorecard.md`: rendered forecast track record across all scored periods
- `learnings.md`: accepted model changes with evidence and backtest delta
- `experiments/`: model hypotheses, evidence, checks, and ratification decisions
- `decisions/`: material CFO decisions and approvals
- `models/`: champion/challenger history and generated entrypoints
- `research/`: immutable autonomous research epochs

This example uses local fabricated files and has no connector. No forecast
has been scored against actual results, and no independent trial is recorded.
