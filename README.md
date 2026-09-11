# au-fpa-pack: reconcile Australian profit and cash

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
<summary>Setup, Australian scope, upstream workbench and reference</summary>

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

## Reference and contribution

- [Upstream workbench and company workspace](docs/upstream-workbench.md)
- [Agent CLI reference](docs/cli-reference.md)
- [Python kernel](docs/python-kernel.md)
- [Contributing](CONTRIBUTING.md) and [security reporting](SECURITY.md)

MIT licensed. Guiderail's upstream work and Ryan Duguid's additions retain their attribution in [LICENSE](LICENSE).

</details>
