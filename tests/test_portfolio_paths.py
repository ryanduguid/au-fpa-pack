"""Fallback and skip paths in pyfpa.portfolio."""

from pathlib import Path

from pyfpa.backtest.score import score_forecast
from pyfpa.backtest.snapshot import save_snapshot, snapshot_forecast
from pyfpa.config.schemas import EntityConfig
from pyfpa.io.loaders import read_yaml, write_yaml
from pyfpa.memory.corrections import Correction, Override, save_correction
from pyfpa.models.cashflow import cashflow_from_config
from pyfpa.portfolio.approval import business_name, skill_tree
from pyfpa.portfolio.library import withdraw_prior
from pyfpa.portfolio.manifest import ClientRef, Portfolio
from pyfpa.portfolio.mine import (
    SkillCandidate,
    client_driver_value,
    find_recurring_skills,
)
from pyfpa.portfolio.validate import validate_prior

DIO = "working_capital.dio_days"


def _make_client(tmp_path: Path, name: str, dio: float) -> ClientRef:
    root = tmp_path / name
    cfg = EntityConfig.model_validate({
        "name": "c", "start_month": "2026-01", "horizon_months": 12, "tax_rate": 0.0,
        "channels": [{"name": "C", "annual_revenue": 1_200_000.0, "growth_rate": 0.0,
                      "seasonality": [1.0] * 12, "cogs_pct": 0.5}],
        "opex": [], "debt": [],
        "working_capital": {"dso_days": 30.0, "dpo_days": 30.0, "dio_days": dio},
        "opening_balances": {"cash": 0.0},
    })
    snap = snapshot_forecast(cfg, cashflow_from_config(cfg), label="2026", created="2026-01-01")
    snap = snap.model_copy(update={"score": score_forecast(snap.predicted, snap.predicted)})
    (root / ".fpa" / "forecasts").mkdir(parents=True, exist_ok=True)
    save_snapshot(snap, root / ".fpa" / "forecasts" / "2026.snapshot.yaml")
    return ClientRef(path=str(root), type="d2c")


def _profile(tmp_path: Path, text: str) -> Path:
    profile = tmp_path / ".fpa" / "business-profile.md"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(text, encoding="utf-8")
    return tmp_path


# --- approval ---------------------------------------------------------------------

def test_business_name_skips_text_before_the_heading(tmp_path):
    workspace = _profile(tmp_path, "Prepared for the CFO.\n\n## Acme Business Profile\n")

    assert business_name(workspace) == "Acme"  # nosec B101: pytest outcome assertion


def test_business_name_is_none_without_a_heading(tmp_path):
    workspace = _profile(tmp_path, "Prepared for the CFO.\nNo heading yet.\n")

    assert business_name(workspace) is None  # nosec B101: pytest outcome assertion


def test_skill_tree_reads_files_in_subdirectories(tmp_path):
    source = tmp_path / "rollup"
    (source / "references").mkdir(parents=True)
    (source / "SKILL.md").write_bytes(b"---\nname: rollup\n---\n")
    (source / "references" / "steps.md").write_bytes(b"1. Roll up.\n")
    candidate = SkillCandidate(business_type="d2c", name="rollup", support=[], source=str(source))

    assert skill_tree(candidate) == [  # nosec B101: pytest outcome assertion
        ("SKILL.md", b"---\nname: rollup\n---\n"),
        ("references/steps.md", b"1. Roll up.\n"),
    ]


# --- library ----------------------------------------------------------------------

