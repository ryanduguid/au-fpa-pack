# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""Opt-in local process adapter; never installs or downloads a calculator."""

import json
import math
import subprocess
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pyfpa.au.payg_withholding import RolePay, RoleWithholding


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("calculator returned a repeated JSON key")
        result[key] = value
    return result


def _run_calculator(payment: RolePay, executable: Path, timeout: float) -> tuple[dict[str, Any], str]:
    """The calculator's JSON object and stdout for one pay, or the reason it gave none."""
    arguments = {
        "earnings": str(payment.earnings), "pay_period": payment.pay_period,
        "scale": payment.scale, "year": payment.year, "scope_confirmed": True,
    }
    try:
        process = subprocess.run(
            [str(executable), "payg-withholding", "--refusal-json"],
            input=json.dumps(arguments), text=True, encoding="utf-8",
            capture_output=True, timeout=timeout, check=False, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise ValueError("local withholding calculator could not complete") from exc
    label = f"{payment.role_name} on {payment.payday.isoformat()}"
    try:
        body = json.loads(process.stdout, object_pairs_hook=_unique_object)
    except (ValueError, TypeError) as exc:
        if process.returncode:
            stderr = (process.stderr or "").strip().splitlines()
            reason = stderr[0] if stderr else "no output"
            raise ValueError(f"calculator exited {process.returncode}: {reason}") from exc
        raise ValueError("calculator returned invalid JSON") from exc
    if not isinstance(body, dict):
        raise ValueError("calculator response must be a JSON object")
    if process.returncode or body.get("ok") is not True:
        code = body.get("code", "process.failed")
        raise ValueError(f"calculator refused withholding for {label}: {code}: {body.get('message', 'no message')}")
    return body, process.stdout


def _withholding(body: dict[str, Any], payment: RolePay, engine_version: str) -> Decimal:
    """The withholding from a successful result, once its identity and evidence check out."""
    if (
        body.get("engine") != "australian-tax-calculators"
        or body.get("engine_version") != engine_version
        or body.get("calculation") != "payg_withholding"
        or body.get("period") != f"{payment.year} {payment.pay_period}"
    ):
        raise ValueError(
            "calculator identity, version, calculation or period does not match: "
            f"{body.get('engine')} {body.get('engine_version')}, "
            f"{body.get('calculation')} {body.get('period')}"
        )
    warnings = body.get("warnings")
    sources = body.get("sources")
    if (
        not isinstance(warnings, list) or not warnings
        or not all(isinstance(w, str) and w.strip() for w in warnings)
        or not isinstance(sources, list) or not sources
        or not all(isinstance(source, str) and source.strip() for source in sources)
        or not isinstance(body.get("source_checked"), str) or not body["source_checked"].strip()
        or not isinstance(body.get("scope"), str) or not body["scope"].strip()
    ):
        raise ValueError("calculator response is missing source or scope evidence")
    amounts = body.get("amounts")
    value = amounts.get("withholding") if isinstance(amounts, dict) else None
    if not isinstance(value, str):
        raise ValueError("calculator withholding must be an AUD decimal string")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("calculator withholding must be an AUD decimal string") from exc


def calculate_role_withholding(
    payments: Sequence[RolePay], *, executable: Path, engine_version: str,
    timeout: float = 10,
) -> list[RoleWithholding]:
    """Calculate ordinary Schedule 1 pays using an explicitly selected local binary.

    The caller verifies the binary's origin and pins its expected version.
    Bonuses, study loans, Medicare variations, offsets and extra-pay adjustments
    are outside this adapter's scope, and `RolePay` refuses scale 4 and
    quarterly pays. Each payment must confirm that scope. The full response is
    retained for sources, warnings and human review.
    """
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError("executable must identify an existing absolute local file")
    if not engine_version.strip():
        raise ValueError("engine_version must be explicitly pinned")
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and greater than 0")
    results = []
    for payment in payments:
        body, stdout = _run_calculator(payment, executable, timeout)
        results.append(RoleWithholding(payment, _withholding(body, payment, engine_version), stdout))
    return results
