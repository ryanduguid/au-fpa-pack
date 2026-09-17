"""The opt-in accounting-depreciation scenario.

Every test runs with sockets blocked. The module reads a file that something
else produced; it makes no call, and the block is what proves it.
"""

from __future__ import annotations

import json
import socket
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from pyfpa.au import depreciation as dep

FIXTURES = Path(dep.__file__).resolve().parent / "fixtures"
GOOD = FIXTURES / "depreciation-evidence-lumbridge.json"
UNRECONCILED = FIXTURES / "depreciation-evidence-unreconciled.json"

# 120,000.00 over five years on a prime-cost basis, 92 days of a 365-day year.
ANNUAL = Decimal("24000.00")
QUARTER = Decimal("6049.32")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the depreciation scenario opened a socket")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def months():
    return pd.period_range("2026-10", periods=3, freq="M")


def test_the_committed_fixtures_are_fabricated():
    for path in (GOOD, UNRECONCILED):
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["calculation"]["synthetic_input"] is True, path.name


def test_the_fixture_charge_is_the_arithmetic_it_claims():
    """Derived here, not read back from the file that asserts it."""
    charge = (ANNUAL * Decimal(92) / Decimal(365)).quantize(Decimal("0.01"))
    assert charge == QUARTER
    evidence = dep.load_evidence(GOOD)
    assert evidence.charge == QUARTER
    assert evidence.opening == Decimal("120000.00") - QUARTER
    assert evidence.closing == evidence.opening - QUARTER


def test_evidence_loads_with_its_provenance_and_advisory():
    evidence = dep.load_evidence(GOOD)
    assert evidence.usable is True
    assert evidence.calculator == "urn:sbrm:calculator:depreciation:range"
    assert len(evidence.calculation_sha256) == 64
    assert any("not a deduction under" in note for note in evidence.advisory_notes)


def test_a_tampered_file_is_refused(tmp_path):
    record = json.loads(GOOD.read_text(encoding="utf-8"))
    record["calculation"]["normalised"]["values"]["range_dep"] = "1.00"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(dep.DepreciationEvidenceError, match="does not match"):
        dep.load_evidence(path)


def test_a_json_number_for_money_is_refused(tmp_path):
    import hashlib

    record = json.loads(GOOD.read_text(encoding="utf-8"))
    record["calculation"]["normalised"]["values"]["range_dep"] = 6049.32
    record["calculation_sha256"] = hashlib.sha256(
        json.dumps(record["calculation"], sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()
    path = tmp_path / "float.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(dep.DepreciationEvidenceError, match="not a decimal string"):
        dep.load_evidence(path)


def test_an_unknown_schema_is_refused(tmp_path):
    record = json.loads(GOOD.read_text(encoding="utf-8"))
    record["schema"] = "something-else/2"
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(dep.DepreciationEvidenceError, match="not one this pack reads"):
        dep.load_evidence(path)


def test_the_movement_closes():
    evidence = dep.load_evidence(GOOD)
    assert evidence.opening is not None
    assert evidence.charge is not None
    assert evidence.closing is not None
    check = dep.asset_movement(
        opening=evidence.opening, additions=Decimal("0.00"),
        depreciation=evidence.charge, closing=evidence.closing,
    )
    assert check.closes is True
    assert check.gap == Decimal("0.00")
    assert check.reasons == ()


def test_an_unreconciled_movement_is_refused_and_nothing_is_derived():
    evidence = dep.load_evidence(UNRECONCILED)
    assert evidence.usable is False, "a contract failure carries no figure"
    check = dep.asset_movement(
        opening=Decimal("0.00"), additions=Decimal("0.00"),
        depreciation=QUARTER, closing=Decimal("120000.00") - QUARTER,
    )
    assert check.closes is False
    assert check.gap == Decimal("120000.00")
    assert any("No addition has been derived" in reason for reason in check.reasons)


def test_a_separately_evidenced_addition_closes_it():
    check = dep.asset_movement(
        opening=Decimal("0.00"), additions=Decimal("120000.00"),
        depreciation=QUARTER, closing=Decimal("120000.00") - QUARTER,
    )
    assert check.closes is True


def test_a_refusal_cannot_be_spread_across_months():
    evidence = dep.load_evidence(UNRECONCILED)
    with pytest.raises(dep.DepreciationEvidenceError, match="not a nil amount"):
        dep.straight_line_schedule(evidence, months())


def test_the_charge_spreads_evenly_and_sums_back(tmp_path):
    schedule = dep.straight_line_schedule(dep.load_evidence(GOOD), months())
    assert len(schedule) == 3
    assert round(schedule.sum(), 2) == float(QUARTER)
    assert schedule.index.equals(months())


def test_expense_and_purchases_stay_apart():
    schedule = dep.straight_line_schedule(dep.load_evidence(GOOD), months())
    purchases = pd.Series([120000.0, 0.0, 0.0], index=months())
    frame = dep.cash_and_expense(schedule, purchases)
    # The charge moves no cash, and the purchase moves no profit.
    assert frame["cash_effect"].tolist() == [-120000.0, 0.0, 0.0]
    assert round(frame["profit_effect"].sum(), 2) == -float(QUARTER)
    assert frame["asset_purchases"].sum() == 120000.0
    assert frame["depreciation_expense"].sum() != frame["asset_purchases"].sum()


def test_with_no_purchases_the_cash_effect_is_nil():
    frame = dep.cash_and_expense(dep.straight_line_schedule(dep.load_evidence(GOOD), months()))
    assert frame["cash_effect"].tolist() == [0.0, 0.0, 0.0]
    assert frame["depreciation_expense"].sum() > 0


def test_the_module_produces_no_tax_figure():
    """There is no tax function here, and the advisory says why."""
    assert not [name for name in dir(dep) if "tax" in name.lower() or "division40" in name.lower()]
    evidence = dep.load_evidence(GOOD)
    assert any("Division 40" in note for note in evidence.advisory_notes)
