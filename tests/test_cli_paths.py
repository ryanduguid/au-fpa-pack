"""Refusal and error paths of the top-level `openfpa` commands in pyfpa/cli.py.

The happy paths live in tests/test_cli.py. These tests drive the same commands
in-process through `run_cli` and assert the JSON error each failure reports.
"""

import json

import pytest

import pyfpa.cli

BROKEN_YAML = "not: [valid"
UNCLOSED_INTAKE = "---\nbusiness_name: Acme\n"


def output_json(result) -> dict:
    assert result.stdout, result.stderr  # nosec B101: pytest outcome assertion
    return json.loads(result.stdout)


def usage_error(result) -> str:
    assert result.returncode == 2  # nosec B101: pytest outcome assertion
    assert result.stdout == ""  # nosec B101: pytest outcome assertion
    payload = json.loads(result.stderr)
    assert payload["command"] == "usage"  # nosec B101: pytest outcome assertion
    assert payload["error"]["type"] == "usage_error"  # nosec B101: pytest outcome assertion
    return payload["error"]["message"]


# Every command that writes to or reads from .fpa/ refuses an uninitialised
# directory with the same error type and an action-specific message.
UNINITIALISED_COMMANDS = [
    ("intake-next", [], "requesting intake questions"),
    (
        "intake-record",
        ["--key", "business_model", "--answer", "Retail", "--source-type", "user"],
        "recording intake facts",
    ),
    (
        "entrypoint-register",
        ["--name", "forecast", "--kind", "forecast", "--description", "Run it",
         "--command-json", '["python", "forecast.py"]'],
        "registering entrypoints",
    ),
    ("entrypoint-list", [], "listing entrypoints"),
    (
        "source-register",
        ["--source-id", "gl", "--kind", "local_file", "--location", "gl.csv",
         "--entity", "Acme", "--currency", "AUD", "--extraction-method", "Export"],
        "registering sources",
    ),
    ("source-list", [], "listing sources"),
    (
        "mapping-register",
        ["--source-id", "gl", "--source-value", "Rent", "--target", "opex"],
        "registering mappings",
    ),
    ("mapping-list", [], "listing mappings"),
    ("model-assumptions", ["--config", "config.yaml"], "reviewing model assumptions"),
    (
        "connector-scaffold",
        ["--name", "gl-pull", "--source-id", "gl", "--description", "Pull GL",
         "--auth-method", "none", "--fixture", "gl.csv"],
        "scaffolding connectors",
    ),
    ("connector-list", [], "listing connectors"),
    ("connector-validate", ["--name", "gl-pull"], "validating connectors"),
    (
        "correction-record",
        ["--slug", "rent", "--type", "context", "--target", "opex.rent",
         "--date", "2026-05-01"],
        "recording corrections",
    ),
    ("correction-list", [], "listing corrections"),
    ("scorecard-render", [], "rendering scorecard"),
    ("experiment-list", [], "listing experiments"),
    ("context-pack", ["--task", "rent"], "building a context pack"),
    (
        "onboarding-render",
        ["--proposal-summary", "Driver model"],
        "rendering onboarding outputs",
    ),
]


@pytest.mark.parametrize(
    ("command", "extra", "action"),
    UNINITIALISED_COMMANDS,
    ids=[case[0] for case in UNINITIALISED_COMMANDS],
)
def test_commands_refuse_an_uninitialised_workspace(
    tmp_path, run_cli, command, extra, action
):
    result = run_cli(command, str(tmp_path), *extra)

    assert result.returncode == 1  # nosec B101: pytest outcome assertion
    payload = output_json(result)
    assert payload["command"] == command  # nosec B101: pytest outcome assertion
    assert payload["ok"] is False  # nosec B101: pytest outcome assertion
    assert payload["root"] == str(tmp_path.resolve())  # nosec B101: pytest outcome assertion
    assert payload["error"] == {  # nosec B101: pytest outcome assertion
        "type": "workspace_not_initialized",
        "message": f"initialize the company workspace before {action}",
    }
    assert not (tmp_path / ".fpa").exists()  # nosec B101: pytest outcome assertion


def test_inspect_data_refuses_a_path_that_is_not_a_directory(tmp_path, run_cli):
    ledger = tmp_path / "ledger.csv"
    ledger.write_text("Account,Amount\n")

    result = run_cli("inspect-data", str(ledger))

    assert result.returncode == 1  # nosec B101: pytest outcome assertion
    payload = output_json(result)
    assert payload["command"] == "inspect-data"  # nosec B101: pytest outcome assertion
    assert payload["error"] == {  # nosec B101: pytest outcome assertion
        "type": "path_not_found",
        "message": "inspection path is not a directory",
    }


def test_status_counts_recorded_facts_by_status(tmp_path, run_cli):
    assert run_cli("init", str(tmp_path)).returncode == 0  # nosec B101: pytest outcome assertion
    for key, source_type in (("business_model", "user"), ("revenue_streams", "inference")):
        recorded = run_cli(
            "intake-record",
            str(tmp_path),
            "--key",
            key,
            "--answer",
            "Retail",
            "--source-type",
            source_type,
        )
        assert recorded.returncode == 0, recorded.stdout  # nosec B101: pytest outcome assertion

    result = run_cli("status", str(tmp_path))

    assert result.returncode == 0  # nosec B101: pytest outcome assertion
    data = output_json(result)["data"]
    assert data["fact_count"] == 2  # nosec B101: pytest outcome assertion
    assert data["facts_by_status"] == {"confirmed": 1, "inferred": 1}  # nosec B101: pytest outcome assertion


