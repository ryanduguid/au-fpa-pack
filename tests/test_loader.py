import sys
from pathlib import Path
from unittest import mock

import pytest
import yaml
from pydantic import ValidationError
from yaml.constructor import ConstructorError, SafeConstructor

from pyfpa.config.loader import load_config
from pyfpa.config.schemas import (
    Channel,
    DebtInstrument,
    EntityConfig,
    OpeningBalances,
    OpexLine,
    WorkingCapitalConfig,
)


def _minimal_kwargs():
    return {
        "name": "X",
        "start_month": "2026-01",
        "tax_rate": 0.30,
        "channels": [Channel(name="D2C", annual_revenue=1200.0,
                             seasonality=[1.0] * 12, cogs_pct=0.5)],
        "working_capital": WorkingCapitalConfig(dso_days=30, dpo_days=30, dio_days=0),
    }


def test_entity_config_defaults():
    cfg = EntityConfig(**_minimal_kwargs())
    assert cfg.horizon_months == 12
    assert cfg.opening_balances.cash == 0.0


def test_a_config_without_a_tax_rate_is_refused():
    """No default fits: 0.21 was the US federal rate, and an Australian company
    pays 25% or 30% depending on base rate entity status."""
    kwargs = _minimal_kwargs()
    del kwargs["tax_rate"]
    with pytest.raises(ValidationError, match="tax_rate"):
        EntityConfig(**kwargs)


def test_seasonality_must_be_twelve():
    with pytest.raises(ValidationError):
        Channel(name="D2C", annual_revenue=1.0, seasonality=[1.0] * 11, cogs_pct=0.5)


def test_cogs_pct_bounded():
    with pytest.raises(ValidationError):
        Channel(name="D2C", annual_revenue=1.0, seasonality=[1.0] * 12, cogs_pct=1.5)


def test_bad_start_month_rejected():
    kwargs = _minimal_kwargs() | {"start_month": "not-a-month"}
    with pytest.raises(ValidationError):
        EntityConfig(**kwargs)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_load_ridgeline_config():
    cfg = load_config(REPO_ROOT / "examples/ridgeline/config.yaml")
    assert cfg.name == "Ridgeline Chair Co."
    assert len(cfg.channels) == 3
    assert cfg.horizon_months == 12


def test_load_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config(REPO_ROOT / "examples/does_not_exist.yaml")


def test_channel_name_total_rejected():
    with pytest.raises(ValidationError):
        Channel(name="total", annual_revenue=1.0, seasonality=[1.0] * 12, cogs_pct=0.5)


def test_opex_name_total_rejected():
    from pyfpa.config.schemas import OpexLine
    with pytest.raises(ValidationError):
        OpexLine(name="Total", kind="fixed", monthly_amount=1.0)


def test_duplicate_channel_names_rejected():
    kwargs = _minimal_kwargs()
    kwargs["channels"] = [
        Channel(name="D2C", annual_revenue=1.0, seasonality=[1.0] * 12, cogs_pct=0.5),
        Channel(name="d2c", annual_revenue=2.0, seasonality=[1.0] * 12, cogs_pct=0.5),
    ]
    with pytest.raises(ValidationError, match="channels names must be unique"):
        EntityConfig(**kwargs)


def test_growth_cannot_reduce_revenue_below_zero():
    with pytest.raises(ValidationError):
        Channel(
            name="D2C",
            annual_revenue=1.0,
            growth_rate=-1.0,
            seasonality=[1.0] * 12,
            cogs_pct=0.5,
        )


_MISSPELLABLE_YAML = """
name: Two Year Co.
start_month: 2026-01
horizon_months: 24
tax_rate: 0.0
channels:
  - name: Wholesale
    annual_revenue: 1200.0
    {growth_key}: 0.10
    seasonality: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
    cogs_pct: 0.5
opex: []
debt: []
working_capital:
  dso_days: 0
  dpo_days: 0
  dio_days: 0
opening_balances:
  cash: 0
"""


def test_misspelt_optional_field_is_rejected(tmp_path):
    # F077: growth_rtae used to load silently, leaving the channel at zero
    # growth while the config looked applied.
    path = tmp_path / "misspelt.yaml"
    path.write_text(_MISSPELLABLE_YAML.format(growth_key="growth_rtae"), encoding="utf-8")
    with pytest.raises(ValidationError, match="growth_rtae"):
        load_config(path)


