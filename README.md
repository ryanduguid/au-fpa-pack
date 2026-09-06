# au-fpa-pack: find the cash gap beyond the next quarter

Synthetic example. Forecasting aid, not tax advice; a human approves the assumptions and funding decision.

**Input:** [Harbour Light's fabricated Xero exports](examples/harbour-light/data/), Victorian payroll assumptions and quarterly BAS cash timing for FY2027.

From a clone in a Python 3.11+ virtual environment, install: `python -m pip install -e .`

```bash
python examples/harbour-light/run_harbour.py
```

**Output:** a briefing and model workbook in `examples/harbour-light/output/`.

| Forecast measure | Reproduced result |
| --- | ---: |
| FY2027 revenue | $1,332,000 |
| Cash at June 2027 year-end | -$1,354 |
| Minimum cash in the 13-week forecast | $33,180, in week 13 |

**Human decision:** Which collection, cost or funding assumptions must change before approving a forecast that ends the financial year with negative cash?

The shorter cash forecast stays positive. That does not settle the full-year funding question.

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