def test_withdrawal_leaves_other_priors_and_reports_each_workspace_once(tmp_path):
    library = tmp_path / "library"
    target, other = "a" * 64, "b" * 64
    (library / "priors").mkdir(parents=True)
    (library / "provenance").mkdir()
    untouched = {"priors": [{"driver": "tax_rate", "candidate_digest": other}]}
    write_yaml(library / "priors" / "construction.yaml", untouched)
    write_yaml(library / "priors" / "d2c.yaml", {"priors": [
        {"driver": DIO, "candidate_digest": target},
        {"driver": "tax_rate", "candidate_digest": other},
    ]})
    write_yaml(library / "provenance" / "seeds.yaml", {"seeds": [
        {"workspace_id": "w1", "candidate_digest": target},
        {"workspace_id": "w2", "candidate_digest": other},
        {"workspace_id": "w1", "candidate_digest": target},
        {"workspace_id": "w3", "candidate_digest": target},
    ]})
    write_yaml(library / "provenance" / "workspaces.yaml", {"workspaces": {"w1": "/clients/one"}})

    seeded = withdraw_prior(library, target)

    assert seeded == ["/clients/one"]  # nosec B101: pytest outcome assertion
    assert read_yaml(library / "priors" / "construction.yaml") == untouched  # nosec B101: pytest outcome assertion
    assert read_yaml(library / "priors" / "d2c.yaml") == {  # nosec B101: pytest outcome assertion
        "priors": [{"driver": "tax_rate", "candidate_digest": other}],
    }
    log = (library / "library-log.md").read_text(encoding="utf-8")
    assert "seeded workspaces w1, w3, unresolved ['w3']" in log  # nosec B101: pytest outcome assertion


# --- mine -------------------------------------------------------------------------

def test_client_without_a_scored_snapshot_has_no_driver_value(tmp_path):
    client = ClientRef(path=str(tmp_path / "new-client"), type="d2c")

    assert client_driver_value(client, DIO) is None  # nosec B101: pytest outcome assertion


def test_unknown_driver_path_has_no_value(tmp_path):
    client = _make_client(tmp_path, "a", 45.0)

    assert client_driver_value(client, "working_capital.unknown_days") is None  # nosec B101: pytest outcome assertion
    assert client_driver_value(client, "tax_rate.monthly") is None  # nosec B101: pytest outcome assertion


def test_applied_parametric_correction_overrides_the_snapshot(tmp_path):
    client = _make_client(tmp_path, "a", 45.0)
    corrections = Path(client.path) / ".fpa" / "corrections"
    save_correction(Correction(
        slug="dio-draft", type="parametric", target="inventory", status="open",
        date="2026-02-01", override=Override(path=DIO, value=90.0),
    ), corrections)
    save_correction(Correction(
        slug="dio-fix", type="parametric", target="inventory", status="applied",
        date="2026-02-02", override=Override(path=DIO, value=60.0),
    ), corrections)

    assert client_driver_value(client, DIO) == 60.0  # nosec B101: pytest outcome assertion
    assert client_driver_value(client, "working_capital.dso_days") == 30.0  # nosec B101: pytest outcome assertion


def test_recurring_skills_ignore_clients_and_folders_without_skills(tmp_path):
    clients = [_make_client(tmp_path, name, 45.0) for name in ("a", "b", "c")]
    for client in clients[:2]:
        skill = Path(client.path) / "skills" / "generated" / "rollup"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: rollup\n---\n", encoding="utf-8")
        (Path(client.path) / "skills" / "generated" / "scratch").mkdir()

    skills = find_recurring_skills(Portfolio(library="lib", clients=clients), "d2c", min_support=2)

    assert [(skill.name, skill.support) for skill in skills] == [  # nosec B101: pytest outcome assertion
        ("rollup", [clients[0].path, clients[1].path]),
    ]


# --- validate ---------------------------------------------------------------------

def test_validation_skips_clients_without_a_scored_snapshot(tmp_path):
    clients = [_make_client(tmp_path, name, dio) for name, dio in (("a", 44.0), ("b", 45.0))]
    clients.append(ClientRef(path=str(tmp_path / "new-client"), type="d2c"))

    result = validate_prior(DIO, clients, tolerance=0.01)

    assert result.n_folds == 2  # nosec B101: pytest outcome assertion
    assert result.validated is True  # nosec B101: pytest outcome assertion