def test_correctly_named_optional_field_still_applies(tmp_path):
    # Control: the same config under the real field name grows year 2 by 10%.
    from pyfpa.models.revenue import revenue_from_config

    path = tmp_path / "correct.yaml"
    path.write_text(_MISSPELLABLE_YAML.format(growth_key="growth_rate"), encoding="utf-8")
    cfg = load_config(path)
    revenue = revenue_from_config(cfg)["total"]
    assert round(float(revenue.iloc[:12].sum())) == 1200
    assert round(float(revenue.iloc[12:].sum())) == 1320


def test_unknown_top_level_key_is_rejected(tmp_path):
    path = tmp_path / "extra.yaml"
    path.write_text(
        _MISSPELLABLE_YAML.format(growth_key="growth_rate") + "tax_ratee: 0.3\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="tax_ratee"):
        load_config(path)


@pytest.mark.parametrize("value", ["2026", "2026-1", "2026-13", "January 2026", "2026-01-15"])
def test_start_month_requires_the_exact_format(value: str) -> None:
    # pd.Period parses far more than YYYY-MM, and month_index read "2026" as January
    # 2026, so a malformed value selected a different start period instead of failing.
    with pytest.raises(ValidationError):
        EntityConfig(**{**_minimal_kwargs(), "start_month": value})


def test_start_month_still_accepts_the_documented_format() -> None:
    assert EntityConfig(**{**_minimal_kwargs(), "start_month": "2026-07"}).start_month == "2026-07"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("model,valid,fields", [
    (Channel, {"name": "Sales", "annual_revenue": 1200, "seasonality": [1.0] * 12,
               "cogs_pct": 0.5}, ("annual_revenue", "growth_rate", "cogs_pct")),
    (OpexLine, {"name": "Rent", "kind": "fixed"}, ("monthly_amount", "pct_of_revenue")),
    (DebtInstrument, {"name": "Loan", "kind": "term_loan", "opening_balance": 100,
                      "annual_rate": 0.05}, ("opening_balance", "annual_rate", "monthly_principal")),
    (WorkingCapitalConfig, {"dso_days": 0, "dpo_days": 0, "dio_days": 0},
     ("dso_days", "dpo_days", "dio_days")),
    (OpeningBalances, {}, ("cash", "ar", "ap", "inventory", "nol")),
    (EntityConfig, _minimal_kwargs(), ("tax_rate", "da_monthly", "capex_monthly")),
])
def test_config_models_reject_non_finite_numbers(model, valid, fields, value):
    for field in fields:
        with pytest.raises(ValidationError) as error:
            model.model_validate({**valid, field: value})
        assert error.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("position", [0, 11])
def test_seasonality_rejects_non_finite_items(value, position):
    weights = [1.0] * 12
    weights[position] = value
    with pytest.raises(ValidationError):
        Channel(name="Sales", annual_revenue=1200, seasonality=weights, cogs_pct=0.5)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("field", ["opening_balances", "channels"])
def test_raw_nested_config_rejects_non_finite_numbers(value, field):
    raw = EntityConfig(**_minimal_kwargs()).model_dump()
    if field == "opening_balances":
        raw[field]["cash"] = value
    else:
        raw[field][0]["seasonality"][0] = value
    with pytest.raises(ValidationError) as error:
        EntityConfig.model_validate(raw)
    assert error.value.errors()[0]["loc"][0] == field


@pytest.mark.parametrize("value", [".nan", ".inf", "-.inf"])
def test_yaml_non_finite_numbers_are_rejected(tmp_path, value):
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace("cash: 0", f"cash: {value}")
    path = tmp_path / "non-finite.yaml"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(ValidationError) as error:
        load_config(path)
    assert error.value.errors()[0]["loc"] == ("opening_balances", "cash")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e10000"])
def test_text_cannot_coerce_to_a_non_finite_balance(value):
    with pytest.raises(ValidationError):
        OpeningBalances(cash=value)


@pytest.mark.parametrize("value", [0.0, -50.0, 50.0, sys.float_info.max, -sys.float_info.max])
def test_finite_opening_balances_keep_their_existing_range(value):
    assert OpeningBalances(cash=value).cash == value


@pytest.mark.parametrize("value", [0.0, 1200.0, sys.float_info.max])
def test_finite_revenue_has_no_new_ceiling(value):
    channel = Channel(name="Sales", annual_revenue=value, seasonality=[1.0] * 12, cogs_pct=0.5)
    assert channel.annual_revenue == value


@pytest.mark.parametrize("original,replacement,key", [
    ("growth_rate: 0.10", "growth_rate: 0.10\n    growth_rate: 0.0", "growth_rate"),
    ("growth_rate: 0.10", 'growth_rate: 0.10\n    "growth_rate": 0.0', "growth_rate"),
    ("growth_rate: 0.10", "growth_rate: 0.10\n    growth_rate: 0.10", "growth_rate"),
    ("cogs_pct: 0.5", "cogs_pct: 1.5\n    cogs_pct: 0.5", "cogs_pct"),
    ("cash: 0", "cash: .nan\n  cash: 0", "cash"),
    ("horizon_months: 24", "horizon_months: 24\nhorizon_months: 12", "horizon_months"),
    ("  - name: Wholesale\n    annual_revenue: 1200.0\n    growth_rate: 0.10\n"
     "    seasonality: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]\n    cogs_pct: 0.5",
     "  - {name: Wholesale, annual_revenue: 1200.0, growth_rate: 0.10, growth_rate: 0.0, "
     "seasonality: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], cogs_pct: 0.5}", "growth_rate"),
    ("growth_rate: 0.10", 'growth_rate: 0.10\n    "growth_\\u0072ate": 0.0', "growth_rate"),
    ("growth_rate: 0.10", "growth_rate: 0.10\n    !!str growth_rate: 0.0", "growth_rate"),
    ("growth_rate: 0.10", "&field growth_rate: 0.10\n    ? *field\n    : 0.0", "growth_rate"),
    ("growth_rate: 0.10", "<<: {growth_rate: 0.10, growth_rate: 0.0}\n    growth_rate: 0.10", "growth_rate"),
    ("growth_rate: 0.10", "<<: {growth_rate: 0.10}\n    <<: {growth_rate: 0.10}", "<<"),
    ("growth_rate: 0.10", "<<: {growth_rate: 0.10}\n    <<: {growth_rate: 0.0}", "<<"),
    ("growth_rate: 0.10", "<<: {growth_rate: 0.10}\n    <<: {cogs_pct: 0.5}", "<<"),
    ("growth_rate: 0.10", "!!merge '<<': {growth_rate: 0.10}\n    <<: {growth_rate: 0.0}", "<<"),
])
def test_duplicate_yaml_keys_fail_before_model_validation(tmp_path, original, replacement, key):
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate")
    assert original in source
    source = source.replace(original, replacement)
    path = tmp_path / "duplicate.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()
    with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
        with pytest.raises(ConstructorError, match=f"duplicate.*{key}"):
            load_config(path)
        validate.assert_not_called()
    assert path.read_bytes() == before


@pytest.mark.parametrize("growth_fields,growth", [
    ("<<: {growth_rate: 0.0}\n    growth_rate: 0.10", 0.10),
    ("growth_rate: 0.10\n    <<: {growth_rate: 0.0}", 0.10),
    ("<<: [{growth_rate: 0.10}, {growth_rate: 0.0}]", 0.10),
    ("<<: [{growth_rate: 0.0}, {growth_rate: 0.10}]", 0.0),
    ("<<: {<<: {growth_rate: 0.0}, growth_rate: 0.10}", 0.10),
    ("<<: {growth_rate: -2.0}\n    growth_rate: 0.10", 0.10),
])
def test_yaml_merge_precedence_matches_expanded_config(tmp_path, growth_fields, growth):
    from pyfpa.models.revenue import revenue_from_config

    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace("growth_rate: 0.10", growth_fields)
    path = tmp_path / "merged.yaml"
    path.write_text(source, encoding="utf-8")
    config = load_config(path)
    expanded = EntityConfig.model_validate(yaml.safe_load(source))
    assert config == expanded
    assert config.channels[0].growth_rate == growth
    assert revenue_from_config(config).equals(revenue_from_config(expanded))
    assert float(revenue_from_config(config)["total"].iloc[12:].sum()) == pytest.approx(1200 * (1 + growth))


def test_reused_merged_mappings_and_value_aliases_keep_record_scopes(tmp_path):
    from pyfpa.models.revenue import revenue_from_config

    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate")
    start, remainder = source.split("channels:\n", 1)
    _, rest = remainder.split("opex:", 1)
    source = start + """channels:
  - &first
    <<: {annual_revenue: 1200.0, growth_rate: 0.0, cogs_pct: 0.5}
    name: Wholesale
    growth_rate: &growth 0.10
    seasonality: &weights [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
  - <<: *first
    name: Retail
    growth_rate: *growth
    seasonality: *weights
opex:""" + rest
    path = tmp_path / "aliased.yaml"
    path.write_text(source, encoding="utf-8")
    config = load_config(path)
    expanded = EntityConfig.model_validate(yaml.safe_load(source))
    assert config == expanded
    assert [channel.name for channel in config.channels] == ["Wholesale", "Retail"]
    assert revenue_from_config(config).equals(revenue_from_config(expanded))
    assert float(revenue_from_config(config)["total"].iloc[12:].sum()) == pytest.approx(2640)


@pytest.mark.parametrize("prefix,key", [
    ("1: first\ntrue: second\n", "True"),
    ("=: first\n'=': second\n", "="),
])
def test_constructed_yaml_key_collisions_are_rejected(tmp_path, prefix, key):
    path = tmp_path / "collision.yaml"
    path.write_text(prefix + _MISSPELLABLE_YAML.format(growth_key="growth_rate"), encoding="utf-8")
    with pytest.raises(ConstructorError, match=f"duplicate.*{key}"):
        load_config(path)


@pytest.mark.parametrize("key", ['"<<"', "!!str '<<'", "="])
def test_literal_merge_and_value_keys_reach_normal_schema_validation(tmp_path, key):
    path = tmp_path / "literal.yaml"
    path.write_text(f"{key}: 0\n" + _MISSPELLABLE_YAML.format(growth_key="growth_rate"), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path)


@pytest.mark.parametrize("key", ["!!str {=: growth_rate}", "*field", "!!value {=: growth_rate}"])
def test_mapping_shaped_string_keys_preserve_safe_constructor_semantics(tmp_path, key):
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "name: Two Year Co.", "name: &field !!str {=: growth_rate}").replace(
        "    growth_rate: 0.10", f"    ? {key}\n    : 0.10")
    expected = EntityConfig.model_validate(yaml.safe_load(source))
    path = tmp_path / "scalar-key.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()

    assert load_config(path) == expected
    assert expected.channels[0].growth_rate == 0.10
    assert path.read_bytes() == before


