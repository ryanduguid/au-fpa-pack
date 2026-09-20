from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from pyfpa.config.schemas import EntityConfig
from pyfpa.io.loaders import read_yaml, write_yaml
from pyfpa.memory.paths import apply_override
from pyfpa.memory.workspace import Workspace
from pyfpa.portfolio.approval import (
    PromotionDenied,
    candidate_digest,
    check_promotion_approval,
    record_screen_findings,
    resolved_support,
    workspace_id,
    load_promotion_approval,
)
from pyfpa.portfolio.mine import PriorCandidate, SkillCandidate
from pyfpa.portfolio.validate import ValidationResult


def _log(library: Path, line: str) -> None:
    library.mkdir(parents=True, exist_ok=True)
    log = library / "library-log.md"
    header = "" if log.exists() else "# Library Log\n\n"
    with log.open("a", encoding="utf-8") as f:
        f.write(header + line + "\n")


def _record_workspace_ids(library: Path, paths: list[str]) -> list[str]:
    """Map each resolved workspace path to its opaque id in the library.

    The shared library YAML and log carry only the ids. This index is the one
    place that holds the paths, so a practitioner can still answer which
    workspaces a promoted record came from.
    """
    path = library / "provenance" / "workspaces.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = (read_yaml(path) if path.exists() else None) or {
        "schema_version": 1,
        "workspaces": {},
    }
    identifiers = []
    for workspace in paths:
        identifier = workspace_id(workspace)
        doc["workspaces"][identifier] = workspace
        identifiers.append(identifier)
    write_yaml(path, doc)
    return identifiers


def load_library(library: str | Path) -> dict[str, Any]:
    """Read the library: {'priors': {type: [prior dicts]}, 'skills': [names]}."""
    library = Path(library)
    priors: dict[str, list[dict[str, Any]]] = {}
    priors_dir = library / "priors"
    if priors_dir.exists():
        for f in sorted(priors_dir.glob("*.yaml")):
            doc = read_yaml(f) or {}
            priors[doc.get("type", f.stem)] = doc.get("priors", [])
    skills = sorted(p.name for p in (library / "skills").glob("*")) if (library / "skills").exists() else []
    return {"priors": priors, "skills": skills}


def promote_prior(library: str | Path, candidate: PriorCandidate, validation: ValidationResult) -> None:
    """Append an approved, ratified prior to priors/<type>.yaml and log it.

    Cross-client promotion is default-deny: a cross-client backtest establishes
    that the value generalises, not that this client's information may be used
    in another client's work. Both the validation and a recorded
    `PromotionApproval` for this exact candidate are required, and the written
    records name workspaces only by opaque id.
    """
    digest = candidate_digest(candidate)
    if not validation.validated or validation.n_folds < 2:
        raise PromotionDenied("prior requires successful validation across at least two folds")
    if validation.candidate_digest != digest:
        raise PromotionDenied(
            "validation does not carry this candidate's digest: re-run "
            "validate_prior with the candidate being promoted"
        )
    approval, findings = check_promotion_approval(library, candidate)
    library = Path(library)
    support_ids = _record_workspace_ids(library, resolved_support(candidate.support))
    priors_dir = library / "priors"
    priors_dir.mkdir(parents=True, exist_ok=True)
    path = priors_dir / f"{candidate.business_type}.yaml"
    doc = read_yaml(path) if path.exists() else None
    doc = doc or {"type": candidate.business_type, "priors": []}
    doc["priors"].append({
        "driver": candidate.driver, "value": candidate.value,
        "candidate_digest": digest, "support_ids": support_ids,
        "cross_client_holdout_delta": validation.mean_delta, "n_folds": validation.n_folds,
    })
    write_yaml(path, doc)
    _log(library, f"- prior `{candidate.driver}` = {candidate.value} for {candidate.business_type} "
                  f"(contributors {', '.join(support_ids)}, approval {digest}, "
                  f"delta {validation.mean_delta:+.4f})")
    record_screen_findings(library, approval, findings)


def promote_skill(library: str | Path, candidate: SkillCandidate) -> None:
    """Copy an approved recurring generated skill into the library and log it.

    A recorded `PromotionApproval` for the tree's digest is required, and it
    must list every file in the tree, so a workpaper left in a client's skill
    directory cannot ride along with the skill.
    """
    digest = candidate_digest(candidate)
    approval, findings = check_promotion_approval(library, candidate)
    library = Path(library)
    support_ids = _record_workspace_ids(library, resolved_support(candidate.support))
    dest = library / "skills" / candidate.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(candidate.source, dest)
    _log(library, f"- skill `{candidate.name}` for {candidate.business_type} "
                  f"(contributors {', '.join(support_ids)}, approval {digest})")
    record_screen_findings(library, approval, findings)


