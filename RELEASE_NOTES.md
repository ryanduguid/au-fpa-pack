# Unreleased

- Cross-client promotion in `pyfpa/portfolio` is default-deny. `promote_prior` and
  `promote_skill` refuse unless a practitioner has recorded a `PromotionApproval` for
  that exact candidate's sha256 digest, listing the purpose, the contributing
  workspaces, the authorisation reference and a confidentiality review.
  `record_promotion_approval` is the only writer of an approval and refuses to
  overwrite one. The approval is an acknowledgement, not authentication and not legal
  proof of client consent.
- `validate_prior` accepts the candidate it validates and stamps its digest into
  `ValidationResult`; a result without the candidate's digest cannot support a
  promotion. `screen_candidate` reports ABN and TFN shaped numbers, email addresses,
  Australian phone numbers, BSB and account patterns, narrative dollar amounts and the
  contributing clients' business names, and any finding blocks promotion until the
  recorded review lists it.
- `promote_skill` copies only the files the approval lists in `allowed_files`. The gate
  counts distinct clients by normalised business-profile heading, ignoring case,
  punctuation, bracketed qualifiers and entity suffixes, and treats a workspace with no
  heading as establishing no client. Promoting across two workspaces that normalise to
  one name takes both workspace ids in the approval's `aliases_acknowledged` and review
  notes saying why they are separate.
- Shared library records now carry opaque workspace ids and the approval digest instead
  of client paths, with the path map in `<library>/provenance/workspaces.yaml`.
  `seed_from_library` takes the receiving `company_root` and `seeded_at`, records the
  seed in that workspace's `.fpa/library-seeds.yaml` and in the library's seed index,
  and the new `withdraw_prior` removes a prior and reports the workspaces it seeded
  without touching anything inside them.
- Documentation states that "nothing leaves your machine" is about network egress and
  does not by itself permit moving one client's information into another client's work.

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