@pytest.mark.parametrize("key", ["!!str {=: growth_rate}", "*field", "!!value {=: growth_rate}"])
def test_mapping_shaped_string_key_duplicates_fail_before_model_validation(tmp_path, key):
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "name: Two Year Co.", "name: &field !!str {=: growth_rate}").replace(
        "    growth_rate: 0.10", f"    ? {key}\n    : 0.10\n    growth_rate: 0.0")
    path = tmp_path / "duplicate-scalar-key.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()

    with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
        with pytest.raises(ConstructorError, match="duplicate.*growth_rate"):
            load_config(path)
        validate.assert_not_called()
    assert path.read_bytes() == before


@pytest.mark.parametrize("duplicate", [False, True], ids=["valid", "duplicate"])
def test_value_tag_alias_key_meaning_matches_inherited_construction(tmp_path, duplicate):
    first_result = "annotation_only" if duplicate else "growth_rate"
    actual_key = "growth_rate" if duplicate else "cogs_pct"
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "name: Two Year Co.",
        "name: &field !!str\n  ? &tax_key !!value {=: tax_rate}\n"
        f"  : {first_result}\n  =: {actual_key}",
    ).replace("tax_rate: 0.0", "? *tax_key\n: 0.0")
    source = source.replace(
        "    growth_rate: 0.10" if duplicate else "    cogs_pct: 0.5",
        "    ? *field\n    : 0.10\n    growth_rate: 0.0" if duplicate
        else "    ? *field\n    : 0.5",
    )
    expected = EntityConfig.model_validate(yaml.safe_load(source))
    assert expected.name == actual_key
    assert expected.channels[0].growth_rate == (0.0 if duplicate else 0.10)
    assert expected.channels[0].cogs_pct == 0.5
    path = tmp_path / "value-tag-alias.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()

    try:
        if duplicate:
            with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
                with pytest.raises(ConstructorError, match="duplicate.*growth_rate"):
                    load_config(path)
                validate.assert_not_called()
        else:
            assert load_config(path) == expected
    finally:
        assert path.read_bytes() == before