def test_status_reports_an_unreadable_workspace(tmp_path, run_cli):
    assert run_cli("init", str(tmp_path)).returncode == 0  # nosec B101: pytest outcome assertion
    (tmp_path / ".fpa" / "intake.md").write_text(UNCLOSED_INTAKE)

    result = run_cli("status", str(tmp_path))

    assert result.returncode == 1  # nosec B101: pytest outcome assertion
    payload = output_json(result)
    assert payload["command"] == "status"  # nosec B101: pytest outcome assertion
    assert payload["error"]["type"] == "invalid_workspace"  # nosec B101: pytest outcome assertion
    assert "missing closing frontmatter delimiter" in payload["error"]["message"]  # nosec B101: pytest outcome assertion


def test_intake_next_reports_an_unreadable_intake(tmp_path, run_cli):
    assert run_cli("init", str(tmp_path)).returncode == 0  # nosec B101: pytest outcome assertion
    (tmp_path / ".fpa" / "intake.md").write_text(UNCLOSED_INTAKE)

    result = run_cli("intake-next", str(tmp_path))

    assert result.returncode == 1  # nosec B101: pytest outcome assertion
    payload = output_json(result)
    assert payload["command"] == "intake-next"  # nosec B101: pytest outcome assertion
    assert payload["error"]["type"] == "invalid_intake"  # nosec B101: pytest outcome assertion
    assert "missing closing frontmatter delimiter" in payload["error"]["message"]  # nosec B101: pytest outcome assertion


def test_intake_record_rejects_a_blank_answer(tmp_path, run_cli):
    assert run_cli("init", str(tmp_path)).returncode == 0  # nosec B101: pytest outcome assertion
    intake_before = (tmp_path / ".fpa" / "intake.md").read_text()

    result = run_cli(
        "intake-record",
        str(tmp_path),
        "--key",
        "business_model",
        "--answer",
        "   ",
        "--source-type",
        "user",
    )

    assert result.returncode == 1  # nosec B101: pytest outcome assertion
    payload = output_json(result)
    assert payload["error"] == {  # nosec B101: pytest outcome assertion
        "type": "invalid_intake_fact",
        "message": "intake answer must not be empty",
    }
    assert (tmp_path / ".fpa" / "intake.md").read_text() == intake_before  # nosec B101: pytest outcome assertion


@pytest.mark.parametrize(
    "command_json",
    ['{"argv": ["python"]}', "[]", '["python", 1]'],
    ids=["object", "empty-array", "non-string-item"],
)
def test_entrypoint_register_rejects_a_malformed_command(tmp_path, run_cli, command_json):
    assert run_cli("init", str(tmp_path)).returncode == 0  # nosec B101: pytest outcome assertion

    result = run_cli(
        "entrypoint-register",
        str(tmp_path),
        "--name",
        "forecast",
        "--kind",
        "forecast",
        "--description",
        "Run the forecast",
        "--command-json",
        command_json,
    )

    assert result.returncode == 1  # nosec B101: pytest outcome assertion
    payload = output_json(result)
    assert payload["error"] == {  # nosec B101: pytest outcome assertion
        "type": "invalid_entrypoint",
        "message": "--command-json must be a non-empty JSON array of strings",
    }


def test_entrypoint_list_reports_an_unreadable_registry(tmp_path, run_cli):
    assert run_cli("init", str(tmp_path)).returncode == 0  # nosec B101: pytest outcome assertion
    (tmp_path / ".fpa" / "models" / "entrypoints.yaml").write_text(BROKEN_YAML)

    result = run_cli("entrypoint-list", str(tmp_path))

    assert result.returncode == 1  # nosec B101: pytest outcome assertion
    payload = output_json(result)
    assert payload["command"] == "entrypoint-list"  # nosec B101: pytest outcome assertion
    assert payload["error"]["type"] == "invalid_entrypoint_registry"  # nosec B101: pytest outcome assertion
    assert "while parsing a flow sequence" in payload["error"]["message"]  # nosec B101: pytest outcome assertion


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["intake-next", "--limit", "0"], "--limit must be at least 1"),
        (
            ["reconcile-source", "--source-id", "gl", "--tolerance", "-0.01"],
            "--tolerance must be non-negative",
        ),
        (
            ["reconcile-source", "--source-id", "gl", "--abs-tolerance", "-1"],
            "--abs-tolerance must be non-negative",
        ),
    ],
    ids=["limit", "tolerance", "abs-tolerance"],
)
def test_numeric_option_bounds_are_usage_errors(tmp_path, run_cli, argv, message):
    command, *options = argv

    result = run_cli(command, str(tmp_path), *options)

    assert usage_error(result) == message  # nosec B101: pytest outcome assertion
    assert not (tmp_path / ".fpa").exists()  # nosec B101: pytest outcome assertion


def test_unexpected_handler_exception_becomes_json(tmp_path, run_cli, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("disk vanished mid-scan")

    monkeypatch.setattr(pyfpa.cli, "inspect_data_files", explode)

    result = run_cli("inspect-data", str(tmp_path))

    assert result.returncode == 1  # nosec B101: pytest outcome assertion
    payload = output_json(result)
    assert payload["command"] == "inspect-data"  # nosec B101: pytest outcome assertion
    assert payload["root"] == str(tmp_path.resolve())  # nosec B101: pytest outcome assertion
    assert payload["error"] == {  # nosec B101: pytest outcome assertion
        "type": "unexpected_error",
        "message": "disk vanished mid-scan",
    }
