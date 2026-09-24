"""Score a hand-built model workbook against the Keldagrim Forge engine.

Build the workbook from `examples/keldagrim-forge/config.yaml` as the README
describes, then run this script to score it. Prints one JSON document to
stdout (the repository CLI contract) and the same scorecard in words to
stderr. Nothing leaves the machine and no result is recorded.

usage:
    uv run --locked --extra dev python examples/keldagrim-forge/drill.py \\
        <workbook.xlsx> [--scenario base|receipt-delay]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from pyfpa.config.loader import load_config
from pyfpa.excel.structure import verify_structure
from pyfpa.excel.verify import verify_workbook
from pyfpa.models.cashflow import apply_receipt_delay, cashflow_from_config

HERE = Path(__file__).resolve().parent


def _verdict(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def _load_scenario(name: str) -> dict[str, object]:
    scenarios = yaml.safe_load((HERE / "scenarios.yaml").read_text(encoding="utf-8"))
    if name not in scenarios:
        raise SystemExit(f"unknown scenario {name!r}; expected one of {sorted(scenarios)}")
    shift = scenarios[name]
    for key in ("month", "to_month", "amount"):
        if key not in shift:
            raise SystemExit(f"scenario {name!r} is missing {key!r}")
    return shift


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score a Keldagrim Forge model workbook against the engine."
    )
    parser.add_argument("workbook", type=Path, help="the workbook to score")
    parser.add_argument(
        "--scenario",
        choices=("base", "receipt-delay"),
        default="base",
        help="which engine scenario the workbook must reproduce",
    )
    args = parser.parse_args()

    cfg = load_config(HERE / "config.yaml")
    forecast = cashflow_from_config(cfg)
    if args.scenario == "receipt-delay":
        shift = _load_scenario("receipt-delay")
        forecast = apply_receipt_delay(
            forecast,
            month=str(shift["month"]),
            to_month=str(shift["to_month"]),
            amount=float(shift["amount"]),
        )

    structure = verify_structure(args.workbook)
    numbers = verify_workbook(args.workbook, forecast)
    deviation = float(numbers.max_rel_deviation)
    passed = structure.passed and numbers.passed
    payload: dict[str, object] = {
        "workbook": str(args.workbook),
        "scenario": args.scenario,
        "structure": {
            "passed": structure.passed,
            "checks_run": structure.checks_run,
            "failures": structure.failures,
        },
        "numbers": {
            "passed": numbers.passed,
            "lines_checked": numbers.lines_checked,
            "max_rel_deviation": deviation,
            "failures": numbers.failures,
        },
        "verdict": _verdict(passed),
    }
    print(json.dumps(payload, indent=2))

    print(f"Keldagrim Forge drill: {args.workbook} [{args.scenario}]", file=sys.stderr)
    print(
        f"structure: {_verdict(structure.passed)} ({structure.checks_run} checks)",
        file=sys.stderr,
    )
    for failure in structure.failures:
        print(f"  - {failure}", file=sys.stderr)
    print(
        f"numbers: {_verdict(numbers.passed)} ({numbers.lines_checked} lines, "
        f"max rel deviation {deviation:.2e})",
        file=sys.stderr,
    )
    for failure in numbers.failures:
        print(f"  - {failure}", file=sys.stderr)
    print(f"verdict: {_verdict(passed)}", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
