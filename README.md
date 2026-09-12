# Australian financial planning and analysis with openfpa

[![tests](https://github.com/ryanduguid/au-fpa-pack/actions/workflows/ci.yml/badge.svg)](https://github.com/ryanduguid/au-fpa-pack/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/au-fpa-pack.svg?color=5C2D91&labelColor=04001F)](https://pypi.org/project/au-fpa-pack/)
[![licence: MIT](https://img.shields.io/badge/licence-MIT-5C2D91.svg?labelColor=04001F)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11%2B-5C2D91.svg?labelColor=04001F)](https://www.python.org/)

Synthetic example. Forecasting aid, not tax advice; a human approves the assumptions and funding decision.

**Input:** [Lumbridge Services' fabricated records](examples/lumbridge-services/data/), NSW payroll assumptions and dated customer receipts and payments for October to December 2026.

Lumbridge Services is a fictional Newcastle maintenance business. Its Varrock and Falador service lines are Old School RuneScape references; no game knowledge is needed. All amounts are AUD.

From a clone, use Python 3.11 and the locked development environment:

```bash
uv sync --locked --extra dev
uv run --locked --extra dev python examples/lumbridge-services/models/generated/lumbridge.py
```

**Output:** `briefing.md`, `lumbridge.xlsx`, monthly and cash schedules in `examples/lumbridge-services/output/`.

| Forecast measure | Receipt on time | Receipt 45 days late |
| --- | ---: | ---: |
| Quarter revenue | $180,000.00 | $180,000.00 |
| Quarter profit before income tax | $35,957.55 | $35,957.55 |
| October closing cash | $32,040.00 | ($11,960.00) |
| Lowest daily closing cash | $16,800.00 | ($25,160.00) |
| December closing cash | $67,320.00 | $67,320.00 |

**Human decision:** Can the business meet its next payments if a customer pays late, and should the owner defer discretionary equipment spending?

In desktop Excel, change `Assumptions!B2` from 0 to 45. This delays one $44,000 receipt and creates a $25,160 cash shortfall on 6 November without changing profit. Restore 0 after use. The workbook supports only whole-day receipt delays from 0 to 120; CSVs and briefing text are fixed exports.

Read the [assumptions and limits](examples/lumbridge-services/README.md), then use the [independent trial guide](examples/lumbridge-services/TRIAL.md) to record a review. The independent accountant trial remains pending. This synthetic case does not establish client outcomes or forecast accuracy.

[Harbour Light](examples/harbour-light/README.md) provides a separate Victorian wholesale example with FY2027 reporting and quarterly BAS cash timing.

<details>
<summary>Setup, Australian scope, skills, kernel packages, upstream workbench and reference</summary>

## What this repository adds

An Australian extension of [openfpa](https://github.com/JeffBrines/openfpa), by Guiderail: 30 June years, Xero AU mapping, GST/BAS cash timing and payroll on-cost assumptions.

**Package lifecycle:** source-only. The distribution is `au-fpa-pack`, the import is `pyfpa`, and the command is `openfpa`. It is not published to PyPI.

## Reproduce and inspect

- [Setup](docs/installation.md)
- [Lumbridge inputs, method and limits](examples/lumbridge-services/README.md)
- [Harbour Light inputs, method and limits](examples/harbour-light/README.md)
- [Australian scope and source dates](docs/australian-pack.md)
- [Other synthetic and public-data examples](docs/examples.md)

The command above creates files; it does not establish native Excel recalculation or forecast accuracy.

## Skills

[`skills/`](skills/) holds 17 skills. Sixteen are the pack's own, grouped by what
they are for:

- **Australian rules:** `fpa-au-drivers`, `fpa-au-gst-bas`, `fpa-au-payroll`, `fpa-au-xero`
- **Onboarding and building:** `fpa-learn-business`, `fpa-configure-actuals`, `fpa-scaffold-model`, `fpa-excel-model`
- **Running the month:** `fpa-monthly-close`, `fpa-cash-runway`, `fpa-board-briefing`, `fpa-cfo-judgment`
- **Learning from outcomes:** `fpa-capture-correction`, `fpa-backtest-learn`, `fpa-research-loop`, `fpa-portfolio-learn`

The seventeenth, [`skills/generated/sku-profitability`](skills/generated/sku-profitability/SKILL.md),
is the worked example of a company-specific skill the workflow writes, not a
skill the pack ships for every company.

[`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) declares the
repository as the `openfpa` plugin, version 0.1.0, MIT. That manifest is what a
Claude Code marketplace entry pointing at this repository installs.

## Kernel packages and how each is reached

| Package | What it is for | How it is reached |
| --- | --- | --- |
| `pyfpa/memory` | Company memory on disk: the `.fpa/` workspace, intake, sources, mappings, connectors, corrections, experiments, entrypoints and the retrieval index. | The `openfpa` CLI. Every workspace command in the [CLI reference](docs/cli-reference.md) goes through it. |
| `pyfpa/research` | The champion and challenger loop: a company objective, scored epochs, and a model registry that only a recorded human approval changes. | `openfpa status` reads the model registry. The loop itself runs from [`skills/fpa-research-loop`](skills/fpa-research-loop/SKILL.md) against the Python API. |
| `pyfpa/portfolio` | Cross-client learning: a portfolio manifest, priors mined and validated across clients, and recurring generated skills promoted into a shared library. | The Python API only. No CLI command reaches it, and today the one documented route is [`skills/fpa-portfolio-learn`](skills/fpa-portfolio-learn/SKILL.md). |

## Reference and contribution

- [Upstream workbench and company workspace](docs/upstream-workbench.md)
- [Agent CLI reference](docs/cli-reference.md)
- [Python kernel](docs/python-kernel.md)
- [Contributing](CONTRIBUTING.md) and [security reporting](SECURITY.md)

MIT licensed. Guiderail's upstream work and Ryan Duguid's additions retain their attribution in [LICENSE](LICENSE).

</details>
