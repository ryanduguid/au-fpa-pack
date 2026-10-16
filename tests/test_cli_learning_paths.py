"""Error branches of the correction, scorecard, experiment and context-pack
commands in pyfpa/cli_commands/learning.py, and the snapshot check in
pyfpa/memory/diagnostics.py.

Refusals on an uninitialised workspace are in tests/test_cli_paths.py.
"""

import json

import pyfpa.backtest.learn
import pyfpa.memory.retrieval


def output_json(result) -> dict:
    assert result.stdout, result.stderr  # nosec B101: pytest outcome assertion
    return json.loads(result.stdout)


def failure(result, command: str) -> dict:
    assert result.returncode == 1, result.stdout  # nosec B101: pytest outcome assertion
    payload = output_json(result)
    assert payload["command"] == command  # nosec B101: pytest outcome assertion
    assert payload["ok"] is False  # nosec B101: pytest outcome assertion
    return payload


def init(tmp_path, run_cli) -> None:
    assert run_cli("init", str(tmp_path)).returncode == 0  # nosec B101: pytest outcome assertion


def test_correction_record_requires_a_path_for_an_override_value(tmp_path, run_cli):
    init(tmp_path, run_cli)

    result = run_cli(
        "correction-record",
        str(tmp_path),
        "--slug",
        "rent",
        "--type",
        "parametric",
        "--target",
        "opex.rent",
        "--date",
        "2026-05-01",
        "--override-value",
        "1200",
    )

    payload = failure(result, "correction-record")
    assert payload["error"] == {  # nosec B101: pytest outcome assertion
        "type": "invalid_correction",
        "message": "override_value requires override_path",
    }
    assert list((tmp_path / ".fpa" / "corrections").glob("*.md")) == []  # nosec B101: pytest outcome assertion


def test_correction_list_reports_an_unreadable_correction(tmp_path, run_cli):
    init(tmp_path, run_cli)
    (tmp_path / ".fpa" / "corrections" / "rent.md").write_text("---\ntype: context\n")

    result = run_cli("correction-list", str(tmp_path))

    payload = failure(result, "correction-list")
    assert payload["error"]["type"] == "invalid_correction"  # nosec B101: pytest outcome assertion
    assert "missing closing frontmatter delimiter" in payload["error"]["message"]  # nosec B101: pytest outcome assertion


def test_scorecard_render_refuses_unreadable_snapshots(tmp_path, run_cli):
    init(tmp_path, run_cli)
    forecasts = tmp_path / ".fpa" / "forecasts"
    forecasts.mkdir(exist_ok=True)
    (forecasts / "broken.yaml").write_text("not: [valid")
    scorecard = tmp_path / ".fpa" / "scorecard.md"
    scorecard_before = scorecard.read_text()

    result = run_cli("scorecard-render", str(tmp_path))

    payload = failure(result, "scorecard-render")
    assert payload["error"]["type"] == "invalid_snapshot"  # nosec B101: pytest outcome assertion
    assert payload["error"]["message"].startswith("broken.yaml: ")  # nosec B101: pytest outcome assertion
    assert scorecard.read_text() == scorecard_before  # nosec B101: pytest outcome assertion


def test_scorecard_render_reports_a_render_failure(tmp_path, run_cli, monkeypatch):
    init(tmp_path, run_cli)

    def fail_render(snapshots):
        raise RuntimeError("template missing")

    monkeypatch.setattr(pyfpa.backtest.learn, "render_scorecard", fail_render)

    result = run_cli("scorecard-render", str(tmp_path))

    payload = failure(result, "scorecard-render")
    assert payload["error"] == {  # nosec B101: pytest outcome assertion
        "type": "render_failed",
        "message": "template missing",
    }


def test_experiment_list_reports_an_unreadable_experiment(tmp_path, run_cli):
    init(tmp_path, run_cli)
    experiments = tmp_path / ".fpa" / "experiments"
    experiments.mkdir(exist_ok=True)
    (experiments / "broken.experiment.yaml").write_text("not: [valid")

    result = run_cli("experiment-list", str(tmp_path))

    payload = failure(result, "experiment-list")
    assert payload["error"]["type"] == "invalid_experiment"  # nosec B101: pytest outcome assertion
    assert payload["error"]["message"]  # nosec B101: pytest outcome assertion


def test_context_pack_reports_an_index_failure(tmp_path, run_cli, monkeypatch):
    init(tmp_path, run_cli)

    def fail_index(workspace):
        raise OSError("memory index unreadable")

    monkeypatch.setattr(pyfpa.memory.retrieval, "build_memory_index", fail_index)

    result = run_cli("context-pack", str(tmp_path), "--task", "rent")

    payload = failure(result, "context-pack")
    assert payload["error"] == {  # nosec B101: pytest outcome assertion
        "type": "context_pack_failed",
        "message": "memory index unreadable",
    }


def test_doctor_reports_unreadable_snapshots(tmp_path, run_cli):
    init(tmp_path, run_cli)
    forecasts = tmp_path / ".fpa" / "forecasts"
    forecasts.mkdir(exist_ok=True)
    (forecasts / "broken.yaml").write_text("not: [valid")

    result = run_cli("doctor", str(tmp_path))

    payload = failure(result, "doctor")
    snapshots = next(
        check for check in payload["data"]["checks"] if check["name"] == "snapshots"
    )
    assert snapshots["result"] == "error"  # nosec B101: pytest outcome assertion
    assert snapshots["details"].startswith("0 ok; errors: broken.yaml: ")  # nosec B101: pytest outcome assertion