@pytest.mark.parametrize("duplicate", [False, True])
def test_alias_key_cached_before_selector_retagging_keeps_its_value(tmp_path, duplicate):
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "name: Two Year Co.",
        "name: &field !!str\n  ? &selector !!value {=: cogs_pct}\n"
        "  : growth_rate\n  =: annual_revenue",
    ).replace("    cogs_pct: 0.5", "    ? *selector\n    : 0.5").replace(
        "    growth_rate: 0.10", "    ? *field\n    : 0.10"
        + ("\n    growth_rate: 0.0" if duplicate else ""),
    )
    expected = EntityConfig.model_validate(yaml.safe_load(source))
    assert expected.name == "growth_rate"
    path = tmp_path / "cached-key.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()
    try:
        if duplicate:
            with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
                with pytest.raises(ConstructorError, match="duplicate.*growth_rate"):
                    load_config(path)
                validate.assert_not_called()
        else:
            assert load_config(path) == expected
            assert expected.channels[0].growth_rate == 0.10
    finally:
        assert path.read_bytes() == before


@pytest.mark.parametrize("duplicate", [False, True])
def test_failed_provisional_alias_comparison_uses_successful_inherited_key(tmp_path, duplicate):
    actual = "growth_rate" if duplicate else "cogs_pct"
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "name: Two Year Co.",
        "name: &field !!str\n  ? &selector !!value {=: tax_rate}\n"
        f"  : *field\n  =: {actual}",
    ).replace("tax_rate: 0.0", "? *selector\n: 0.0").replace(
        "    growth_rate: 0.10" if duplicate else "    cogs_pct: 0.5",
        "    ? *field\n    : 0.10\n    growth_rate: 0.0" if duplicate
        else "    ? *field\n    : 0.5",
    )
    expected = EntityConfig.model_validate(yaml.safe_load(source))
    path = tmp_path / "failed-comparison.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()
    try:
        if duplicate:
            with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
                with pytest.raises(ConstructorError, match="duplicate.*growth_rate"):
                    load_config(path)
                validate.assert_not_called()
        else:
            assert load_config(path) == expected
    finally:
        assert path.read_bytes() == before


