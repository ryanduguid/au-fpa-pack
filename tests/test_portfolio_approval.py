"""The cross-client promotion gate. Every workspace and name here is fabricated."""

import os
from pathlib import Path

import pytest

import pyfpa.portfolio.library as library_module
from pyfpa.backtest.score import score_forecast
from pyfpa.backtest.snapshot import save_snapshot, snapshot_forecast
from pyfpa.config.schemas import EntityConfig
from pyfpa.io.loaders import read_yaml, write_yaml
from pyfpa.models.cashflow import cashflow_from_config
from pyfpa.portfolio.approval import (
    APPROVAL_STATEMENT,
    ApprovalScope,
    ConfidentialityReview,
    PromotionApproval,
    PromotionDenied,
    attest_validation,
    business_name,
    candidate_digest,
    check_promotion_approval,
    load_promotion_approval,
    record_promotion_approval,
    resolved_support,
    screen_candidate,
    skill_tree,
    workspace_id,
)
from pyfpa.portfolio.library import (
    load_library,
    promote_prior,
    promote_skill,
    seed_from_library,
    withdraw_prior,
)
from pyfpa.portfolio.manifest import ClientRef, Portfolio
from pyfpa.portfolio.mine import (
    PriorCandidate,
    SkillCandidate,
    find_recurring_skills,
    mine_priors,
)
from pyfpa.portfolio.validate import ValidationResult, validate_prior

DRIVER = "working_capital.dio_days"


def _cfg(dio):
    return EntityConfig.model_validate({
        "name": "c", "start_month": "2026-01", "horizon_months": 12, "tax_rate": 0.0,
        "channels": [{"name": "C", "annual_revenue": 1_200_000.0, "growth_rate": 0.0,
                      "seasonality": [1.0] * 12, "cogs_pct": 0.5}],
        "opex": [], "debt": [],
        "working_capital": {"dso_days": 30.0, "dpo_days": 30.0, "dio_days": dio},
        "opening_balances": {"cash": 0.0},
    })


def _client(tmp_path, folder, dio, *, profile_name=None, skills=()):
    root = tmp_path / folder
    cfg = _cfg(dio)
    snap = snapshot_forecast(cfg, cashflow_from_config(cfg), label="2026", created="2026-01-01")
    snap = snap.model_copy(update={"score": score_forecast(snap.predicted, snap.predicted)})
    (root / ".fpa" / "forecasts").mkdir(parents=True, exist_ok=True)
    save_snapshot(snap, root / ".fpa" / "forecasts" / "2026.snapshot.yaml")
    if profile_name is not None:
        (root / ".fpa" / "business-profile.md").write_text(
            f"# {profile_name} Business Profile\n\n## Revenue Model\n\n- Not yet known.\n",
            encoding="utf-8",
        )
    for name, files in skills:
        directory = root / "skills" / "generated" / name
        directory.mkdir(parents=True, exist_ok=True)
        for relative, text in files.items():
            (directory / relative).write_text(text, encoding="utf-8")
    return ClientRef(path=str(root), type="d2c")


def _three_clients(tmp_path, names=("Wattlebank Joinery", "Coral Bay Cartage", "Emu Plains Dental")):
    return [
        _client(tmp_path, folder, dio, profile_name=name)
        for folder, dio, name in zip(("one", "two", "three"), (44.0, 45.0, 46.0), names)
    ]


def _prior(clients):
    portfolio = Portfolio(library="lib", clients=clients)
    candidates = [c for c in mine_priors(portfolio, "d2c") if c.driver == DRIVER]
    assert len(candidates) == 1
    return candidates[0]


def _approval(library, candidate, *, findings=None, notes="", allowed_files=None,
              scope=None, digest=None, workspaces=None, aliases=()):
    """Record the approval a practitioner would record for `candidate`."""
    if scope is None:
        scope = ApprovalScope(
            business_type=candidate.business_type,
            driver=candidate.driver if isinstance(candidate, PriorCandidate) else None,
            skill=None if isinstance(candidate, PriorCandidate) else candidate.name,
        )
    if allowed_files is None and isinstance(candidate, SkillCandidate):
        allowed_files = ["SKILL.md"]
    approval = PromotionApproval(
        purpose="Reuse an inventory-days prior across same-type engagements",
        scope=scope,
        contributing_workspaces=list(candidate.support if workspaces is None else workspaces),
        authorisation_reference="EL-2026-014 cl 8 and practitioner sign-off",
        candidate_digest=digest or candidate_digest(candidate),
        confidentiality_review=ConfidentialityReview(
            reviewer="Marlo Quinn",
            reviewed_on="2026-09-20",
            notes=notes,
            automated_checks=screen_candidate(candidate) if findings is None else list(findings),
        ),
        approved_by="Marlo Quinn",
        approved_at="2026-09-20T09:30:00+10:00",
        allowed_files=list(allowed_files or []),
        aliases_acknowledged=list(aliases),
    )
    record_promotion_approval(library, approval)
    return approval


