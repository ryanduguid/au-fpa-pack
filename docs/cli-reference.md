## Agent toolbelt CLI

The `openfpa` command is a machine-oriented control surface for Codex, Claude
Code, and other capable coding agents. It emits JSON, performs deterministic
workspace operations, and leaves reasoning and conversation to the host agent.

The command set is:

```text
openfpa init
openfpa inspect-data
openfpa status
openfpa source-profile
openfpa source-register
openfpa source-list
openfpa mapping-register
openfpa mapping-list
openfpa reconcile-source
openfpa connector-scaffold
openfpa connector-list
openfpa connector-validate
openfpa intake-next
openfpa intake-record
openfpa doctor
openfpa entrypoint-list
openfpa entrypoint-register
openfpa correction-record
openfpa correction-list
openfpa scorecard-render
openfpa experiment-list
openfpa context-pack
openfpa onboarding-render
openfpa model-export
```

In a source checkout without the `openfpa` console script installed, every
command also works as `python3 -m pyfpa.cli <command>`.

The CLI can:

- initialize and validate the workspace;
- inventory local files and likely financial artifacts;
- profile CSV, TSV, and Excel tables without changing them;
- register source provenance, coverage, entities, and currencies;
- persist exact source-to-model mappings and deliberate ignores;
- reconcile account-amount CSV files while surfacing duplicates and unmapped values;
- scaffold company connector bundles from redacted fixtures;
- execute fixture-mode connector contracts and compare golden mapped totals;
- show unresolved intake questions;
- expose source, mapping, model, and research status;
- run deterministic checks and reports;
- provide structured context for the AI to continue the work;
- support non-interactive automation where the operation is deterministic.

The AI should still decide what questions matter, what data path to use, what
model fits the business, and what experiment to run next.

All commands return a versioned JSON envelope. Exit code `0` means success, `1`
means the requested operation or a diagnostic check failed, and `2` means the
command arguments were invalid.

`intake-record` writes one sourced fact to `.fpa/intake.md`. Generated company
workflows are published in `.fpa/models/entrypoints.yaml` with
`entrypoint-register`. The registry lets an agent discover the tested command,
working directory, inputs, and outputs. Registration does not execute the
command.

```bash
openfpa source-register . \
  --source-id monthly-pl \
  --kind local_file \
  --location data/monthly-pl.csv \
  --entity "Acme Inc." \
  --currency USD \
  --period 2026-05 \
  --extraction-method "Controller export from the accounting system"

openfpa mapping-register . \
  --source-id monthly-pl \
  --source-value "Product Revenue" \
  --target income_statement.product_revenue

openfpa reconcile-source . \
  --source-id monthly-pl \
  --account-column Account \
  --amount-column Amount

openfpa connector-scaffold . \
  --name accounting-pl \
  --source-id monthly-pl \
  --description "Pull and normalize the monthly P&L" \
  --auth-method host_environment \
  --fixture fixtures/redacted-monthly-pl.csv

openfpa connector-validate . --name accounting-pl

openfpa intake-record . \
  --key business_model \
  --answer "Commercial coffee roasting" \
  --source-type user

openfpa entrypoint-register . \
  --name forecast \
  --kind forecast \
  --description "Run the approved monthly forecast" \
  --command-json '["python3", "models/generated/run_forecast.py"]' \
  --input data/actuals.csv \
  --output output/forecast.xlsx
```

`connector-scaffold` creates:

```text
connectors/generated/accounting-pl/
|-- connector.yaml
|-- connector.py
|-- run.py
|-- README.md
`-- fixtures/source.csv
```

The scaffold requires a registered source, complete mappings, and a redacted
CSV fixture with no duplicate or unmapped accounts. It stores golden mapped
totals in `connector.yaml`. `connector-validate` parses the fixture in-process
through the closed `account-amount-csv` adapter and reconciles it against those
totals. It does not import or run bundle code, and it does not contact a live
system.

The generated `extract_live()` function intentionally fails until the agent
implements host-authenticated access. After the live path has its own
fixture-backed tests and safe failure behavior, register the recurring command
with `entrypoint-register --kind connector`.