def seed_from_library(
    library: str | Path,
    business_type: str,
    cfg: EntityConfig,
    *,
    company_root: str | Path,
    seeded_at: str,
) -> EntityConfig:
    """Apply the library's promoted priors for `business_type` to a starting config.

    Returns a NEW config (input unmutated). Priors are seeds; the per-client loop refines.
    Each seeding is recorded in the receiving workspace's `.fpa/library-seeds.yaml`
    and in the library's `provenance/seeds.yaml`, so a later withdrawal can name
    the workspaces whose artefacts derive from a prior.
    """
    library = Path(library)
    data = cfg.model_dump()
    seeds: list[dict[str, Any]] = []
    for prior in load_library(library)["priors"].get(business_type, []):
        digest = prior.get("candidate_digest", "")
        if not isinstance(digest, str) or len(digest) != 64 or load_promotion_approval(library, digest) is None:
            continue
        apply_override(data, prior["driver"], prior["value"])
        seeds.append({
            "library": str(library), "driver": prior["driver"], "value": prior["value"],
            "candidate_digest": prior.get("candidate_digest", ""), "seeded_at": seeded_at,
        })
    if seeds:
        workspace = _write_workspace_seeds(company_root, seeds)
        _write_library_seeds(library, workspace, seeds, seeded_at)
    return EntityConfig.model_validate(data)


def _write_workspace_seeds(company_root: str | Path, seeds: list[dict[str, Any]]) -> Workspace:
    workspace = Workspace.open(company_root)
    target = workspace.memory / "library-seeds.yaml"
    workspace.assert_safe_existing_chain(target)
    workspace.memory.mkdir(parents=True, exist_ok=True)
    doc = (read_yaml(target) if target.exists() else None) or {
        "schema_version": 1,
        "seeds": [],
    }
    doc["seeds"].extend(seeds)
    write_yaml(target, doc)
    return workspace


def _write_library_seeds(
    library: Path, workspace: Workspace, seeds: list[dict[str, Any]], seeded_at: str
) -> None:
    identifier = _record_workspace_ids(library, [str(workspace.root)])[0]
    path = library / "provenance" / "seeds.yaml"
    doc = (read_yaml(path) if path.exists() else None) or {
        "schema_version": 1,
        "seeds": [],
    }
    doc["seeds"].extend({
        "workspace_id": identifier,
        "driver": seed["driver"], "candidate_digest": seed["candidate_digest"],
        "seeded_at": seeded_at,
    } for seed in seeds)
    write_yaml(path, doc)


def withdraw_prior(library: str | Path, candidate_digest: str) -> list[str]:
    """Remove a promoted prior from the library and report where it was seeded.

    Returns the workspaces the library's seed index records for this prior, so
    the artefacts derived from it can be identified. It changes nothing inside
    a client workspace: what to do with a derived forecast, model or workpaper
    is the practitioner's decision, not a deletion this function should make.
    """
    library = Path(library)
    removed = 0
    for path in sorted((library / "priors").glob("*.yaml")):
        doc = read_yaml(path) or {}
        priors = doc.get("priors", [])
        kept = [p for p in priors if p.get("candidate_digest") != candidate_digest]
        if len(kept) != len(priors):
            removed += len(priors) - len(kept)
            doc["priors"] = kept
            write_yaml(path, doc)
    if not removed:
        raise ValueError(f"no promoted prior with candidate digest {candidate_digest}")
    index = library / "provenance" / "seeds.yaml"
    entries = ((read_yaml(index) if index.exists() else None) or {}).get("seeds", [])
    seeded: list[str] = []
    workspaces = ((read_yaml(library / "provenance" / "workspaces.yaml") or {}).get("workspaces", {}))
    for entry in entries:
        identifier = entry.get("workspace_id")
        path = workspaces.get(identifier)
        if entry.get("candidate_digest") == candidate_digest and path and path not in seeded:
            seeded.append(path)
    _log(library, f"- withdrawn prior {candidate_digest} "
                  f"(seeded workspaces {', '.join(workspace_id(p) for p in seeded) or 'none recorded'}; "
                  "derived artefacts in those workspaces are untouched)")
    return seeded
