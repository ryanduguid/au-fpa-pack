import runpy

import pytest

from pyfpa.io.pl_csv import read_pl_csv
from pyfpa.memory.connectors import _connector_module
from pyfpa.memory.lineage import MappingRegistry, MappingRule, reconcile_account_table


@pytest.fixture(params=["pl", "connector", "reconciliation"])
def read_values(request, tmp_path):
    if request.param == "pl":
        return read_pl_csv
    if request.param == "reconciliation":
        def reconcile(path):
            mappings = MappingRegistry(mappings=[
                MappingRule(source_id="fabricated", source_value=name, target=name)
                for name in ("Sales", "Cost")
            ])
            result = reconcile_account_table(
                path, source_id="fabricated", mappings=mappings,
                account_column="Account", amount_column="Amount")
            assert result["passed"]
            return result["mapped_totals"]
        return reconcile
    module = tmp_path / "connector.py"
    module.write_text(_connector_module(account_column="Account", amount_column="Amount"), encoding="utf-8")
    return runpy.run_path(str(module))["normalize_fixture"]


@pytest.mark.parametrize("body, message", [
    ("Account,Amount\n,999\n", "missing account"),
    ("Account,Amount\n ,0\n", "missing account"),
    ("Account,Amount\n,NaN\n", "missing account"),
    ("Account,Amount\nSales,1,234\n", "extra fields"),
    ("Account,Amount\nSales,1,\n", "extra fields"),
    ("Account,Amount,Amount\nSales,100,200\n", "duplicate.*columns"),
    ("Account,Account,Amount\nSales,Rent,100\n", "duplicate.*columns"),
])
def test_ambiguous_rows_are_refused_instead_of_losing_values(tmp_path, read_values, body, message):
    path = tmp_path / "ambiguous.csv"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        read_values(path)


def test_blank_rows_and_declared_extra_columns_keep_valid_amounts(tmp_path, read_values):
    path = tmp_path / "valid.csv"
    path.write_text('Account,Amount,Note\n,,\n  , , \nSales,"1,234",Fabricated\nCost,(34),\n', encoding="utf-8")
    assert read_values(path) == {"Sales": 1234.0, "Cost": -34.0}