@pytest.mark.parametrize("consumption", ["ignored", "value", "scalar selection"])
@pytest.mark.parametrize("other_key", ["old_key", "new_key"])
def test_uncached_alias_fallback_and_late_constructed_objects(tmp_path, consumption, other_key):
    # Scalar selection can inspect a node without caching its tagged object.
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "name: Two Year Co.",
        "name: !!str\n  ? &field !!str\n    ? &selector !!value {=: tax_rate}\n"
        "    : old_key\n    =: new_key\n  : ignored\n"
        f"  =: {'*field' if consumption == 'scalar selection' else 'company'}\n"
        f"  {other_key}: ignored",
    ).replace("tax_rate: 0.0", "? *selector\n: 0.0")
    if consumption == "value":
        source = source.replace("  - name: Wholesale", "  - name: *field")
    expected = EntityConfig.model_validate(yaml.safe_load(source))
    assert expected.name == ("new_key" if consumption == "scalar selection" else "company")
    path = tmp_path / "fallback.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()
    duplicate = other_key == ("new_key" if consumption == "value" else "old_key")
    try:
        if duplicate:
            with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
                with pytest.raises(ConstructorError, match=f"duplicate.*{other_key}"):
                    load_config(path)
                validate.assert_not_called()
        else:
            assert load_config(path) == expected
    finally:
        assert path.read_bytes() == before


@pytest.mark.parametrize("duplicate", [False, True])
def test_alias_key_in_uncached_merge_source_uses_actual_construction(tmp_path, duplicate):
    actual = "growth_rate" if duplicate else "cogs_pct"
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "name: Two Year Co.",
        "name: &field !!str\n  ? &selector !!value {=: tax_rate}\n"
        f"  : annotation_only\n  =: {actual}",
    ).replace("tax_rate: 0.0", "? *selector\n: 0.0")
    if duplicate:
        source = source.replace("    growth_rate: 0.10", "    <<:\n      ? *field\n      : 0.10\n      growth_rate: 0.0")
    else:
        source = source.replace("    cogs_pct: 0.5", "    <<:\n      ? *field\n      : 0.5")
    expected = EntityConfig.model_validate(yaml.safe_load(source))
    path = tmp_path / "merge-source.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()
    try:
        if duplicate:
            with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
                with pytest.raises(ConstructorError, match="duplicate.*growth_rate"):
                    load_config(path)
                validate.assert_not_called()
        else:
            assert load_config(path) == expected
    finally:
        assert path.read_bytes() == before


@pytest.mark.parametrize("collection", [
    "!!map [bad]", "!!seq {bad: ignored}", "!!set [bad]",
    "!!omap [{a: 1, b: 2}]", "!!pairs [{a: 1, b: 2}]",
])
@pytest.mark.parametrize("consumed", [False, True])
def test_optional_collection_audit_does_not_drain_generators(tmp_path, collection, consumed):
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "name: Two Year Co.",
        f"name: !!str\n  =: company\n  ? &bad {collection}\n  : ignored",
    )
    if consumed:
        source = source.replace("cash: 0", "cash: *bad")
        with pytest.raises(ConstructorError):
            yaml.safe_load(source)
    else:
        expected = EntityConfig.model_validate(yaml.safe_load(source))
    path = tmp_path / "collection.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()
    try:
        if consumed:
            with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
                with pytest.raises(ConstructorError):
                    load_config(path)
                validate.assert_not_called()
        else:
            assert load_config(path) == expected
    finally:
        assert path.read_bytes() == before


