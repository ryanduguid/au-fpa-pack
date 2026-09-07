## Why this exists

Traditional FP&A software asks a company to configure itself inside a fixed
application. openfpa gives an AI enough finance structure, memory, and
guardrails to learn the business and build what that CFO or FP&A team actually
needs.

A generic AI can write a forecast from scratch, but each run tends to produce a
new pile of code with no shared accounting logic, durable context, test history,
or promotion process. openfpa adds:

- **A tested finance kernel.** Revenue, COGS, operating expenses, working
  capital, debt, tax, cash flow, reconciliation, and reporting primitives live
  in `pyfpa`.
- **An agent operating contract.** `AGENTS.md`, `CLAUDE.md`, and the skills in
  `skills/` define how the agent should inspect evidence, ask questions, make
  changes, and validate its work.
- **Durable company memory.** Business facts, sources, mappings, corrections,
  forecasts, experiments, decisions, and model history live in `.fpa/`.
- **Evidence-gated iteration.** Champion and challenger models are evaluated on
  held-out actuals and accounting checks. Weak challengers are retained as
  failed research. Promotion requires human approval.
- **Visible adaptation.** Company-specific code belongs in generated namespaces,
  where it can be reviewed, tested, and changed.

The goal is a dependable process that helps the AI produce a better
company-specific result over time.
## How onboarding works

For broad company work, the agent starts by inspecting local evidence. It does
not begin with a long generic questionnaire.

It records what it can establish, including sources and confidence, then asks
only unresolved questions in short rounds. Typical questions cover:

- business model, products, customers, segments, and revenue drivers;
- seasonality, pricing, unit economics, and major operating constraints;
- legal entities, reporting periods, currencies, and consolidation needs;
- debt, liquidity, capital spending, and working-capital behavior;
- the decisions the CFO needs the model to support;
- available systems, exports, folders, and credentials.

The first durable outputs are:

- `.fpa/intake.md`;
- `.fpa/business-profile.md`;
- `.fpa/decisions/initial-model-architecture.md`.

The agent waits for approval before generating a model or accessing an external
system. Narrow requests do not force a full company interview.
## Data access is agent-built

openfpa does not aim to maintain a conventional connector marketplace. The AI
should help the user reach the data that already exists, then build the smallest
reliable ingestion path for that company.

The agent should first ask where the relevant evidence lives:

- QuickBooks, Xero, NetSuite, or another accounting system;
- local CSV, Excel, or Google Sheets files;
- a shared folder containing monthly financial packages;
- P&L and balance-sheet exports;
- AR and AP aging reports;
- inventory balances, item detail, or purchasing data;
- payroll, CRM, billing, bank, or operational systems;
- public filings when the company is public.

It should then choose an access path:

1. Read local files already supplied by the user.
2. Use an existing host tool, MCP server, or authenticated command if available.
3. Ask the user to export a report when that is the safest and fastest path.
4. Build a company-specific API or file connector when recurring access matters.

Generated connector code belongs in `connectors/generated/`. It should include:

- the expected source and authentication method;
- a fixture or redacted sample;
- explicit field and account mappings;
- source totals and reconciliation checks;
- failure behavior for missing, duplicate, or unmapped records;
- tests that do not require production credentials.

Credentials stay with the host tool or environment and are never committed.
## The company workspace

```text
company/
|-- .fpa/
|   |-- MEMORY.md
|   |-- intake.md
|   |-- business-profile.md
|   |-- sources/
|   |-- mappings/
|   |-- corrections/
|   |-- forecasts/
|   |-- experiments/
|   |-- decisions/
|   |-- models/
|   `-- research/
|-- connectors/generated/
|-- models/generated/
|-- skills/generated/
`-- agents/generated/
```

Canonical memory remains readable Markdown and YAML. A rebuildable local index
supports task-specific retrieval, but the index is not the source of truth.

Memory and learning are different:

- **Memory** preserves what the system knows, where it learned it, and what
  humans corrected or approved.
- **Learning** evaluates model changes against actual outcomes and retains the
  evidence from accepted and rejected experiments.

See [`docs/agent-native-workspace.md`](../docs/agent-native-workspace.md) for the
workspace and mutation contract.
## The research loop

The iteration model is inspired by
[Karpathy's AutoResearch](https://github.com/karpathy/autoresearch): define an
objective, run bounded experiments, keep measurable improvements, and preserve
failed attempts so they are not repeated without new evidence.

For FP&A, the objective is not simple in-sample reconciliation. A candidate
should improve forecast performance on held-out actuals while passing hard
checks such as:

- source reconciliation;
- accounting identities;
- segment or entity rollups;
- working-capital continuity;
- fit and holdout separation;
- scenario coherence.

The AI may generate, evaluate, and discard challengers after the initial
architecture is approved. A promotion-eligible challenger is presented to the
human with its metrics, tradeoffs, complexity cost, and evidence. The active
champion changes only after explicit approval.
## Skills

The repository includes skills for:

- learning the business;
- scaffolding an initial model;
- configuring actuals and data access;
- running monthly close and cash runway analysis;
- producing board briefings;
- capturing human corrections;
- applying CFO judgment;
- running company research epochs;
- learning cautiously across a portfolio.

The skills are repo-native instructions for capable coding agents. The
`.claude-plugin/` manifest also supports Claude plugin installation, but the
underlying workflow is not intended to be Claude-only.
