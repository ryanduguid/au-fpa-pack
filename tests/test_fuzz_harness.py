"""Replay the fuzz seed corpus so a broken harness fails ordinary CI."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fuzz import xero_import  # noqa: E402

SEEDS = sorted((ROOT / "fuzz" / "corpus").iterdir())


def test_the_corpus_is_not_empty() -> None:
    assert SEEDS


@pytest.mark.parametrize("seed", SEEDS, ids=lambda seed: seed.name)
def test_seed_replays_cleanly(seed: Path) -> None:
    xero_import.test_one_input(seed.read_bytes())


def test_a_non_finite_amount_is_caught() -> None:
    with mock.patch.object(xero_import, "read_pl_csv", return_value={"Sales": float("nan")}):
        with pytest.raises(AssertionError, match="non-finite amount"):
            xero_import.test_one_input(b"")


def test_unexpected_importer_errors_escape() -> None:
    with mock.patch.object(xero_import, "read_xero_report", side_effect=TypeError("bug")):
        with pytest.raises(TypeError, match="bug"):
            xero_import.test_one_input(b"")
