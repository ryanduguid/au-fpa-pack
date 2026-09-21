"""The close handoff must tie to the forecast's exact source balances."""
import csv
import json
import runpy
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "examples/lumbridge-services"
HANDOFF = runpy.run_path(str(ROOT / "models/generated/close_handoff.py"))["handoff"]


def test_balances_and_identity_survive_the_handoff(tmp_path):
    output = tmp_path / "handoff"
    result = HANDOFF(output)
    assert result["opening_receivables"] == str((40000 + 4000) + (20000 + 2000))
    for name in ("prior", "current"):
        with (output / f"{name}.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert sum(Decimal(row["Debit"]) - Decimal(row["Credit"]) for row in rows) == 0
        assert sum(Decimal(row["YTDDebit"]) - Decimal(row["YTDCredit"]) for row in rows) == 0
        assert {row["Tenant"] for row in rows} == {"Lumbridge Services"}
        assert next(row for row in rows if row["AccountID"] == "BS-090")["AccountCode"] == "090"
    assert json.loads((output / "handoff.json").read_text())["source_sha256"] == result["source_sha256"]
    with pytest.raises(FileExistsError):
        HANDOFF(output)


def test_changed_invoice_is_not_silently_used(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data", data)
    path = data / "invoices.csv"
    path.write_text(path.read_text().replace("40000,4000", "40001,4000", 1))
    output = tmp_path / "handoff"
    with pytest.raises(ValueError, match="does not tie"):
        HANDOFF(output, data)
    assert not output.exists()
