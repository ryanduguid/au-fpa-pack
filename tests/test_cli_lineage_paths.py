"""Error and path-resolution branches of the source, mapping, reconcile and
connector commands in pyfpa/cli_commands/lineage.py.

The happy paths live in tests/test_cli.py; refusals on an uninitialised
workspace are in tests/test_cli_paths.py.
"""

import json

LEDGER = "Account,Amount\nProduct Revenue,100\nRent,(20)\n"


def output_json(result) -> dict:
    assert result.stdout, result.stderr  # nosec B101: pytest outcome assertion
    return json.loads(result.stdout)


def failure(result, command: str) -> dict:
    assert result.returncode == 1, result.stdout  # nosec B101: pytest outcome assertion
    payload = output_json(result)
    assert payload["command"] == command  # nosec B101: pytest outcome assertion
    assert payload["ok"] is False  # nosec B101: pytest outcome assertion
    return payload


def init_with_source(tmp_path, run_cli, location: str) -> None:
    assert run_cli("init", str(tmp_path)).returncode == 0  # nosec B101: pytest outcome assertion
    registered = run_cli(
        "source-register",
        str(tmp_path),
        "--source-id",
        "gl-actuals",
        "--kind",
        "local_file",
        "--location",
        location,
        "--entity",
        "Acme",
        "--currency",
        "AUD",
        "--extraction-method",
        "Manual export",
    )
    assert registered.returncode == 0, registered.stdout  # nosec B101: pytest outcome assertion


def map_value(tmp_path, run_cli, source_value: str, target: str, *extra: str) -> None:
    mapped = run_cli(
        "mapping-register",
        str(tmp_path),
        "--source-id",
        "gl-actuals",
        "--source-value",
        source_value,
        "--target",
        target,
        *extra,
    )
    assert mapped.returncode == 0, mapped.stdout  # nosec B101: pytest outcome assertion


def test_source_profile_reads_an_absolute_file_path(tmp_path, run_cli):
    elsewhere = tmp_path / "exports"
    elsewhere.mkdir()
    ledger = elsewhere / "actuals.csv"
    ledger.write_text(LEDGER)
    company = tmp_path / "company"
    company.mkdir()

    result = run_cli("source-profile", str(company), "--file", str(ledger))

    assert result.returncode == 0, result.stdout  # nosec B101: pytest outcome assertion
    data = output_json(result)["data"]
    assert data["rows"] == 2  # nosec B101: pytest outcome assertion
    assert data["writes_performed"] is False  # nosec B101: pytest outcome assertion


def test_source_profile_reports_a_missing_file(tmp_path, run_cli):
    result = run_cli("source-profile", str(tmp_path), "--file", "missing.csv")

    payload = failure(result, "source-profile")
    assert payload["error"]["type"] == "profile_failed"  # nosec B101: pytest outcome assertion
    assert "missing.csv" in payload["error"]["message"]  # nosec B101: pytest outcome assertion


def test_mapping_register_refuses_an_unregistered_source(tmp_path, run_cli):
    assert run_cli("init", str(tmp_path)).returncode == 0  # nosec B101: pytest outcome assertion

    result = run_cli(
        "mapping-register",
        str(tmp_path),
        "--source-id",
        "gl-actuals",
        "--source-value",
        "Rent",
        "--target",
        "opex.rent",
    )

    payload = failure(result, "mapping-register")
    assert payload["error"] == {  # nosec B101: pytest outcome assertion
        "type": "invalid_mapping",
        "message": "source is not registered: gl-actuals",
    }
    listed = output_json(run_cli("mapping-list", str(tmp_path)))
    assert listed["data"]["mapping_count"] == 0  # nosec B101: pytest outcome assertion


def test_mapping_list_reports_an_unreadable_registry(tmp_path, run_cli):
    assert run_cli("init", str(tmp_path)).returncode == 0  # nosec B101: pytest outcome assertion
    (tmp_path / ".fpa" / "mappings" / "registry.yaml").write_text("not: [valid")

    result = run_cli("mapping-list", str(tmp_path))

    payload = failure(result, "mapping-list")
    assert payload["error"]["type"] == "invalid_mapping_registry"  # nosec B101: pytest outcome assertion
    assert "while parsing a flow sequence" in payload["error"]["message"]  # nosec B101: pytest outcome assertion


def test_reconcile_source_reads_an_absolute_source_location(tmp_path, run_cli):
    ledger = tmp_path / "exports" / "actuals.csv"
    ledger.parent.mkdir()
    ledger.write_text(LEDGER)
    company = tmp_path / "company"
    init_with_source(company, run_cli, str(ledger))
    map_value(company, run_cli, "Product Revenue", "revenue")
    map_value(company, run_cli, "Rent", "opex")

    result = run_cli(
        "reconcile-source",
        str(company),
        "--source-id",
        "gl-actuals",
        "--expected-json",
        '{"revenue": 100, "opex": -20}',
    )

    assert result.returncode == 0, result.stdout  # nosec B101: pytest outcome assertion
    data = output_json(result)["data"]
    assert data["passed"] is True  # nosec B101: pytest outcome assertion
    assert data["mapped_total"] == 80.0  # nosec B101: pytest outcome assertion