@pytest.mark.parametrize("failure,error_type,diagnostic", [
    ("\n? !!int bad\n: ignored\n", ValueError, "invalid literal"),
    ("\n? !!python/object:builtins.object {}\n: ignored\n", ConstructorError, "could not determine"),
    ("\n? [annotation]\n: ignored\n", ConstructorError, "unhashable key"),
    ("\nignored: {<<: 1}\n", ConstructorError, "expected a mapping"),
    ("\nignored: !!omap [{a: 1, b: 2}]\n", ConstructorError, "expected a single mapping item"),
])
def test_inherited_failure_precedes_duplicate_audit_and_model_validation(tmp_path, failure, error_type, diagnostic):
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "growth_rate: 0.10", "growth_rate: 0.10\n    growth_rate: 0.0",
    ) + failure
    with pytest.raises(error_type, match=diagnostic):
        yaml.safe_load(source)
    path = tmp_path / "construction-failure.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()
    with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
        with pytest.raises(error_type, match=diagnostic):
            load_config(path)
        validate.assert_not_called()
    assert path.read_bytes() == before


def test_unhashable_annotation_alias_consumed_as_valid_sequence_preserves_model(tmp_path):
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "name: Two Year Co.",
        "name: !!str\n  =: company\n"
        "  ? &weights [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]\n  : ignored",
    ).replace("seasonality: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]", "seasonality: *weights")
    expected = EntityConfig.model_validate(yaml.safe_load(source))
    path = tmp_path / "sequence-alias.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()
    assert load_config(path) == expected
    assert path.read_bytes() == before


def test_optional_constructor_allocation_errors_are_not_deferred(tmp_path, monkeypatch):
    monkeypatch.setattr("pyfpa.config.loader.SafeConstructor", mock.Mock(side_effect=ValueError("allocation fault")))
    path = tmp_path / "allocation.yaml"
    path.write_text(_MISSPELLABLE_YAML.format(growth_key="growth_rate"), encoding="utf-8")
    before = path.read_bytes()
    with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
        with pytest.raises(ValueError, match="allocation fault"):
            load_config(path)
        validate.assert_not_called()
    assert path.read_bytes() == before


def test_duplicate_audit_preserves_original_key_marks(tmp_path):
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "growth_rate: 0.10", "growth_rate: 0.10\n    growth_rate: 0.0",
    )
    graph = yaml.compose(source)
    channels = next(value for key, value in graph.value if key.value == "channels")
    keys = [key for key, _ in channels.value[0].value if key.value == "growth_rate"]
    path = tmp_path / "marked.yaml"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(ConstructorError, match="duplicate.*growth_rate") as error:
        load_config(path)
    assert error.value.context_mark is not None
    assert error.value.problem_mark is not None
    assert error.value.context_mark.line == keys[0].start_mark.line
    assert error.value.problem_mark.line == keys[1].start_mark.line
    assert error.value.context_mark.name == keys[0].start_mark.name
    assert error.value.problem_mark.name == keys[1].start_mark.name


_INVALID_YAML_KEYS = [
    ("[annotation]", ConstructorError),
    ("!unsupported annotation", ConstructorError),
    ("!!int bad", ValueError),
    ("!!bool bad", KeyError),
    ("!!int ''", IndexError),
    ("!!float ''", IndexError),
    ("!!timestamp bad", AttributeError),
    ("!!timestamp {=: 2026-01-01}", TypeError),
    ("!!binary '\u00e9'", ConstructorError),
    ("!!python/object:builtins.object {}", ConstructorError),
    ('!!float "' + ":".join(["1"] * 200) + '"', OverflowError),
    ("&cycle !!str {=: *cycle}", RecursionError),
]


@pytest.mark.parametrize("annotation_key,error_type", _INVALID_YAML_KEYS)
@pytest.mark.parametrize("duplicate", [False, True])
def test_string_scalar_annotations_preserve_safe_loading_and_outer_duplicates(
    tmp_path, annotation_key, error_type, duplicate,
):
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "name: Two Year Co.",
        f"name: &field !!str\n  =: growth_rate\n  ? {annotation_key}\n  : ignored",
    ).replace("    growth_rate: 0.10", "    ? *field\n    : 0.10")
    if duplicate:
        source = source.replace("    : 0.10", "    : 0.10\n    growth_rate: 0.0")
    expected = EntityConfig.model_validate(yaml.safe_load(source))
    path = tmp_path / "annotated-scalar.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()

    try:
        if duplicate:
            with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
                with pytest.raises(ConstructorError, match="duplicate.*growth_rate"):
                    load_config(path)
                validate.assert_not_called()
        else:
            assert load_config(path) == expected
            assert expected.channels[0].growth_rate == 0.10
    finally:
        assert path.read_bytes() == before


