# au-fpa-pack: reconcile Australian profit and cash

Synthetic example. Forecasting aid, not tax advice; a human approves the assumptions and funding decision.

**Input:** [Harbour Light's fabricated Xero exports](examples/harbour-light/data/), Victorian payroll assumptions and quarterly BAS cash timing for FY2027.

From a clone in a Python 3.11+ virtual environment, install: `python -m pip install -e ".[dev]"`. The example uses the formula verifier included in the development dependencies.

```bash
python examples/harbour-light/run_harbour.py
```

**Output:** a briefing and model workbook in `examples/harbour-light/output/`.

| Forecast measure | Reproduced result |
| --- | ---: |
| FY2027 revenue | $1,332,000 |
| FY2027 net loss | -$86,774 |
| Cash at June 2027 year-end | $51,312 |
| GST payable at June 2027 year-end | $9,630 |
| Minimum cash in the 13-week forecast | $60,312, in week 13 |

**Human decision:** Which sales or cost assumptions need to change to address the forecast loss, and how much cash must be reserved for unpaid BAS and other obligations?

The model retains leave provisions in profit and adds them back in cash. It includes GST collections, purchases and settlements, including the opening liability. The [example's assumptions and limits](examples/harbour-light/README.md) explain what remains outside the cash forecast.

For a Newcastle service-business case, try [Lumbridge Services](examples/lumbridge-services/README.md).
Its OSRS-inspired example traces a delayed $44,000 customer receipt into a
$25,160 cash shortfall while quarterly profit stays unchanged. It includes a
formula workbook, management briefing and [independent trial guide](examples/lumbridge-services/TRIAL.md).

<details>
<summary>Setup, Australian scope, upstream workbench and reference</summary>

## What this repository adds

An Australian extension of [openfpa](https://github.com/JeffBrines/openfpa), by Guiderail: 30 June years, Xero AU mapping, GST/BAS cash timing and payroll on-cost assumptions.

**Package lifecycle:** source-only. The distribution is `au-fpa-pack`, the import is `pyfpa`, and the command is `openfpa`. It is not published to PyPI.

## Reproduce and inspect

- [Setup](docs/installation.md)
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
