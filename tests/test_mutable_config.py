from collections.abc import Callable

import pandas as pd
import pytest
from pydantic import ValidationError

from pyfpa.config.schemas import EntityConfig, IncomeTaxConfig
from pyfpa.excel.model_workbook import model_to_excel
from pyfpa.excel.verify import verify_workbook
from pyfpa.models.cashflow import cashflow_from_config
from pyfpa.models.cogs import cogs_from_config
from pyfpa.models.debt import debt_from_config
from pyfpa.models.opex import opex_from_config
from pyfpa.models.revenue import revenue_from_config
from pyfpa.models.working_capital import working_capital_from_config


@pytest.fixture
def cfg():
    return EntityConfig.model_validate({
        "name": "Fabricated", "start_month": "2026-07", "horizon_months": 24,
        "tax_rate": 0.25,
        "channels": [
            {"name": "A", "annual_revenue": 1200, "seasonality": [1] * 12, "cogs_pct": 0.2},
            {"name": "B", "annual_revenue": 2400, "seasonality": [1] * 12, "cogs_pct": 0},
        ],
        "opex": [
            {"name": "Cost A", "kind": "fixed", "monthly_amount": 10},
            {"name": "Cost B", "kind": "fixed", "monthly_amount": 20},
        ],
        "debt": [{"name": "Loan", "kind": "term_loan", "opening_balance": 120,
                  "annual_rate": 0.1, "monthly_principal": 10}],
        "working_capital": {"dso_days": 0, "dpo_days": 0, "dio_days": 0},
    })


def mutate(cfg, case):
    if case.startswith("channel_name:"):
        cfg.channels[0].name = case.split(":", 1)[1]
    elif case.startswith("opex_name:"):
        cfg.opex[0].name = case.split(":", 1)[1]
    elif case == "channel_duplicate":
        cfg.channels[1].name = "a"
    elif case == "opex_duplicate":
        cfg.opex[1].name = "cost a"
    elif case == "append_duplicate":
        cfg.channels.append(cfg.channels[0])
    elif case == "root_copy":
        return cfg.model_copy(update={"channels": [cfg.channels[0], cfg.channels[0]]})
    elif case == "nested_copy":
        cfg.channels[0] = cfg.channels[0].model_copy(update={"name": "total"})
    elif case == "root_extra":
        return cfg.model_copy(update={"unexpected": 1})
    elif case == "nested_extra":
        cfg.channels[0] = cfg.channels[0].model_copy(update={"unexpected": 1})
    elif case == "missing_default":
        del cfg.capex_monthly
    elif case == "missing_nested":
        del cfg.channels[0].growth_rate
    elif case == "empty_channels":
        cfg.channels.clear()
    elif case == "weights_length":
        cfg.channels[0].seasonality.pop()
    elif case == "weights_zero":
        cfg.channels[0].seasonality[:] = [0] * 12
    elif case == "weights_negative":
        cfg.channels[0].seasonality[0] = -1
    elif case == "weights_nan":
        cfg.channels[0].seasonality[0] = float("nan")
    elif case == "cogs_pct":
        cfg.channels[0].cogs_pct = 1.1
    elif case == "tax_rate":
        cfg.tax_rate = float("nan")
    elif case == "working_capital":
        cfg.working_capital.dso_days = -1
    elif case == "receivables_conflict":
        cfg.working_capital.collection_profile = [1]
    elif case == "payment_nan":
        cfg.income_tax = IncomeTaxConfig()
        cfg.income_tax.payments["2026-07"] = float("nan")
    elif case == "payment_month":
        cfg.income_tax = IncomeTaxConfig(payments={"2030-01": 1})
    elif case == "debt_duplicate":
        cfg.debt.append(cfg.debt[0].model_copy(update={"name": "loan"}))
    elif case == "nested_none":
        return cfg.model_copy(update={"working_capital": None})
    else:
        raise AssertionError(case)
    return cfg


INVALID = [
    "channel_name:total", "channel_name: Total ", "channel_name: ",
    "opex_name:total", "opex_name: Total ", "opex_name:",
    "channel_duplicate", "opex_duplicate", "append_duplicate", "root_copy",
    "nested_copy", "root_extra", "nested_extra", "missing_default", "missing_nested",
    "empty_channels", "weights_length", "weights_zero", "weights_negative", "weights_nan",
    "cogs_pct", "tax_rate", "working_capital", "receivables_conflict", "payment_nan",
    "payment_month", "debt_duplicate", "nested_none",
]


@pytest.mark.parametrize("case", INVALID)
def test_forecast_revalidates_current_state(cfg, case):
    invalid = mutate(cfg, case)
    with pytest.raises(ValueError):
        cashflow_from_config(invalid)


@pytest.mark.parametrize("case", INVALID)
@pytest.mark.parametrize("existing", [False, True])
def test_export_refuses_invalid_state_without_touching_destination(cfg, case, existing, tmp_path):
    invalid = mutate(cfg, case)
    destination = tmp_path / "model.xlsx"
    original = b"existing destination must survive"
    if existing:
        destination.write_bytes(original)
    with pytest.raises(ValueError):
        model_to_excel(invalid, destination)
    assert destination.read_bytes() == original if existing else not destination.exists()


BUILDERS: list[Callable[..., pd.DataFrame]] = [
    revenue_from_config, cogs_from_config, opex_from_config, debt_from_config,
    working_capital_from_config, cashflow_from_config,
]