@pytest.mark.parametrize("key,error_type", _INVALID_YAML_KEYS)
def test_invalid_actual_yaml_keys_fail_before_model_validation(tmp_path, key, error_type):
    source = f"? {key}\n: ignored\n" + _MISSPELLABLE_YAML.format(growth_key="growth_rate")
    with pytest.raises(error_type):
        yaml.safe_load(source)
    path = tmp_path / "invalid-key.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()

    with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
        with pytest.raises(error_type):
            load_config(path)
        validate.assert_not_called()
    assert path.read_bytes() == before


@pytest.mark.parametrize("key,error_type,position", [
    (key, error_type, position)
    for key, error_type in _INVALID_YAML_KEYS
    for position in ("key", "value")
    if key != "[annotation]" or position == "key"
])
def test_invalid_annotation_aliases_fail_when_later_consumed(tmp_path, key, error_type, position):
    anchored = key.replace("&cycle", "&bad").replace("*cycle", "*bad") if "&cycle" in key else "&bad " + key
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "name: Two Year Co.",
        f"name: !!str\n  =: company\n  ? {anchored}\n  : ignored",
    ).replace("    growth_rate: 0.10", "    ? *bad\n    : 0.10" if position == "key" else "    growth_rate: *bad")
    with pytest.raises(error_type):
        yaml.safe_load(source)
    path = tmp_path / "consumed-annotation.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()

    with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
        with pytest.raises(error_type):
            load_config(path)
        validate.assert_not_called()
    assert path.read_bytes() == before


@pytest.mark.parametrize("annotation,key", [
    ("  note: first\n  ? !unsupported ignored\n  : ignored\n  note: second", "note"),
    ("  =: another", "="),
    ("  <<: {note: first}\n  <<: {other: second}", "<<"),
    ("  note: {field: first, field: second}", "field"),
    ("  ? [{field: first, field: second}]\n  : ignored", "field"),
    ("  ? !unsupported {field: first, field: second}\n  : ignored", "field"),
])
def test_explicit_duplicates_in_scalar_annotations_remain_rejected(tmp_path, annotation, key):
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "name: Two Year Co.", "name: !!str\n  =: company\n" + annotation,
    )
    expected = EntityConfig.model_validate(yaml.safe_load(source))
    assert expected.name == "company"
    path = tmp_path / "duplicate-annotation.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()

    with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
        with pytest.raises(ConstructorError, match=f"duplicate.*{key}"):
            load_config(path)
        validate.assert_not_called()
    assert path.read_bytes() == before


@pytest.mark.parametrize("consumed", [False, True])
@pytest.mark.parametrize("first,key", [
    ("!!float nan", "nan"), ("!!null null", "None"),
    ("!!bool false", "False"), ("!!str ''", "''"),
])
def test_successful_annotation_alias_keys_keep_identity_after_a_failed_comparison(tmp_path, first, key, consumed):
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "name: Two Year Co.",
        f"name: !!str\n  =: company\n  ? &first {first}\n  : ignored\n"
        "  ? !unsupported ignored\n  : ignored\n  ? *first\n  : ignored",
    )
    if consumed:
        source += "ignored: *first\n"
    assert yaml.safe_load(source)["name"] == "company"
    path = tmp_path / "annotation-alias.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()

    with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
        with pytest.raises(ConstructorError, match=f"duplicate.*{key}"):
            load_config(path)
        validate.assert_not_called()
    assert path.read_bytes() == before


def test_failed_annotation_comparisons_use_separate_constructor_state(tmp_path, monkeypatch):
    events = []

    class Audit(SafeConstructor):
        def construct_object(self, node, deep=False):
            events.append((self, node))
            return super().construct_object(node, deep=deep)

    monkeypatch.setattr("pyfpa.config.loader.SafeConstructor", Audit)
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "name: Two Year Co.",
        "name: !!str\n  =: company\n  ? &bad !unsupported ignored\n  : ignored\n"
        "  ? *bad\n  : ignored",
    )
    expected = EntityConfig.model_validate(yaml.safe_load(source))
    path = tmp_path / "failed-state.yaml"
    path.write_text(source, encoding="utf-8")
    before = path.read_bytes()

    try:
        assert load_config(path) == expected
    finally:
        assert path.read_bytes() == before
    failed = [(audit, node) for audit, node in events if node.tag == "!unsupported"]
    assert len(failed) == 2
    assert failed[0][1] is failed[1][1]
    assert failed[0][0] is not failed[1][0]