def _validated(clients, candidate):
    result = validate_prior(DRIVER, clients, tolerance=0.01, candidate=candidate)
    assert result.validated and result.n_folds == 3
    return result


def _attested(digest, *, mean_delta=-0.01, n_folds=3, validated=True):
    """A hand-built result carrying this process's attestation for those numbers.

    The attestation stops a result built elsewhere, not a caller inside this
    process, which is why the tests can build one: see promote_prior's docstring.
    """
    return ValidationResult(
        mean_delta=mean_delta, n_folds=n_folds, validated=validated,
        candidate_digest=digest,
        attestation=attest_validation(digest, n_folds, mean_delta),
    )


# --- no approval, no promotion -------------------------------------------------

def test_prior_promotion_without_an_approval_is_denied(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    validation = _validated(clients, candidate)
    library = tmp_path / "library"
    with pytest.raises(PromotionDenied, match="no promotion approval recorded"):
        promote_prior(library, candidate, validation)
    assert not library.exists()


def test_mined_candidate_is_discoverable_but_unpromotable(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    assert candidate.value == 45.0
    assert len(candidate.support) == 3
    with pytest.raises(PromotionDenied):
        promote_prior(tmp_path / "library", candidate, _validated(clients, candidate))


def test_recurring_skill_is_discoverable_but_unpromotable(tmp_path):
    skill = ("segment-rollup", {"SKILL.md": "---\nname: segment-rollup\n---\nRoll up segments.\n"})
    clients = [
        _client(tmp_path, folder, 45.0, profile_name=name, skills=[skill])
        for folder, name in zip(
            ("one", "two", "three"),
            ("Wattlebank Joinery", "Coral Bay Cartage", "Emu Plains Dental"),
        )
    ]
    candidates = find_recurring_skills(Portfolio(library="lib", clients=clients), "d2c")
    assert [c.name for c in candidates] == ["segment-rollup"]
    library = tmp_path / "library"
    with pytest.raises(PromotionDenied, match="no promotion approval recorded"):
        promote_skill(library, candidates[0])
    assert not (library / "skills").exists()


# --- the approval is bound to one exact candidate ------------------------------

def test_approval_for_an_earlier_digest_does_not_cover_a_changed_candidate(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    library = tmp_path / "library"
    _approval(library, candidate)
    changed = candidate.model_copy(update={"value": 52.0})
    with pytest.raises(PromotionDenied, match="no promotion approval recorded"):
        promote_prior(library, changed, _attested(candidate_digest(changed)))


def test_validation_from_another_candidate_is_refused(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    library = tmp_path / "library"
    _approval(library, candidate)
    stale = _attested("0" * 64)
    with pytest.raises(PromotionDenied, match="does not carry this candidate's digest"):
        promote_prior(library, candidate, stale)


def test_a_validation_result_built_by_hand_is_denied(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    library = tmp_path / "library"
    _approval(library, candidate)
    forged = ValidationResult(
        mean_delta=-9.0, n_folds=99, validated=True,
        candidate_digest=candidate_digest(candidate),
    )
    with pytest.raises(PromotionDenied, match="no attestation from validate_prior"):
        promote_prior(library, candidate, forged)


def test_an_attestation_does_not_cover_edited_numbers(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    library = tmp_path / "library"
    _approval(library, candidate)
    validation = _validated(clients, candidate)
    edited = validation.model_copy(update={"mean_delta": -9.0, "n_folds": 99})
    with pytest.raises(PromotionDenied, match="no attestation from validate_prior"):
        promote_prior(library, candidate, edited)


def test_an_attested_result_still_needs_an_approval(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    with pytest.raises(PromotionDenied, match="no promotion approval recorded"):
        promote_prior(tmp_path / "library", candidate, _validated(clients, candidate))


def test_validate_prior_refuses_a_candidate_it_does_not_hold_out(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    outside = candidate.model_copy(
        update={"support": [*candidate.support, str(tmp_path / "four")]}
    )
    with pytest.raises(ValueError, match="outside the validated client list"):
        validate_prior(DRIVER, clients, candidate=outside)
    with pytest.raises(ValueError, match="validation is for"):
        validate_prior("tax_rate", clients, candidate=candidate)


def test_validation_without_a_candidate_carries_no_digest(tmp_path):
    clients = _three_clients(tmp_path)
    assert validate_prior(DRIVER, clients).candidate_digest == ""


# --- scope --------------------------------------------------------------------

@pytest.mark.parametrize("scope_kwargs,message", [
    ({"business_type": "trucking", "driver": DRIVER}, "business type"),
    ({"business_type": "d2c", "driver": "tax_rate"}, "driver"),
])
def test_scope_mismatch_is_denied(tmp_path, scope_kwargs, message):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    library = tmp_path / "library"
    _approval(library, candidate, scope=ApprovalScope(**scope_kwargs))
    with pytest.raises(PromotionDenied, match=message):
        promote_prior(library, candidate, _validated(clients, candidate))


def test_skill_scope_must_name_the_skill(tmp_path):
    candidate = _skill_candidate(tmp_path)
    library = tmp_path / "library"
    _approval(library, candidate, scope=ApprovalScope(business_type="d2c", skill="other-skill"))
    with pytest.raises(PromotionDenied, match="approval covers skill"):
        promote_skill(library, candidate)


def test_scope_names_exactly_one_target():
    with pytest.raises(ValueError, match="exactly one of driver or skill"):
        ApprovalScope(business_type="d2c")
    with pytest.raises(ValueError, match="exactly one of driver or skill"):
        ApprovalScope(business_type="d2c", driver=DRIVER, skill="segment-rollup")


# --- contributors: duplicated and aliased workspaces ---------------------------

def test_duplicated_workspace_leaves_one_contributor(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    doubled = candidate.model_copy(
        update={"support": [clients[0].path, os.path.join(clients[0].path, "..", "one")]}
    )
    library = tmp_path / "library"
    _approval(library, doubled)
    with pytest.raises(PromotionDenied, match="at least two contributing workspaces"):
        promote_prior(library, doubled, _attested(candidate_digest(doubled)))


ALIAS_NOTES = (
    "Two separate engagements trade under one name; both engagement letters "
    "permit reuse across the group."
)


@pytest.mark.parametrize("second_name", [
    "Wattlebank Joinery",                 # an exact copy of the heading
    "Wattlebank Joinery Pty Ltd",         # relabelled with an entity suffix
    "wattlebank joinery (Newcastle)",     # relabelled with a bracketed qualifier
])
def test_a_relabelled_copy_is_still_one_contributor(tmp_path, second_name):
    clients = _three_clients(
        tmp_path, names=("Wattlebank Joinery", second_name, "Emu Plains Dental")
    )
    candidate = _prior(clients)
    validation = _validated(clients, candidate)
    library = tmp_path / "library"
    _approval(library, candidate, notes=ALIAS_NOTES)
    with pytest.raises(PromotionDenied, match="same business name"):
        promote_prior(library, candidate, validation)


def test_acknowledging_the_alias_ids_promotes(tmp_path):
    clients = _three_clients(
        tmp_path,
        names=("Wattlebank Joinery", "Wattlebank Joinery Pty Ltd", "Emu Plains Dental"),
    )
    candidate = _prior(clients)
    validation = _validated(clients, candidate)
    aliases = [workspace_id(clients[0].path), workspace_id(clients[1].path)]

    partial = tmp_path / "partial-library"
    _approval(partial, candidate, notes=ALIAS_NOTES, aliases=aliases[:1])
    with pytest.raises(PromotionDenied, match="aliases_acknowledged"):
        promote_prior(partial, candidate, validation)

    silent = tmp_path / "silent-library"
    _approval(silent, candidate, aliases=aliases)
    with pytest.raises(PromotionDenied, match="review notes"):
        promote_prior(silent, candidate, validation)

    reviewed = tmp_path / "reviewed-library"
    _approval(reviewed, candidate, notes=ALIAS_NOTES, aliases=aliases)
    promote_prior(reviewed, candidate, validation)
    assert load_library(reviewed)["priors"]["d2c"][0]["driver"] == DRIVER


def test_a_workspace_without_a_profile_establishes_no_client(tmp_path):
    clients = [
        _client(tmp_path, "one", 44.0, profile_name="Wattlebank Joinery"),
        _client(tmp_path, "two", 45.0),
        _client(tmp_path, "three", 46.0),
    ]
    candidate = _prior(clients)
    validation = _validated(clients, candidate)
    library = tmp_path / "library"
    _approval(library, candidate, notes=ALIAS_NOTES)
    with pytest.raises(PromotionDenied, match="establishes 1 distinct client"):
        promote_prior(library, candidate, validation)


def test_an_unidentifying_heading_counts_as_unestablished(tmp_path):
    clients = _three_clients(tmp_path)
    (tmp_path / "one" / ".fpa" / "business-profile.md").write_text(
        "# Pty Ltd\n", encoding="utf-8"
    )
    candidate = _prior(clients)
    library = tmp_path / "library"
    _approval(library, candidate)
    promote_prior(library, candidate, _validated(clients, candidate))
    # Two headings still establish two clients, so the promotion stands.
    assert load_library(library)["priors"]["d2c"][0]["driver"] == DRIVER


def test_genuinely_different_businesses_promote(tmp_path):
    clients = _three_clients(
        tmp_path,
        names=("Wattlebank Joinery Pty Ltd", "Coral Bay Cartage", "Emu Plains Dental"),
    )
    candidate = _prior(clients)
    library = tmp_path / "library"
    _approval(library, candidate)
    promote_prior(library, candidate, _validated(clients, candidate))
    assert load_library(library)["priors"]["d2c"][0]["value"] == 45.0


def test_approval_must_list_the_candidate_support(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    library = tmp_path / "library"
    _approval(library, candidate, workspaces=[clients[0].path, clients[1].path])
    with pytest.raises(PromotionDenied, match="do not match the candidate's support"):
        promote_prior(library, candidate, _validated(clients, candidate))


# --- confidentiality screen ----------------------------------------------------

def _skill_candidate(tmp_path, *, files=None, name="segment-rollup", profile="Wattlebank Joinery"):
    files = files or {"SKILL.md": "---\nname: segment-rollup\n---\nRoll up segments.\n"}
    clients = [
        _client(tmp_path, folder, 45.0, profile_name=client_name, skills=[(name, files)])
        for folder, client_name in zip(
            ("one", "two", "three"), (profile, "Coral Bay Cartage", "Emu Plains Dental")
        )
    ]
    candidates = find_recurring_skills(Portfolio(library="lib", clients=clients), "d2c")
    return candidates[0]


def test_sensitive_field_in_a_skill_file_blocks_promotion(tmp_path):
    body = (
        "---\nname: segment-rollup\n---\n"
        "Email the pack to accounts@wattlebank.example and quote ABN 51 824 753 556.\n"
    )
    candidate = _skill_candidate(tmp_path, files={"SKILL.md": body})
    findings = screen_candidate(candidate)
    assert "email address in SKILL.md" in findings
    assert "abn-like number in SKILL.md" in findings
    library = tmp_path / "library"
    _approval(library, candidate, findings=[])
    with pytest.raises(PromotionDenied, match="not recorded as reviewed"):
        promote_skill(library, candidate)

    reviewed = tmp_path / "reviewed-library"
    _approval(reviewed, candidate, findings=findings)
    promote_skill(reviewed, candidate)
    assert (reviewed / "skills" / "segment-rollup" / "SKILL.md").exists()


def test_screen_reports_each_shape_without_the_value(tmp_path):
    body = (
        "---\nname: segment-rollup\n---\n"
        "Call 03 9876 5432, TFN 123 456 789, BSB 083-004 12345678.\n"
        "Inventory carried $412,000 over the quarter.\n"
        "```\n$ python -m pyfpa\n```\n"
    )
    candidate = _skill_candidate(tmp_path, files={"SKILL.md": body})
    assert screen_candidate(candidate) == [
        "australian phone number in SKILL.md",
        "bank bsb or account number in SKILL.md",
        "dollar amount in narrative in SKILL.md",
        "tfn-like number in SKILL.md",
    ]


@pytest.mark.parametrize("profile", ["Wattlebank Joinery", "Wattlebank Joinery Pty Ltd"])
def test_screen_flags_a_client_name_in_a_skill_file(tmp_path, profile):
    body = "---\nname: segment-rollup\n---\nBuilt for wattlebank-joinery.\n"
    candidate = _skill_candidate(tmp_path, files={"SKILL.md": body}, profile=profile)
    identifier = workspace_id(resolved_support(candidate.support)[0])
    assert f"business name of workspace {identifier} in SKILL.md" in screen_candidate(candidate)


def test_screen_reads_the_profile_heading(tmp_path):
    client = _client(tmp_path, "one", 45.0, profile_name="Wattlebank Joinery")
    assert business_name(client.path) == "Wattlebank Joinery"
    assert business_name(tmp_path / "absent") is None


def test_screen_flags_prior_support_metadata(tmp_path):
    candidate = PriorCandidate(
        business_type="d2c", driver=DRIVER, value=45.0, dispersion=0.01,
        support=[str(tmp_path / "clients" / "accounts@wattlebank.example"), str(tmp_path / "two")],
    )
    assert any("email address in support entry" in f for f in screen_candidate(candidate))


# --- promote_skill copies only approved files ---------------------------------

def test_an_unlisted_file_cannot_ride_along(tmp_path):
    files = {
        "SKILL.md": "---\nname: segment-rollup\n---\nRoll up segments.\n",
        "workpaper.md": "Client stocktake counts.\n",
    }
    candidate = _skill_candidate(tmp_path, files=files)
    library = tmp_path / "library"
    _approval(library, candidate, allowed_files=["SKILL.md"])
    with pytest.raises(PromotionDenied, match="allowed_files"):
        promote_skill(library, candidate)
    assert not (library / "skills").exists()

    reviewed = tmp_path / "reviewed-library"
    _approval(reviewed, candidate, allowed_files=["SKILL.md", "workpaper.md"])
    promote_skill(reviewed, candidate)
    assert (reviewed / "skills" / "segment-rollup" / "workpaper.md").exists()


def test_the_library_gets_the_bytes_that_were_screened(tmp_path, monkeypatch):
    candidate = _skill_candidate(tmp_path)
    screened = dict(skill_tree(candidate))["SKILL.md"]
    library = tmp_path / "library"
    _approval(library, candidate)
    source = Path(candidate.source) / "SKILL.md"

    def rewrite_then_check(*args, **kwargs):
        # A client edit landing between the screen and the copy.
        source.write_text("Client stocktake counts.\n", encoding="utf-8")
        return check_promotion_approval(*args, **kwargs)

    monkeypatch.setattr(library_module, "check_promotion_approval", rewrite_then_check)
    promote_skill(library, candidate)
    assert (library / "skills" / "segment-rollup" / "SKILL.md").read_bytes() == screened


def test_a_link_in_the_skill_tree_is_refused(tmp_path, directory_link):
    candidate = _skill_candidate(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "workpaper.md").write_text("Client stocktake counts.\n", encoding="utf-8")
    directory_link(Path(candidate.source) / "linked", outside)
    library = tmp_path / "library"
    with pytest.raises(PromotionDenied, match="link or reparse point"):
        promote_skill(library, candidate)
    assert not (library / "skills").exists()


# --- what the shared library records -----------------------------------------

def test_promoted_records_carry_ids_not_paths(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    validation = _validated(clients, candidate)
    library = tmp_path / "library"
    approval = _approval(library, candidate)
    promote_prior(library, candidate, validation)

    prior_yaml = (library / "priors" / "d2c.yaml").read_text(encoding="utf-8")
    log = (library / "library-log.md").read_text(encoding="utf-8")
    approval_yaml = (
        library / "approvals" / f"{approval.candidate_digest}.yaml"
    ).read_text(encoding="utf-8")
    identifiers = [workspace_id(path) for path in resolved_support(candidate.support)]
    for path in resolved_support(candidate.support):
        assert path not in prior_yaml
        assert path not in log
        assert path not in approval_yaml           # the approval file names no client path
    for identifier in identifiers:
        assert identifier in prior_yaml
        assert identifier in log
        assert identifier in approval_yaml
    assert approval.contributing_workspaces == sorted(identifiers)
    assert candidate_digest(candidate) in log
    index = (library / "provenance" / "workspaces.yaml").read_text(encoding="utf-8")
    assert all(path in index for path in resolved_support(candidate.support))
    stored = load_promotion_approval(library, approval.candidate_digest)
    assert stored is not None
    assert stored.confidentiality_review.automated_checks == screen_candidate(candidate)


def test_seeding_records_provenance_in_both_places(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    library = tmp_path / "library"
    _approval(library, candidate)
    promote_prior(library, candidate, _validated(clients, candidate))

    receiving = tmp_path / "fourth"
    seeded = seed_from_library(
        library, "d2c", _cfg(30.0), company_root=receiving, seeded_at="2026-09-20"
    )
    assert seeded.working_capital.dio_days == 45.0
    seeds = (receiving / ".fpa" / "library-seeds.yaml").read_text(encoding="utf-8")
    assert DRIVER in seeds
    assert candidate_digest(candidate) in seeds
    assert "2026-09-20" in seeds
    index = (library / "provenance" / "seeds.yaml").read_text(encoding="utf-8")
    assert workspace_id(receiving) in index
    assert str(receiving.resolve()) not in index      # the index carries ids, not paths
    assert receiving.name not in index
    assert str(receiving.resolve()) in (
        (library / "provenance" / "workspaces.yaml").read_text(encoding="utf-8")
    )


def test_withdrawal_names_the_seeded_workspace_and_leaves_it_alone(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    library = tmp_path / "library"
    _approval(library, candidate)
    promote_prior(library, candidate, _validated(clients, candidate))
    digest = candidate_digest(candidate)

    receiving = tmp_path / "fourth"
    seed_from_library(library, "d2c", _cfg(30.0), company_root=receiving, seeded_at="2026-09-20")
    derived = receiving / ".fpa" / "forecasts" / "derived.snapshot.yaml"
    derived.parent.mkdir(parents=True, exist_ok=True)
    derived.write_text("label: derived\n", encoding="utf-8")

    affected = withdraw_prior(library, digest)
    assert affected == [str(receiving.resolve())]
    assert load_library(library)["priors"]["d2c"] == []
    assert "withdrawn prior" in (library / "library-log.md").read_text(encoding="utf-8")
    assert workspace_id(receiving) in (library / "library-log.md").read_text(encoding="utf-8")
    assert derived.read_text(encoding="utf-8") == "label: derived\n"
    assert (receiving / ".fpa" / "library-seeds.yaml").exists()


def test_an_unapproved_library_entry_cannot_seed(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    library = tmp_path / "library"
    _approval(library, candidate)
    promote_prior(library, candidate, _validated(clients, candidate))
    receiving = tmp_path / "fourth"

    # A hand-authored entry with no digest at all.
    priors = library / "priors" / "d2c.yaml"
    doc = read_yaml(priors)
    promoted = dict(doc["priors"][0])
    doc["priors"].append({"driver": "tax_rate", "value": 0.25})
    write_yaml(priors, doc)
    with pytest.raises(PromotionDenied, match="no candidate digest"):
        seed_from_library(library, "d2c", _cfg(30.0),
                          company_root=receiving, seeded_at="2026-09-21")

    # A digest with no support ids to re-digest from.
    doc["priors"][-1]["candidate_digest"] = "0" * 64
    write_yaml(priors, doc)
    with pytest.raises(PromotionDenied, match="not in the provenance map"):
        seed_from_library(library, "d2c", _cfg(30.0),
                          company_root=receiving, seeded_at="2026-09-21")
    assert not (receiving / ".fpa" / "library-seeds.yaml").exists()

    # Withdrawing the unapproved entry restores seeding.
    withdraw_prior(library, "0" * 64)
    seeded = seed_from_library(library, "d2c", _cfg(30.0),
                               company_root=receiving, seeded_at="2026-09-21")
    assert seeded.working_capital.dio_days == 45.0

    # An approval removed from the library stops the entry seeding again.
    (library / "approvals" / f"{promoted['candidate_digest']}.yaml").unlink()
    with pytest.raises(PromotionDenied, match="is not in the library"):
        seed_from_library(library, "d2c", _cfg(30.0),
                          company_root=receiving, seeded_at="2026-09-21")


def test_an_edited_library_prior_cannot_seed(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    library = tmp_path / "library"
    _approval(library, candidate)
    promote_prior(library, candidate, _validated(clients, candidate))
    priors = library / "priors" / "d2c.yaml"
    doc = read_yaml(priors)
    recorded = doc["priors"][0]["value"]

    for field, value in (("value", 52.0), ("driver", "working_capital.dso_days")):
        edited = read_yaml(priors)
        edited["priors"][0][field] = value
        write_yaml(priors, edited)
        with pytest.raises(PromotionDenied, match="edited after promotion"):
            seed_from_library(library, "d2c", _cfg(30.0),
                              company_root=tmp_path / "fourth", seeded_at="2026-09-21")

    write_yaml(priors, doc)
    seeded = seed_from_library(library, "d2c", _cfg(30.0),
                               company_root=tmp_path / "fourth", seeded_at="2026-09-21")
    assert seeded.working_capital.dio_days == recorded


def test_an_approval_at_another_digests_filename_is_refused(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    library = tmp_path / "library"
    approval = _approval(library, candidate)
    other = candidate.model_copy(update={"value": 52.0})
    other_digest = candidate_digest(other)
    copied = library / "approvals" / f"{other_digest}.yaml"
    copied.write_bytes((library / "approvals" / f"{approval.candidate_digest}.yaml").read_bytes())

    with pytest.raises(PromotionDenied, match=f"not the {other_digest}"):
        promote_prior(library, other, _attested(other_digest))
    # The record it was copied from keeps its own findings and stays where it is.
    stored = load_promotion_approval(library, approval.candidate_digest)
    assert stored is not None
    assert stored.candidate_digest == approval.candidate_digest
    assert not (library / "priors").exists()


def test_a_candidate_value_that_was_not_validated_is_refused(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    shifted = candidate.model_copy(update={"value": 52.0})
    with pytest.raises(ValueError, match="not the validated median"):
        validate_prior(DRIVER, clients, tolerance=0.01, candidate=shifted)


def test_a_candidate_for_another_business_type_is_refused(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    other = candidate.model_copy(update={"business_type": "trucking"})
    with pytest.raises(ValueError, match="business type"):
        validate_prior(DRIVER, clients, candidate=other)


def test_withdrawing_an_unknown_prior_raises(tmp_path):
    library = tmp_path / "library"
    (library / "priors").mkdir(parents=True)
    with pytest.raises(ValueError, match="no promoted prior"):
        withdraw_prior(library, "0" * 64)


# --- the approval record itself ----------------------------------------------

def test_recording_an_approval_twice_is_refused(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    library = tmp_path / "library"
    _approval(library, candidate)
    with pytest.raises(FileExistsError, match="already recorded"):
        _approval(library, candidate)


def test_recording_an_approval_is_an_exclusive_create(tmp_path):
    # A second writer must lose the race, not overwrite the first decision. The
    # placeholder is not a valid approval, so a refusal that never reads or
    # parses it shows the create itself did the checking.
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    library = tmp_path / "library"
    placeholder = library / "approvals" / f"{candidate_digest(candidate)}.yaml"
    placeholder.parent.mkdir(parents=True)
    placeholder.write_text("first writer wins\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already recorded"):
        _approval(library, candidate)
    assert placeholder.read_text(encoding="utf-8") == "first writer wins\n"


def test_the_statement_is_fixed_text(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    approval = _approval(tmp_path / "library", candidate)
    assert "not authentication" in approval.statement
    assert "not legal proof" in approval.statement
    assert approval.statement == APPROVAL_STATEMENT
    with pytest.raises(ValueError, match="statement is fixed text"):
        PromotionApproval.model_validate(
            {**approval.model_dump(), "statement": "The client consented."}
        )


@pytest.mark.parametrize("field", ["purpose", "authorisation_reference", "approved_by", "approved_at"])
def test_blank_required_fields_are_refused(tmp_path, field):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    approval = _approval(tmp_path / "library", candidate)
    with pytest.raises(ValueError, match=f"requires {field}"):
        PromotionApproval.model_validate({**approval.model_dump(), field: "  "})


def test_an_approval_needs_a_digest_and_contributors(tmp_path):
    clients = _three_clients(tmp_path)
    candidate = _prior(clients)
    approval = _approval(tmp_path / "library", candidate)
    with pytest.raises(ValueError, match="sha256 hex digest"):
        PromotionApproval.model_validate({**approval.model_dump(), "candidate_digest": "abc"})
    with pytest.raises(ValueError, match="requires contributing_workspaces"):
        PromotionApproval.model_validate({**approval.model_dump(), "contributing_workspaces": []})
    with pytest.raises(ValueError, match="ISO date"):
        ConfidentialityReview(reviewer="Marlo Quinn", reviewed_on="20 September 2026")
    with pytest.raises(ValueError, match="requires reviewer"):
        ConfidentialityReview(reviewer=" ", reviewed_on="2026-09-20")
