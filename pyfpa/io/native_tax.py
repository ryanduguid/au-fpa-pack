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


def calculate_role_withholding(
    payments: Sequence[RolePay], *, executable: Path, engine_version: str,
    timeout: float = 10,
) -> list[RoleWithholding]:
    """Calculate ordinary Schedule 1 pays using an explicitly selected local binary.

    The caller verifies the binary's origin and pins its expected version.
    Bonuses, study loans, Medicare variations, offsets and extra-pay adjustments
    are outside this adapter's scope. Each payment must confirm that scope.
    The full response is retained for sources, warnings and human review.
    """
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError("executable must identify an existing absolute local file")
    if not engine_version.strip():
        raise ValueError("engine_version must be explicitly pinned")
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and greater than 0")
    results = []
    for payment in payments:
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
        try:
            body = json.loads(process.stdout, object_pairs_hook=_unique_object)
        except (ValueError, TypeError) as exc:
            raise ValueError("calculator returned invalid JSON") from exc
        if not isinstance(body, dict):
            raise ValueError("calculator response must be a JSON object")
        if process.returncode or body.get("ok") is not True:
            raise ValueError(f"calculator refused withholding: {body.get('code', 'process.failed')}")
        if (
            body.get("engine") != "australian-tax-calculators"
            or body.get("engine_version") != engine_version
            or body.get("calculation") != "payg_withholding"
            or body.get("period") != f"{payment.year} {payment.pay_period}"
        ):
            raise ValueError("calculator identity, version, calculation or period does not match")
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
            withholding = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("calculator withholding must be an AUD decimal string") from exc
        results.append(RoleWithholding(payment, withholding, process.stdout))
    return results
