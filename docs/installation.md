## Current quick start

Clone the repository and install it into a Python 3.11 or newer environment:

```bash
git clone https://github.com/ryanduguid/au-fpa-pack
cd au-fpa-pack
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Then open the repository in Codex or Claude Code and ask:

```text
Help me onboard this company into openfpa.
The financial files are in ./company-data.
Inspect them first, then ask me only what you cannot determine.
```

The repository instructions tell the agent to initialize `.fpa/`, inspect local
evidence, conduct the intake, and stop for architecture approval.
