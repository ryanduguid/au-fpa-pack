"""Fuzz the Xero and P&L CSV importers with fabricated exports."""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

from pyfpa.io.pl_csv import read_pl_csv
from pyfpa.io.xero_au import read_xero_report

SCRATCH = Path(tempfile.mkdtemp(prefix="pyfpa-fuzz-")) / "export.csv"


def _check_amounts(amounts: dict[str, float], where: str) -> None:
    # Explicit raises, because python -O strips assert statements.
    if not all(math.isfinite(amount) for amount in amounts.values()):
        raise AssertionError(f"{where} accepted a non-finite amount: {amounts!r}")


def test_one_input(data: bytes) -> None:
    SCRATCH.write_bytes(data)
    # A malformed export must be refused with ValueError, the importers'
    # documented failure; anything else escaping is a crash.
    for tracking_comparison in (False, True):
        try:
            report = read_xero_report(SCRATCH, tracking_comparison=tracking_comparison)
        except ValueError:
            continue
        _check_amounts(report.by_account(), "read_xero_report")
    try:
        _check_amounts(read_pl_csv(SCRATCH), "read_pl_csv")
    except ValueError:
        pass


if __name__ == "__main__":
    import atheris

    atheris.instrument_all()
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