def test_reconcile_source_reports_an_unregistered_source(tmp_path, run_cli):
    assert run_cli("init", str(tmp_path)).returncode == 0  # nosec B101: pytest outcome assertion

    result = run_cli("reconcile-source", str(tmp_path), "--source-id", "gl-actuals")

    payload = failure(result, "reconcile-source")
    assert payload["error"] == {  # nosec B101: pytest outcome assertion
        "type": "source_not_found",
        "message": "source is not registered: gl-actuals",
    }


def test_reconcile_source_rejects_non_numeric_expected_totals(tmp_path, run_cli):
    init_with_source(tmp_path, run_cli, "actuals.csv")
    (tmp_path / "actuals.csv").write_text(LEDGER)

    result = run_cli(
        "reconcile-source",
        str(tmp_path),
        "--source-id",
        "gl-actuals",
        "--expected-json",
        '{"revenue": "100"}',
    )

    payload = failure(result, "reconcile-source")
    assert payload["error"] == {  # nosec B101: pytest outcome assertion
        "type": "reconciliation_failed",
        "message": "--expected-json must be a JSON object of finite numeric totals",
    }
    assert "data" not in payload  # nosec B101: pytest outcome assertion


def test_connector_scaffold_refuses_an_unregistered_source(tmp_path, run_cli):
    assert run_cli("init", str(tmp_path)).returncode == 0  # nosec B101: pytest outcome assertion
    fixture = tmp_path / "redacted.csv"
    fixture.write_text(LEDGER)

    result = run_cli(
        "connector-scaffold",
        str(tmp_path),
        "--name",
        "gl-pull",
        "--source-id",
        "gl-actuals",
        "--description",
        "Pull the general ledger.",
        "--auth-method",
        "none",
        "--fixture",
        str(fixture),
    )

    payload = failure(result, "connector-scaffold")
    assert payload["error"] == {  # nosec B101: pytest outcome assertion
        "type": "connector_scaffold_failed",
        "message": "source is not registered: gl-actuals",
    }
    assert not (tmp_path / "connectors" / "generated" / "gl-pull").exists()  # nosec B101: pytest outcome assertion


def test_connector_list_reports_an_invalid_manifest(tmp_path, run_cli):
    assert run_cli("init", str(tmp_path)).returncode == 0  # nosec B101: pytest outcome assertion
    bundle = tmp_path / "connectors" / "generated" / "broken"
    bundle.mkdir(parents=True)
    (bundle / "connector.yaml").write_text("not: [valid")

    result = run_cli("connector-list", str(tmp_path))

    payload = failure(result, "connector-list")
    assert payload["error"]["type"] == "invalid_connector_manifest"  # nosec B101: pytest outcome assertion
    assert payload["error"]["message"]  # nosec B101: pytest outcome assertion


def test_connector_validate_reports_a_missing_bundle(tmp_path, run_cli):
    assert run_cli("init", str(tmp_path)).returncode == 0  # nosec B101: pytest outcome assertion

    result = run_cli("connector-validate", str(tmp_path), "--name", "gl-pull")

    payload = failure(result, "connector-validate")
    assert payload["error"]["type"] == "connector_validation_failed"  # nosec B101: pytest outcome assertion
    assert payload["error"]["message"].startswith("connector bundle not found: ")  # nosec B101: pytest outcome assertion


def test_connector_validate_fails_when_a_mapping_changes_after_scaffold(tmp_path, run_cli):
    init_with_source(tmp_path, run_cli, "quickbooks")
    (tmp_path / "redacted.csv").write_text(LEDGER)
    map_value(tmp_path, run_cli, "Product Revenue", "revenue.product")
    map_value(tmp_path, run_cli, "Rent", "opex.rent")
    scaffolded = run_cli(
        "connector-scaffold",
        str(tmp_path),
        "--name",
        "gl-pull",
        "--source-id",
        "gl-actuals",
        "--description",
        "Pull the general ledger.",
        "--auth-method",
        "none",
        "--fixture",
        "redacted.csv",
    )
    assert scaffolded.returncode == 0, scaffolded.stdout  # nosec B101: pytest outcome assertion
    # Remapping Rent moves its total to a target the manifest does not expect.
    map_value(tmp_path, run_cli, "Rent", "opex.occupancy", "--overwrite")

    result = run_cli("connector-validate", str(tmp_path), "--name", "gl-pull")

    payload = failure(result, "connector-validate")
    assert payload["error"] == {  # nosec B101: pytest outcome assertion
        "type": "connector_validation_failed",
        "message": "connector fixture output failed reconciliation",
    }
    assert payload["data"]["passed"] is False  # nosec B101: pytest outcome assertion
    assert payload["data"]["reconciliation"]["passed"] is False  # nosec B101: pytest outcome assertion