@pytest.mark.parametrize("builder", BUILDERS, ids=lambda builder: builder.__name__)
def test_every_public_builder_checks_fields_outside_its_calculation(cfg, builder):
    revenue = revenue_from_config(cfg)
    cogs = cogs_from_config(cfg, revenue)
    cfg.tax_rate = float("nan")
    args = (cfg, revenue, cogs) if builder is working_capital_from_config else (
        (cfg, revenue) if builder in (cogs_from_config, opex_from_config) else (cfg,)
    )
    with pytest.raises(ValidationError):
        builder(*args)


def test_valid_numeric_edit_preserves_all_workbook_lines(cfg, tmp_path):
    cfg.channels[0].cogs_pct = 0.5
    forecast = cashflow_from_config(cfg)
    assert forecast["revenue"].iloc[0] == 300
    assert forecast["cogs"].iloc[0] == 50
    assert forecast["opex"].iloc[0] == 30
    path = tmp_path / "valid.xlsx"
    model_to_excel(cfg, path)
    report = verify_workbook(path, forecast)
    assert report.passed, report.failures
    assert report.lines_checked == 17


def test_valid_edits_and_shared_lists_preserve_schema_canonicalisation(cfg):
    shared = [1.0] * 12
    cfg.channels[0].name = " Services "
    cfg.channels[0].seasonality = shared
    cfg.channels[1].seasonality = shared
    cfg.channels[1].growth_rate = 0.1
    cfg.opex[0].name = " New cost "
    cfg.channels.append(cfg.channels[0].model_copy(update={"name": "C"}))
    cfg.working_capital.dso_days = 10
    forecast = cashflow_from_config(cfg)
    revenue = revenue_from_config(cfg)
    costs = opex_from_config(cfg, revenue)
    assert list(revenue.columns) == ["Services", "B", "C", "total"]
    assert list(costs.columns) == ["New cost", "Cost B", "total"]
    assert forecast["revenue"].iloc[0] == 400
    assert forecast["revenue"].iloc[12] == pytest.approx(420)
    assert cfg.channels[0].name == " Services "
    assert cfg.opex[0].name == " New cost "
    assert cfg.channels[0].seasonality is shared
    assert cfg.channels[1].seasonality is shared


def test_cogs_accepts_external_frame_using_current_uncanonicalised_channel_name(cfg):
    cfg.channels[0].name = " A "
    canonical = revenue_from_config(cfg)
    external = canonical.rename(columns={"A": " A "})
    expected = cogs_from_config(cfg, canonical)
    pd.testing.assert_frame_equal(cogs_from_config(cfg, external), expected)
    assert list(external.columns) == [" A ", "B", "total"]
    assert cfg.channels[0].name == " A "


def test_cogs_prefers_canonical_frame_column_when_both_names_exist(cfg):
    cfg.channels[0].name = " A "
    canonical = revenue_from_config(cfg)
    external = canonical.assign(**{" A ": canonical["A"] * 10})
    pd.testing.assert_frame_equal(cogs_from_config(cfg, external),
                                  cogs_from_config(cfg, canonical))


def test_export_uses_one_snapshot_after_engine_preflight(cfg, tmp_path, monkeypatch):
    from pyfpa.excel import model_workbook

    expected = cashflow_from_config(cfg)
    real_preflight = cashflow_from_config

    def preflight(snapshot):
        result = real_preflight(snapshot)
        cfg.channels[0].name = "total"
        cfg.channels[0].annual_revenue = 9999
        return result

    monkeypatch.setattr(model_workbook, "cashflow_from_config", preflight)
    path = tmp_path / "snapshot.xlsx"
    model_to_excel(cfg, path)
    report = verify_workbook(path, expected)
    assert report.passed, report.failures


@pytest.mark.parametrize("location", ["root", "nested", "payments"])
def test_current_state_cycles_fail_normally(cfg, location):
    if location == "root":
        cfg.__dict__["channels"] = [cfg]
    elif location == "nested":
        cfg.channels[0].__dict__["seasonality"] = [cfg.channels[0]]
    else:
        cfg.income_tax = IncomeTaxConfig()
        cfg.income_tax.payments["2026-07"] = cfg.income_tax.payments
    with pytest.raises(ValueError, match="configuration contains a cycle"):
        cashflow_from_config(cfg)


@pytest.mark.parametrize("extra", [{"unexpected": 1}, {"tax_rate": 0.3}, ["unexpected"]])
def test_extra_storage_cannot_discard_or_override_current_fields(cfg, extra):
    object.__setattr__(cfg, "__pydantic_extra__", extra)
    with pytest.raises(ValueError):
        cashflow_from_config(cfg)


def test_nested_subclass_fields_remain_visible_to_schema(cfg):
    from pyfpa.config.schemas import Channel

    class ExtendedChannel(Channel):
        unexpected: int = 1

    cfg.channels[0] = ExtendedChannel(**cfg.channels[0].model_dump())
    with pytest.raises(ValidationError, match="unexpected"):
        cashflow_from_config(cfg)


def test_valid_unchecked_tuple_copy_remains_supported(cfg):
    copied = cfg.model_copy(update={"channels": tuple(cfg.channels)})
    pd.testing.assert_frame_equal(cashflow_from_config(copied), cashflow_from_config(cfg))


def test_valid_reusable_range_mutation_remains_supported(cfg):
    cfg.channels[0].seasonality = list(range(1, 13))
    expected = cashflow_from_config(cfg)
    cfg.channels[0].seasonality = range(1, 13)
    pd.testing.assert_frame_equal(cashflow_from_config(cfg), expected)
    assert cfg.channels[0].seasonality == range(1, 13)


def test_unchecked_iterator_is_refused_before_consumption(cfg):
    channels = iter(cfg.channels)
    copied = cfg.model_copy(update={"channels": channels})
    with pytest.raises(ValueError, match="unsupported iterable"):
        cashflow_from_config(copied)
    assert next(channels) is cfg.channels[0]
