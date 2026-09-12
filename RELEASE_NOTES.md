# v0.1.1

- Publishes the attested wheel and source distribution to PyPI as `au-fpa-pack` through trusted publishing.
- No functional change since v0.1.0.

# v0.1.0

First release of the Australian FP&A pack for openfpa: 30 June financial years,
Xero AU mapping, GST and BAS cash timing, and payroll on-cost assumptions.

- `openfpa`, a JSON-emitting CLI for company workspace intake, source lineage,
  mappings, reconciliation, connector scaffolding, corrections, scorecards,
  context packs and verified Excel export.
- 17 skills under `skills/`, plus the `.claude-plugin/plugin.json` manifest that
  declares the repository as the `openfpa` plugin.
- Five worked examples: Lumbridge Services, Harbour Light and Ridgeline Chair
  Co. from synthetic records, ARB Corporation from its FY2025 Appendix 4E, and
  Fox Factory Holding Corp. from public SEC filings.
- Source-only. The distribution is `au-fpa-pack` and the import is `pyfpa`; it
  is not published to PyPI.
- Tested on Python 3.11, 3.12 and 3.13.
