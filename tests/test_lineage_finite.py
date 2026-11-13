# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

import json

import pytest

from pyfpa.memory.connectors import scaffold_connector_bundle
from pyfpa.memory.lineage import (
    MappingRegistry,
    MappingRule,
    SourceRecord,
    SourceRegistry,
    reconcile_account_table,
    save_mapping_registry,
    save_source_registry,
)


def reconcile(tmp_path, amounts, targets, expected=None, **options):
    path = tmp_path / "fabricated-aud.csv"
    path.write_text(
        "Account,Amount\n" + "".join(f"{i:03},{amount}\n" for i, amount in enumerate(amounts)),
        encoding="utf-8",
    )
    mappings = MappingRegistry(mappings=[
        MappingRule(
            source_id="fabricated-aud", source_value=f"{i:03}", target=target or "",
            status="mapped" if target else "ignored",
            rationale="Fabricated account deliberately outside the model" if target is None else "",
        )
        for i, target in enumerate(targets)
    ])
    original = path.read_bytes()
    try:
        return reconcile_account_table(
            path, source_id="fabricated-aud", mappings=mappings,
            account_column="Account", amount_column="Amount", expected=expected, **options,
        )
    finally:
        assert path.read_bytes() == original


@pytest.mark.parametrize("amounts,targets,expected", [
    ([1e308, 1e308], ["a", "b"], {"a": 1e308, "b": 1e308}),
    ([1e308, 1e308], ["a", "a"], {"a": 1e308}),
    ([1e308, 1e308], ["a", None], {"a": 1e308}),
    ([1e308, 1e308, -1e308], ["a", "b", None], {"a": 1e308, "b": 1e308}),
    ([1e308, 1e308, -1e308], ["a", "a", "a"], {"a": 1e308}),
    ([1e308, -1e308, 1e308], ["a", None, "b"], {"a": 1e308, "b": 1e308}),
    ([1e308, -1e308, 1e308], ["a", None, "a"], {"a": 1e308}),
    ([1e308, -1e308, 1e308, -1e308], ["a", "b", "a", "a"], {"a": 1e308, "b": -1e308}),
    ([1e308], ["a"], {"a": -1e308}),
    ([1.0], ["a"], {"a": 5e-324}),
])
def test_reconciliation_refuses_nonfinite_derived_values(tmp_path, amounts, targets, expected):
    with pytest.raises(ValueError, match="finite"):
        reconcile(tmp_path, amounts, targets, expected)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("target", ["a", "missing"])
def test_api_refuses_nonfinite_expected_controls(tmp_path, value, target):
    with pytest.raises(ValueError, match="finite"):
        reconcile(tmp_path, [100], ["a"], {target: value})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), -0.01])
@pytest.mark.parametrize("option", ["tolerance", "abs_tolerance"])
def test_api_refuses_invalid_tolerances(tmp_path, value, option):
    with pytest.raises(ValueError, match="finite|non-negative"):
        reconcile(tmp_path, [100], ["a"], {"a": 99}, **{option: value})


@pytest.mark.parametrize("amounts,expected,passed", [
    ([100, -40], {"a": 60}, True),
    ([100, -40], {"a": 59.99}, False),
    ([1e308, -1e308], {"a": 0}, True),
    ([1e308], {"a": 1e308}, True),
])
def test_finite_reconciliation_retains_controls(tmp_path, amounts, expected, passed):
    result = reconcile(tmp_path, amounts, ["a"] * len(amounts), expected)
    assert result["passed"] is passed
    json.dumps(result, allow_nan=False)


@pytest.fixture
def cli_workspace(tmp_path, run_cli):
    assert run_cli("init", str(tmp_path)).returncode == 0
    path = tmp_path / "fabricated-aud.csv"
    path.write_text("Account,Amount\n001,100\n002,-40\n", encoding="utf-8")
    save_source_registry(SourceRegistry(sources=[SourceRecord(
        source_id="fabricated-aud", kind="local_file", location=path.name,
        entity="Fabricated AU", currency="AUD", extraction_method="Synthetic fixture",
    )]), tmp_path / ".fpa/sources/registry.yaml")
    mappings = MappingRegistry(mappings=[
        MappingRule(source_id="fabricated-aud", source_value=code, target=target)
        for code, target in [("001", "a"), ("002", "b")]
    ])
    save_mapping_registry(mappings, tmp_path / ".fpa/mappings/registry.yaml")
    return path, mappings


@pytest.mark.parametrize("option", ["--tolerance", "--abs-tolerance"])
@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_cli_refuses_nonfinite_tolerances(tmp_path, run_cli, cli_workspace, option, value):
    result = run_cli(
        "reconcile-source", str(tmp_path), "--source-id", "fabricated-aud",
        "--expected-json", '{"a": 99, "b": -40}', f"{option}={value}",
    )
    # Negative values already use the CLI's usage-error path, before reconciliation.
    assert result.returncode == (2 if value == "-inf" else 1), result.stdout
    payload = json.loads(result.stderr if value == "-inf" else result.stdout)
    assert payload["ok"] is False
    assert ("non-negative" if value == "-inf" else "finite") in payload["error"]["message"]
    json.dumps(payload, allow_nan=False)


@pytest.mark.parametrize("extra", [[], ["--allow-unmapped"]])
def test_cli_refuses_overflow_without_emitting_nonfinite_json(
    tmp_path, run_cli, cli_workspace, extra,
):
    path, _ = cli_workspace
    path.write_text("Account,Amount\n001,1e308\n002,1e308\n", encoding="utf-8")
    result = run_cli(
        "reconcile-source", str(tmp_path), "--source-id", "fabricated-aud",
        "--expected-json", '{"a": 1e308, "b": 1e308}', *extra,
    )
    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "reconciliation_failed"
    assert "finite" in payload["error"]["message"]
    json.dumps(payload, allow_nan=False)


def test_connector_scaffold_refuses_overflow_before_creating_a_bundle(
    tmp_path, cli_workspace,
):
    path, mappings = cli_workspace
    path.write_text("Account,Amount\n001,1e308\n002,1e308\n", encoding="utf-8")
    bundle = tmp_path / "connectors/generated/fabricated-aud"
    with pytest.raises(ValueError, match="finite"):
        scaffold_connector_bundle(
            tmp_path, name="fabricated-aud", source_id="fabricated-aud",
            description="Fabricated AUD fixture", auth_method="host_environment", fixture=path,
            account_column="Account", amount_column="Amount", mappings=mappings,
        )
    assert not bundle.exists()
