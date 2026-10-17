## Package-only first result

On Python 3.14 or newer, install the published distribution in a virtual
environment:

```bash
python -m pip install au-fpa-pack
```

Save this as `first_result.py` and run `python first_result.py` from any
directory. The fabricated CSV is part of the installed package:

```python
from importlib.resources import as_file, files

from pyfpa.io.xero_au import read_xero_report

with as_file(files("pyfpa.io").joinpath("fixtures/xero_pl_au.csv")) as fixture:
    accounts = read_xero_report(fixture).by_account()

print(f"Sales - Domestic: {accounts['Sales - Domestic']:.2f}")
print(f"Fixture profit: {sum(accounts.values()):.2f}")
```

```text
Sales - Domestic: 99000.00
Fixture profit: -4504.00
```

The parser reads local data without connecting to Xero or creating a company
workspace. The example demonstrates the import and signed totals only. Real
company work still needs source registration, mapping and reconciliation in
the [Xero recipe](recipes/xero-au.md).

## Source quick start

Clone the repository and install the locked development environment with
[uv](https://docs.astral.sh/uv/), on Python 3.14 or newer:

```bash
git clone https://github.com/ryanduguid/au-fpa-pack
cd au-fpa-pack
uv sync --locked --extra dev
```

`uv sync --locked --extra dev` is the install path. It is what CI runs and what
`uv.lock` pins, so the committed example figures reproduce. Run anything in the
repository through the same environment, for example
`uv run --locked --extra dev pytest -q`.

Secondary, without uv: `python -m pip install -e ".[dev]"` inside a virtual
environment installs the same package, but it resolves dependencies fresh
rather than from `uv.lock`, so versions can differ from CI and from the
recorded outputs.

Then open the repository in Codex or Claude Code and ask:

```text
Help me onboard this company into openfpa.
The financial files are in ./company-data.
Inspect them first, then ask me only what you cannot determine.
```

The repository instructions tell the agent to initialise `.fpa/`, inspect local
evidence, conduct the intake, and stop for architecture approval.
