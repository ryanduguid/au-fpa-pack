# Unreleased

Added:

- `runway_summary` names every week whose ending cash is below zero in `negative_weeks`, and with a facility every week headroom is below the buffer in `headroom_breach_weeks`. The briefing from `to_briefing_md` adds a 'Weeks below zero' line, so a one-week dip reads apart from a month below zero. In the Lumbridge example a 45-day late receipt leaves weeks 4, 5 and 6 below zero. `compare_scenarios` rows and the Ridgeline decision pack carry the same lists, and the decision pack's metric dictionary declares `negative_weeks`.
- `gst_weekly_flows(..., expected_receipt_on={period_label: date})` banks a BAS refund on the date the caller expects, as `fbt_weekly_flows` does for FBT. Only refund rows move. Without it a refund still lands on the statement's due date, a forecast assumption; a label with no refund in the schedule is refused.
- `collection_profile_from_history(invoices, receipts)` measures a `collection_profile` from fully paid invoices: the share
  of the money invoiced in a month that arrived that month and in each month after, counting part payments when they
  arrived. It refuses an invoice not paid to the cent, a receipt dated before its invoice and a receipt for an unknown
  invoice, and text dates that are not ISO. Open invoices are the slow payers, so use a cohort issued long enough
  ago to have fully paid. A stated profile still works as before; nothing derives one unless the caller does.

Changed:

- The Claude Code plugin is now named `au-fpa-pack`, not `openfpa`, with Ryan Duguid as its author, and the
  repository is its own marketplace: `/plugin marketplace add ryanduguid/au-fpa-pack`, then
  `/plugin install au-fpa-pack@au-fpa-pack`. Uninstall a plugin installed under the old name before
  installing this one.

Fixed:

- An eligible business's December monthly BAS is due 21 February, and that date now reaches the PAYG withholding and instalments on it, not only the GST. `paygw_due_rule` and `payg_instalment_schedule` take `december_agent_date=True` with the `AGENT` channel, as `GstAssumptions` does; before, withholding and instalments on that statement stayed on 21 January. Source: ATO, 'Activity statements', registered agent lodgment program (last updated 1 July 2026, read 13 November 2026): the December business activity statement is not due for lodgment and payment until 21 February for business clients with up to $10 million annual turnover who report GST monthly and lodge electronically; businesses registered for deferred GST are not eligible. The flag is the caller's statement that the business meets those conditions, is not registered for deferred GST (the importer scheme, which the code cannot see) and that the statement is not one with only a monthly PAYG withholding cycle. The code refuses the flag for a deferred BAS payer, which lodges no monthly GST, and with a channel other than `AGENT`. It does not move an instalment whose notice came after the quarter ended, which stays on its s 45-112(3) date.

# v0.5.0

Breaking for code and workbooks written against 0.4.0:

- Versions made available from 4 November 2026 are licensed under the Ryan Duguid Public Attribution Licence 1.0: the FSL-1.1-ALv2 text unchanged, plus a condition that anyone making a copy, port or derivative available outside their organisation credits Ryan Duguid publicly with a link to this repository (#278). Internal use is exempt, and 0.4.0 keeps its FSL-1.1-ALv2 terms.
- The Lumbridge workbook's status cell moves from `Model!B26` to `Model!B27`, below a fourth check, `check_receivables_open_invoices`, which compares Receivables with the receipts for invoices raised by month end and received after it (#269).

Added:

- An optional `Cash13Config.facility_limit` adds a weekly `headroom` column to the 13-week cash forecast, and `runway_summary(..., headroom_buffer)` reports the first week headroom falls below the buffer (#251).

- `openfpa model-assumptions <workspace> --config <config.yaml> [--previous-config <previous.yaml>]` reports each effective model input as JSON with whether it was supplied or defaulted, the receipts, inventory and income tax methods, and, against a previous configuration, changed, added and removed inputs with entity, horizon, start-month and method differences. Objects, line lists and tax payment maps have their own rows; named channel, expense and debt lines stay aligned when reordered, payment months are compared individually, and SHA-256 digests identify the exact bytes parsed. It runs no forecast.
- `pyfpa.config.loader.config_from_bytes` validates an `EntityConfig` from the exact bytes of a YAML file; `load_config` now uses it, with the same UTF-8 and newline handling.
- 13-week cash flows can recur `monthly` or `quarterly`. Such a flow takes an `anchor_date` and recurs every 1 or 3 months from it on its day of month, or on the month's last day when that is earlier, so the 31st falls on 28 or 29 February. `Cash13Config.window_start`, the first day of week 1, places each date in the week that contains it, as `gst_weekly_flows` does; dates before week 1, outside `start_week` to `end_week` or past the horizon are dropped. A monthly or quarterly flow without an `anchor_date`, an `anchor_date` on any other recurrence and a monthly or quarterly flow in a config without `window_start` are refused. A scenario delay moves the `anchor_date` by the same number of weeks. `expand_flow` takes the window start as an optional third argument.

- Australian due dates by lodgment channel: `LodgmentChannel` on `GstAssumptions`, `payg_instalment_schedule` and `paygw_due_rule` takes the 2-week online concession or the registered agent program date, and `december_agent_date` the 21 February date for an eligible December monthly BAS. The default stays on the original dates, and an agent date the ATO has not confirmed is refused. `fbt_due_date`, `fbt_schedule` and `fbt_weekly_flows` add FBT return and payment dates, from the new `fbt.yaml`; an FBT refund enters the forecast only on an `expected_receipt_on` date from the caller.
- `payment_plan_estimate` and `payment_plan_weekly_flows` show what paying an ATO debt by instalments would cost, with GIC worked daily from the effective due date using the dated `gic.yaml`. The result is labelled an estimate and implies no ATO approval, and a plan needing a day outside `gic.yaml` is refused. A plan is a scenario only: the base case keeps statutory dates. `fpa-cash-runway` and `fpa-cfo-judgment` now carry a guardrail against presenting deferred tax, super or payroll as a source of cash without its consequences.

Changed:

- Australian BAS, PAYG withholding and PAYG instalment due dates now move past a public holiday for the whole of any State, the ACT or the NT, as Taxation Administration Act 1953 s 8AAZMB and Schedule 1 s 388-52 require, and not only past a weekend. The December 2026 quarter is due on Tuesday 2 March 2027, not Monday 1 March, which is WA Labour Day. Holidays come from the dated `public_holidays.yaml`, and a date before 1 January 2026 or after 31 August 2027 is refused. The list leaves out WA King's Birthday, Melbourne Cup, Christmas Eve and New Year's Eve, which the ATO's table lists, because none is a day that is a public holiday for the whole of a State, so a date on one falls before the ATO's. `bas_schedule` gains a `nominal_due_date` column beside the effective `due_date`.
- `.claude-plugin/plugin.json` now carries the package's version, 0.4.0, instead of 0.1.0, and a test keeps the 2 equal.
- A `proposed` or `promoted` `ResearchEpoch` now needs a holdout period that does not overlap its training periods. Saved epochs that lack one no longer load until their periods are recorded or their status changes.

Fixed:

- `fy_year`, `fy_label`, `fy_quarter_label` and `fy_half_label` accept text only as `YYYY-MM` or `YYYY-MM-DD`, as `format_au_date` already did, because pandas read '1/10/2026' and '2026' as January 2026. Other text they used to parse, such as the date-times '2026-10-01T00:00:00' and '2026-10-01 00:00:00', the quarter '2026Q4' and 'Oct 2026', is now an error; pass a `Timestamp` or `Period` instead.
- Depreciation evidence must reconcile before its charge is spread into a forecast (#293). `load_evidence` refuses raw and normalised movement figures that disagree; evidence that reports additions without opening, closing or charge, has a negative addition or charge, or whose opening plus additions less charge misses closing by any amount is refused; and `straight_line_schedule` refuses a monthly charge it cannot hold as whole cents. Evidence 0.4.0 accepted can now be refused.

# v0.4.0

Breaking for code and configurations written against 0.3.0:

- au-fpa-pack is now licensed under FSL-1.1-ALv2 (Functional Source License, with Apache-2.0 as the future licence) instead of MIT (#235). openfpa's MIT notice moves from LICENSE to NOTICE, and wheels and source distributions include both. Releases up to and including 0.3.0 remain MIT.
- `load_config` refuses a YAML file that repeats a key in one mapping, including a repeated `<<` merge key, before validating it (#203). PyYAML used to keep the last value. The forecast builders and `model_to_excel` validate the configuration's current state again, so an `EntityConfig` edited into an invalid state after loading raises `ValueError` instead of being modelled or exported.
- The 13-week cash configuration refuses NaN and infinite `opening_cash` and flow `amount` values, as the monthly schemas already did, and correction slugs made only of dots are refused before any write (#201).
- `model-export` refuses an output path that does not end in `.xlsx` (#210), and `forecast_to_excel` refuses any destination that is not `.xlsx` (#214).
- `holdout_backtest` refuses actuals whose periods are not unique months and a forecast that does not cover the held-out months, and `snapshot_forecast` refuses a forecast whose index differs from the configured months (#238). Both used to score or save misaligned data.
- Reconciliation, `score_forecast`, `recover_actuals`, snapshot selection and portfolio validation and mining refuse non-finite or overflowed arithmetic instead of carrying `nan` or `inf` into a score, prior or recovered actual (#241). `score_forecast` refuses a positive weight that normalises to 0, `best_snapshot` ignores a snapshot whose fitness is not finite and non-negative, and `validate_prior` skips baselines with unusable stored evidence or weights. Integer and `float32` totals are now summed exactly.
- `reconcile` and `reconcile_account_table` divide the variance by the absolute actual, so `variance_pct` on a negative line has the same sign as the variance (#219). A loss of 80 modelled as 100 used to read +25% although the model was 20 below. A forecast score's per-line errors change sign on negative lines in the same way; tolerance results and fitness are unchanged.

Added:

- `verify_workbook(..., inputs={"Sheet!A1": value})` recalculates the workbook with input cells replaced, as a user changing them in Excel would, and refuses a key that is not an existing value cell (#237). The Lumbridge test now changes `Assumptions!B2` in one exported workbook to 0, 1, 44, 45, 46 and 120 and checks both `Model` and `Cash 13 weeks` against the engine.
- `docs/australian-pack.md` and the GST/BAS and payroll skills explain how to compare this pack's results with external calculators and policy models, so a match between tools is not taken as evidence (#221).

Fixed:

- `model_to_excel` and `forecast_to_excel` write each workbook beside its destination and replace the destination only after the file is closed, so a failed save or replacement keeps the previous report (#214). `model_to_excel` also reopens the staged workbook read-only first, and `model-export` no longer leaves the finished workbook open.
- The model workbook's receivables, payables and inventory formulas group the days ratio, keeping large finite working-capital values in step with the engine (#203).
- `recover_actuals` recovers negative actuals. Since #219, `score_forecast` stores each line's error as `(predicted - actual) / |actual|`, but `recover_actuals` still inverted it as `predicted / (1 + error)`, so a loss of 100 forecast as 80 came back as a loss of 66.67 and portfolio prior validation rescored its folds against that. `ScoreResult.actual_signs` now records the sign of each scored actual, and `recover_actuals` inverts by it. A score without it, such as one written by 0.3.0, is recovered only where the 0.3.0 signed reading and the `|actual|` reading give the same actual; any other line raises `ValueError` naming it, and `validate_prior` leaves that client out of its folds. Rescore such a snapshot to record its signs. A line whose forecast is too small relative to its actual for the stored error to fix it (`|1 + sign * error|` below `1e-8`) also raises `ValueError` rather than returning an imprecise actual.

# v0.3.0

Breaking for code and configurations written against 0.2.0:

- Requires Python 3.14 or later (#172). 0.2.0 remains the last release for Python 3.12 and 3.13.
- `fetch_rba_series` picks each month's value by observation date instead of file order, keeping the latest date in the month, and raises `ValueError` when one date carries two different values (#175). Identical duplicate dates are still accepted.
- Forecast evidence extraction refuses incomplete selected evidence and non-finite totals, and `score_forecast` requires a finite, positive weight total (#182). Missing values used to disappear during reduction, and two weights of 1e308 could erase nonzero errors. A refused portfolio candidate now fails its fold while the other folds continue.

Added:

- `XeroReport.account_identities()` and `pyfpa.memory.reimport.compare_reimport()` compare account identities, mappings and source metadata across Xero re-imports (#179). Account codes keep leading zeros, and the comparison reports additions, removals, renames, tracking changes, mapping changes and coverage gaps without changing amounts or company memory.

Fixed:

- `write_onboarding_outputs` refuses a linked `decisions` folder that leads out of the workspace, and replaces files through a sibling temporary file, so a failed overwrite no longer truncates an existing business profile (#173).
- A forecast snapshot whose assumptions cannot be written no longer creates an empty file or erases an existing snapshot during an explicit overwrite (#177).

# v0.2.0

Breaking for code and configurations written against 0.1.2:

- Requires Python 3.12 or later, with pandas 3.0.5, PyYAML 6.0.3 and openpyxl 3.1.5 as the dependency floors (#159). 0.1.2 remains the last release for Python 3.11.
- The days-based working-capital model refuses a configuration that implies negative customer receipts, purchases or supplier payments, naming the month, the flow and the amount, and `model-export` writes no workbook for it. A DSO of 60 days with revenue tripling in a month used to report a smaller operating cash flow instead (#139). Use a collection profile or the replenishment basis below where the days model cannot follow the business.
- Forecast configuration rejects NaN and infinity (#135), a receipt shift rejects non-finite amounts and keeps cash unchanged when its source and destination month match (#136), and seasonality that overflows its total or growth that overflows raises `ValueError` instead of erasing revenue or producing infinite cash (#137).
- Removed public names nothing read: `GstAssumptions.agent_lodgment` (a YAML `agent_lodgment` key is now ignored), `XeroReport.gst_inclusive`, `XeroReport.unmapped_tracking` and the `connector-validate --timeout` flag (#134).

Added:

- `review_forecast` structural controls over a monthly forecast frame (#140), an opt-in income-year tax provision (#141), receivables collected by a stated profile (#142) with bad debts and later write-offs (#150), and an opt-in replenishment basis for inventory (#151).
- `pyfpa.au.payroll_settlement` settles payroll costs on their own dates (#143), with due-date rules for PAYG withholding (#144), the super guarantee under Payday Super and the quarterly regime (#145) and monthly payroll tax lodgers (#146), and PAYG instalments for quarterly payers (#149).
- Ridgeline cash decisions with a 12-cell receipt-delay and hiring grid (#166), and a Lumbridge close handoff that reconstructs the opening payable from its own fabricated bills, credits and settlements (#170).

Fixed:

- `model-export` refuses to write over its own configuration, including through links (#154); correction slugs cannot leave the corrections directory (#155); experiment saves no longer overwrite a competing save of the same name (#156); depreciation evidence refuses a non-boolean `synthetic_input` (#157); registry loaders report broken paths and non-mapping YAML instead of returning empty records (#158).
- The Lumbridge briefing's figures are tied to their sources by tests (#138), the learning workflows keep Xero API data out until the developer terms are checked (#148), and `docs/ai-register-entry.md` gives supplier information for a firm's AI register (#153).

# v0.1.2

Breaking for scripts written against 0.1.1:

- `reconcile-source` and `reconcile_account_table` agree a target within half a cent
  by default (`--abs-tolerance 0.005`), and the relative `--tolerance` is off unless
  set. The old 1% default passed 3,000 cross-mapped between two revenue targets.
  Whole-dollar controls need `--abs-tolerance 0.5`.
- `EntityConfig.tax_rate` is required; the old 21% default was the US federal rate.
  `start_month` must be `YYYY-MM`, and date text given to payroll, GST, rate lookups and
  `format_au_date` must be ISO: day-first text such as `1/10/2026` is refused instead
  of being read as January.
- Config and 13-week cash files refuse unknown keys (`EntityConfig` and its parts,
  `Cash13Config`, `WeeklyFlow`), and opex amounts cannot be negative.
- `read_xero_report` refuses a report whose amount columns are not periods, such as a
  comparison or tracking export, unless `tracking_comparison=True` is set for a
  standard P&L with one tracking option per column. It also refuses a `Total X` row
  with no `X` heading above it and, in the flat layout, a row with more fields than
  the header, a filled row with no account, and unnamed or repeated columns.
  `pyfpa.io.xero_au.from_xero` is removed.
- Payroll tax and super guarantee lookups after 30 June 2027, the date those tables
  were verified to, raise until the tables are verified again.
- `fetch_abs_series` reads its key only from `ABS_API_KEY` and no longer takes an
  `api_key` argument. Its keys map to the ABS Indicator API's `_H` dataflows, a
  response in the wrong frequency is refused, and retail trade is history only: the
  ABS ceased it with the June 2025 period.
- Cross-client promotion is default-deny (below), `seed_from_library` requires
  `company_root` and `seeded_at`, and `promote_challenger` requires `objective` and
  `approved_at`.
- `verify_workbook` requires every expected column, a matching period header and zero
  `check_*` rows. `recover_actuals` raises for a line it cannot recover instead of
  skipping it, `score_forecast` skips zero-weight lines and refuses all-zero weights,
  and `pyfpa.memory.diagnostics.validate_workspace` is removed in favour of
  `Workspace.validate`.

Figures that change:

- A BAS due date on a weekend moves to the following Monday, and a leading partial
  quarter settles the months the series holds instead of being dropped.
- Workers compensation includes bonuses, as every state's wage definition does.
- `fy_summary` orders periods by date, and a divestiture keeps cogs consistent with
  gross profit.

New:

- 13-week cash scenarios: `Scenario`, `apply_scenario`, `compare_scenarios` and
  `load_cash13_scenarios`.
- `pyfpa.au.depreciation` reads accounting-depreciation evidence files, refuses one
  whose producer rejected it or whose digest no longer matches, and spreads a charge
  in whole cents with expense and asset purchases kept apart.
- `verify_structure` checks a workbook's layout contract, and `model_to_excel` writes
  `check_*` self-check rows.

Cross-client promotion:

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
- Approval files store contributing workspaces as opaque ids, so nothing in a shared
  library names a client directory. Building one still accepts paths. The library's seed
  index records the receiving workspace by id too, and `withdraw_prior` resolves ids back
  to paths through `provenance/workspaces.yaml` when it reports affected workspaces.
- `record_promotion_approval` writes with an exclusive create through the new
  `pyfpa.io.loaders.create_yaml`, so a second writer racing on the same digest is
  refused instead of replacing a recorded decision.
- `validate_prior` stamps each result it produces, and `promote_prior` refuses a result
  that stamp does not cover, which rejects a `ValidationResult` built by hand, edited on
  disk or carried over from another candidate. The stamp is a per-process structural
  barrier, not a security control, so validate and promote in one session.
- `validate_prior` also refuses a candidate whose business type or value are not the ones
  its folds tested.
- `promote_skill` reads the skill tree once and writes those exact bytes, instead of
  copying the client's directory again after the screen, and refuses a symlink, junction
  or other reparse point inside the tree.
- `seed_from_library` digests each stored prior again from its driver, business type,
  value and contributing workspace ids, and refuses it unless that reproduces the
  recorded digest and its approval is on disk. A legacy entry with no digest, and an
  entry edited after promotion, are both refused.
- Loading an approval checks that the record's own `candidate_digest` is the one it was
  looked up by, so a record copied onto another candidate's filename is refused, and the
  findings stamp writes to the digest the gate verified.
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
- The distribution is `au-fpa-pack` and the import is `pyfpa`. Version 0.1.1
  is available on [PyPI](https://pypi.org/project/au-fpa-pack/0.1.1/).
- Tested on Python 3.11, 3.12 and 3.13.
