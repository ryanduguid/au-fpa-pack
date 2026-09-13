from dataclasses import dataclass

import pytest

from pyfpa.cli import main
from pyfpa.config.schemas import (
    Channel,
    DebtInstrument,
    EntityConfig,
    OpeningBalances,
    OpexLine,
    WorkingCapitalConfig,
)


@dataclass(frozen=True)
class CliResult:
    """What one in-process `openfpa` invocation produced."""

    returncode: int
    stdout: str
    stderr: str


@pytest.fixture
def run_cli(capsys):
    """Call `pyfpa.cli.main(argv)` in this process and capture its JSON.

    Shelling out to a fresh interpreter hid the CLI from coverage. The console
    script contract is what a subprocess establishes, so tests/test_cli.py keeps
    2 subprocess tests for that and nothing else.
    """

    def _run(*args: str) -> CliResult:
        capsys.readouterr()
        try:
            returncode = main([*args])
        except SystemExit as exc:
            # JsonArgumentParser.error writes JSON to stderr and exits.
            returncode = 0 if exc.code is None else int(exc.code)
        captured = capsys.readouterr()
        return CliResult(returncode, captured.out, captured.err)

    return _run


@pytest.fixture
def sample_config() -> EntityConfig:
    return EntityConfig(
        name="Test Co",
        start_month="2026-01",
        horizon_months=12,
        tax_rate=0.0,
        channels=[
            Channel(name="D2C", annual_revenue=1200.0, growth_rate=0.0,
                    seasonality=[1.0] * 12, cogs_pct=0.5),
        ],
        opex=[OpexLine(name="Rent", kind="fixed", monthly_amount=100.0)],
        debt=[DebtInstrument(name="Term", kind="term_loan", opening_balance=1200.0,
                             annual_rate=0.12, monthly_principal=100.0)],
        working_capital=WorkingCapitalConfig(dso_days=30, dpo_days=30, dio_days=0),
        opening_balances=OpeningBalances(cash=500.0, ar=0.0, ap=0.0, inventory=0.0),
    )