@pytest.mark.parametrize("error_type", [RuntimeError, MemoryError])
def test_unexpected_audit_faults_propagate_before_validation(tmp_path, monkeypatch, error_type):
    audit = mock.Mock()
    audit.construct_object.side_effect = error_type("audit fault")
    monkeypatch.setattr("pyfpa.config.loader.SafeConstructor", mock.Mock(return_value=audit))
    path = tmp_path / "fault.yaml"
    path.write_text(_MISSPELLABLE_YAML.format(growth_key="growth_rate"), encoding="utf-8")
    before = path.read_bytes()

    with mock.patch.object(EntityConfig, "model_validate", wraps=EntityConfig.model_validate) as validate:
        with pytest.raises(error_type, match="audit fault"):
            load_config(path)
        validate.assert_not_called()
    assert path.read_bytes() == before


@pytest.mark.parametrize("prefix", [
    "? [key]\n: value\n",
    "? {key: value}\n: value\n",
    "? &key [*key]\n: value\n",
])
def test_complex_and_recursive_yaml_keys_keep_constructor_failures(tmp_path, prefix):
    path = tmp_path / "key.yaml"
    path.write_text(prefix + _MISSPELLABLE_YAML.format(growth_key="growth_rate"), encoding="utf-8")
    with pytest.raises(ConstructorError, match="unhashable key"):
        load_config(path)


@pytest.mark.parametrize("growth_fields", [
    "growth_rate: *missing",
    "growth_rate: !unsupported 0.10",
    "growth_rate: !!python/object:builtins.object {}",
    "<<: 1",
    "<<: [1]",
])
def test_invalid_aliases_tags_and_merges_keep_yaml_errors(tmp_path, growth_fields):
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace("growth_rate: 0.10", growth_fields)
    path = tmp_path / "invalid.yaml"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_config(path)


def test_recursive_value_alias_reaches_model_validation(tmp_path):
    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate").replace(
        "opening_balances:\n  cash: 0", "opening_balances: &balances\n  cash: *balances")
    path = tmp_path / "recursive-value.yaml"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path)


def test_private_yaml_checker_does_not_change_other_loaders_or_later_documents(tmp_path):
    from pyfpa.io.loaders import read_yaml

    source = _MISSPELLABLE_YAML.format(growth_key="growth_rate")
    valid, invalid = tmp_path / "valid.yaml", tmp_path / "duplicate.yaml"
    valid.write_text(source, encoding="utf-8")
    invalid.write_text(source.replace("growth_rate: 0.10", "growth_rate: 0.10\n    growth_rate: 0.0"), encoding="utf-8")
    expected = load_config(valid)
    with pytest.raises(ConstructorError, match="duplicate.*growth_rate"):
        load_config(invalid)
    assert load_config(valid) == expected
    assert load_config(valid) == expected
    assert read_yaml(invalid)["channels"][0]["growth_rate"] == 0.0
    assert yaml.safe_load(invalid.read_text(encoding="utf-8"))["channels"][0]["growth_rate"] == 0.0


@pytest.mark.parametrize("source", ["", "[]", "42"])
def test_empty_and_non_mapping_yaml_reaches_model_validation(tmp_path, source):
    path = tmp_path / "not-a-config.yaml"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path)


def test_multiple_yaml_documents_remain_invalid(tmp_path):
    path = tmp_path / "documents.yaml"
    path.write_text(_MISSPELLABLE_YAML.format(growth_key="growth_rate") + "\n---\n{}\n", encoding="utf-8")
    with pytest.raises(yaml.composer.ComposerError):
        load_config(path)


def test_channel_name_must_not_be_blank():
    with pytest.raises(ValidationError, match="name must not be empty"):
        Channel(name="  ", annual_revenue=1200.0, seasonality=[1.0] * 12, cogs_pct=0.5)


def test_seasonality_weights_must_be_non_negative():
    with pytest.raises(ValidationError, match="seasonality weights must be non-negative"):
        Channel(name="D2C", annual_revenue=1200.0, seasonality=[-1.0] + [1.0] * 11, cogs_pct=0.5)


def test_seasonality_weights_must_not_all_be_zero():
    with pytest.raises(ValidationError, match="seasonality weights must sum to a positive number"):
        Channel(name="D2C", annual_revenue=1200.0, seasonality=[0.0] * 12, cogs_pct=0.5)


def test_debt_name_must_not_be_blank():
    with pytest.raises(ValidationError, match="name must not be empty"):
        DebtInstrument(name=" ", kind="term_loan", opening_balance=0.0, annual_rate=0.0)


def test_debt_name_is_trimmed():
    debt = DebtInstrument(name=" Term ", kind="term_loan", opening_balance=0.0, annual_rate=0.0)
    assert debt.name == "Term"  # nosec B101: pytest outcome assertion
