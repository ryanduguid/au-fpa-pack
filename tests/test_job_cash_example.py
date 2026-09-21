"""The file handoff retains cash timing and rejects altered assumptions."""
import hashlib
import json
import runpy
from pathlib import Path

import pytest

PROJECT = runpy.run_path(str(Path(__file__).parents[1] / "examples/job-to-cash/project_cash.py"))["project"]


@pytest.fixture
def pack(tmp_path):
    content = ("id,date,receipt,payment,evidence\n"
               "ordinary,2026-10-15,145500,0,certificate less retention less collected\n"
               "cost,2026-11-15,0,440000,remaining cost cash assumption\n"
               "retention,2027-02-28,49500,0,conditional release assumption\n").encode()
    (tmp_path / "cash-assumptions.csv").write_bytes(content)
    (tmp_path / "job-to-cash.json").write_text(json.dumps({
        "currency": "AUD", "cash_assumptions_sha256": hashlib.sha256(content).hexdigest(),
        "as_at": "2026-09-30", "contract_id": "fabricated-contract", "cash_to_date": "-140000",
    }), encoding="utf-8")
    return tmp_path


def test_retention_does_not_enter_the_current_horizon(pack):
    result = PROJECT(pack)
    assert len(result["weeks"]) == 13
    assert result["weeks"][-1]["ending_cash"] == -140000 + 145500 - 440000
    assert result["outside_horizon"] == [{"id": "retention", "date": "2027-02-28", "receipt": 49500, "payment": 0}]


def test_changed_cash_file_is_refused(pack):
    with (pack / "cash-assumptions.csv").open("ab") as stream:
        stream.write(b"extra,2026-10-01,1,0,unreviewed\n")
    with pytest.raises(ValueError, match="does not match"):
        PROJECT(pack)


@pytest.mark.parametrize("value", ["nan", "inf", "-1"])
def test_non_cash_amounts_are_refused_even_with_matching_digest(pack, value):
    path = pack / "cash-assumptions.csv"
    content = path.read_bytes().replace(b"145500", value.encode())
    path.write_bytes(content)
    evidence_path = pack / "job-to-cash.json"
    evidence = json.loads(evidence_path.read_text())
    evidence["cash_assumptions_sha256"] = hashlib.sha256(content).hexdigest()
    evidence_path.write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match="finite"):
        PROJECT(pack)
