"""Score a hand-built model workbook against the Keldagrim Forge engine.

Build the workbook from `examples/keldagrim-forge/config.yaml` as the README
describes, then run this script to score it. Nothing leaves the machine and no
result is recorded.

usage:
    uv run --locked --extra dev python examples/keldagrim-forge/drill.py <workbook.xlsx>
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pyfpa.config.loader import load_config
from pyfpa.excel.structure import verify_structure
from pyfpa.excel.verify import verify_workbook
from pyfpa.models.cashflow import cashflow_from_config

HERE = Path(__file__).resolve().parent


def _verdict(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score a Keldagrim Forge model workbook against the engine."
    )
    parser.add_argument("workbook", type=Path, help="the workbook to score")
    args = parser.parse_args()

    cfg = load_config(HERE / "config.yaml")
    structure = verify_structure(args.workbook)
    numbers = verify_workbook(args.workbook, cashflow_from_config(cfg))

    print(f"Keldagrim Forge drill: {args.workbook}")
    print(f"structure: {_verdict(structure.passed)} ({structure.checks_run} checks)")
    for failure in structure.failures:
        print(f"  - {failure}")
    print(
        f"numbers: {_verdict(numbers.passed)} ({numbers.lines_checked} lines, "
        f"max rel deviation {numbers.max_rel_deviation:.2e})"
    )
    for failure in numbers.failures:
        print(f"  - {failure}")
    passed = structure.passed and numbers.passed
    print(f"verdict: {_verdict(passed)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
