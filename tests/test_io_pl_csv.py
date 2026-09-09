from pathlib import Path

import pytest

from pyfpa.io.pl_csv import read_pl_csv

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_read_pl_csv_parses_amounts(tmp_path):
    csv_path = tmp_path / "pl.csv"
    csv_path.write_text(
        "Account,Amount\n"
        'Revenue,"$6,000,000"\n'
        'COGS,"($2,940,000)"\n'
        "Blank,\n"
        ",999\n"  # blank account -> skipped
    )
    result = read_pl_csv(csv_path)
    assert result["Revenue"] == 6_000_000.0
    assert result["COGS"] == -2_940_000.0
    assert result["Blank"] == 0.0
    assert "" not in result  # blank-account row skipped


def test_read_pl_csv_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        read_pl_csv(REPO_ROOT / "examples/nope.csv")


def test_read_pl_csv_bad_columns_raises(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Name,Value\nx,1\n")
    with pytest.raises(ValueError):
        read_pl_csv(bad)


def test_read_ridgeline_sample():
    result = read_pl_csv(REPO_ROOT / "examples/ridgeline/quickbooks_pl_sample.csv")
    assert result["Product Revenue"] == 6_000_000.0
    assert result["Cost of Goods Sold"] == -2_940_000.0


def test_duplicate_accounts_raise(tmp_path):
    path = tmp_path / "duplicate.csv"
    path.write_text("Account,Amount\nRevenue,100\nRevenue,200\n")

    with pytest.raises(ValueError, match="duplicate account"):
        read_pl_csv(path)


@pytest.mark.parametrize("row", ["Sales", "Sales,NaN", "Sales,inf", "Sales,-inf", "Sales,1e309"])
def test_read_pl_csv_rejects_missing_or_nonfinite_amounts(tmp_path, row):
    path = tmp_path / "invalid.csv"
    path.write_text(f"Account,Amount\n{row}\n")
    with pytest.raises(ValueError, match="amount"):
        read_pl_csv(path)


@pytest.mark.parametrize("amount", ["0", "-", "", "  "])
def test_read_pl_csv_preserves_supported_zero_notation(tmp_path, amount):
    path = tmp_path / "zero.csv"
    path.write_text(f"Account,Amount\nSales,{amount}\n")
    assert read_pl_csv(path) == {"Sales": 0.0}


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
def test_read_pl_csv_accepts_utf8_with_or_without_bom(tmp_path, encoding):
    path = tmp_path / "utf8.csv"
    path.write_text("Account,Amount\nCafé,100\n", encoding=encoding)
    assert read_pl_csv(path) == {"Café": 100.0}
