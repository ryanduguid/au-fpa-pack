"""Default-deny approval boundary for cross-client promotion and reuse.

Mining a pattern out of one client's workspace and writing it into a shared
library moves that client's information into other clients' work. The kernel
cannot know whether an engagement permits that, so it decides nothing: a
promotion proceeds only against an approval a practitioner recorded by hand,
bound to the exact candidate by digest. Nothing in this module creates an
approval, and running the pack locally does not create one either.

A recorded approval is an acknowledgement, not authentication and not legal
proof that the client consented. The automated confidentiality screen assists
that human review; a clean screen is not a finding that no client information
is present.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import stat
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from pyfpa.io.loaders import create_yaml, read_yaml, write_yaml
from pyfpa.memory.workspace import Workspace
from pyfpa.portfolio.manifest import canonical_client_path
from pyfpa.portfolio.mine import PriorCandidate, SkillCandidate

APPROVAL_STATEMENT = (
    "This record is an acknowledgement recorded by the practitioner. It is not "
    "authentication, and it is not legal proof that the client consented to its "
    "information being used in another client's work."
)

WORKSPACE_ID_LENGTH = 16

# Per-process key behind the validation attestation. It is a structural barrier,
# not a security control: it stops a ValidationResult built by hand or carried in
# from somewhere else, and any caller that can import this module can also call
# `attest_validation`. See promote_prior for the trust boundary this sits inside.
_ATTESTATION_KEY = secrets.token_bytes(32)

_FILE_ATTRIBUTE_REPARSE_POINT = 0x400

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_WORKSPACE_ID = re.compile(r"^[0-9a-f]{%d}$" % WORKSPACE_ID_LENGTH)
_NON_ALNUM = re.compile(r"[^0-9a-z]+")
_BRACKETED = re.compile(r"[(\[][^)\]]*[)\]]")
# Trailing words that describe the legal wrapper rather than the business, so
# two headings that differ only by one of them name the same client.
_ENTITY_SUFFIXES = frozenset({
    "pty", "ltd", "limited", "proprietary", "inc", "incorporated", "nl", "co",
})

# Shapes worth a human look, not proof of anything. Each entry is (finding
# label, pattern); the label is what an approval must list as reviewed, so it
# never carries the matched value itself.
_SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("abn-like number", re.compile(r"\b\d{2} ?\d{3} ?\d{3} ?\d{3}\b")),
    ("tfn-like number", re.compile(r"\b\d{3} ?\d{3} ?\d{3}\b")),
    ("email address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]*\w")),
    (
        "australian phone number",
        re.compile(r"(?:\+61[ -]?|\b0)[2-478](?:[ -]?\d){8}\b"),
    ),
    (
        "bank bsb or account number",
        re.compile(
            r"\b\d{3}-\d{3}\b(?:[ -]?\d{6,10}\b)?"
            r"|\bacc(?:ount)?\.? ?(?:no\.?|number|#)? ?:? ?\d{6,10}\b",
            re.IGNORECASE,
        ),
    ),
)
_DOLLAR_AMOUNT = re.compile(r"\$ ?\d")


class PromotionDenied(ValueError):
    """Cross-client promotion is not covered by a recorded approval.

    It subclasses ``ValueError`` so a caller that already treats a refused
    promotion as a value error keeps behaving the same way.
    """


def workspace_id(path: str | Path) -> str:
    """An opaque id for one workspace: sha256 of its resolved path, truncated.

    Shared library records carry this instead of the path, so the library does
    not name a client's directory to whoever else reads it. The reverse map
    stays in the library's own ``provenance/workspaces.yaml``.
    """
    digest = hashlib.sha256(canonical_client_path(str(path)).encode("utf-8"))
    return digest.hexdigest()[:WORKSPACE_ID_LENGTH]


def resolved_support(support: list[str]) -> list[str]:
    """The candidate's support as a sorted set of resolved workspace paths."""
    return sorted({canonical_client_path(path) for path in support})


def business_name(workspace: str | Path) -> str | None:
    """The business name in `<workspace>/.fpa/business-profile.md`'s first heading.

    None when the workspace has no profile or the profile has no heading. The
    name identifies the client, so callers keep it out of shared records.
    """
    profile = Workspace.open(workspace).memory / "business-profile.md"
    if not profile.is_file():
        return None
    for line in profile.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            suffix = " Business Profile"
            if heading.endswith(suffix):
                heading = heading[: -len(suffix)].strip()
            return heading or None
    return None


class ConfidentialityReview(BaseModel):
    """The human confidentiality review behind one promotion approval.

    `automated_checks` is the screen's findings the reviewer has considered.
    A finding the screen raises but this list omits blocks the promotion, and a
    successful promotion rewrites the list with the findings actually observed.
    """

    reviewer: str
    reviewed_on: str
    notes: str = ""
    automated_checks: list[str] = Field(default_factory=list)

    @field_validator("reviewer")
    @classmethod
    def _non_blank(cls, value: str, info: ValidationInfo) -> str:
        return _require_text(value, str(info.field_name))

    @field_validator("reviewed_on")
    @classmethod
    def _iso_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value.strip())
        except ValueError as error:
            raise ValueError(f"reviewed_on must be an ISO date: {value!r}") from error
        return value.strip()


class ApprovalScope(BaseModel):
    """What one approval covers: a business type and a single named artefact."""

    business_type: str
    driver: str | None = None
    skill: str | None = None

    @field_validator("business_type")
    @classmethod
    def _non_blank(cls, value: str, info: ValidationInfo) -> str:
        return _require_text(value, str(info.field_name))

    @model_validator(mode="after")
    def _one_target(self) -> ApprovalScope:
        if (self.driver is None) == (self.skill is None):
            raise ValueError("approval scope names exactly one of driver or skill")
        return self


class PromotionApproval(BaseModel):
    """A practitioner's recorded approval for one cross-client promotion.

    The record is deliberately narrow: it names the purpose, the one artefact
    in scope, every contributing workspace, the authorisation it rests on, and
    the exact candidate digest. A candidate that changes digests, so an
    approval cannot follow the candidate into new content.

    `contributing_workspaces` holds opaque workspace ids, never paths. Pass
    paths or ids when building one; both are stored as ids, so the approval file
    in a shared library names no client directory. The id-to-path map lives in
    the library's own `provenance/workspaces.yaml`.
    """

    purpose: str
    scope: ApprovalScope
    contributing_workspaces: list[str]
    authorisation_reference: str
    candidate_digest: str
    confidentiality_review: ConfidentialityReview
    approved_by: str
    approved_at: str
    # Every file promote_skill may copy. A file in the candidate tree that is
    # not listed refuses the promotion, so a workpaper cannot ride along.
    allowed_files: list[str] = Field(default_factory=list)
    # Workspace ids the practitioner asserts are separate clients although their
    # business names match. Without them, matching names count as one client.
    aliases_acknowledged: list[str] = Field(default_factory=list)
    statement: str = APPROVAL_STATEMENT

    @field_validator("purpose", "authorisation_reference", "approved_by", "approved_at")
    @classmethod
    def _non_blank(cls, value: str, info: ValidationInfo) -> str:
        return _require_text(value, str(info.field_name))

    @field_validator("candidate_digest")
    @classmethod
    def _is_digest(cls, value: str) -> str:
        if not _SHA256_HEX.match(value):
            raise ValueError(f"candidate_digest must be a sha256 hex digest: {value!r}")
        return value

    @field_validator("contributing_workspaces")
    @classmethod
    def _workspace_ids(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("promotion approval requires contributing_workspaces")
        return sorted({
            entry if _WORKSPACE_ID.match(entry) else workspace_id(entry)
            for entry in value
        })

    @field_validator("statement")
    @classmethod
    def _fixed_statement(cls, value: str) -> str:
        if value != APPROVAL_STATEMENT:
            raise ValueError(
                "statement is fixed text and must not be edited; it records that "
                "the approval is an acknowledgement, not legal clearance"
            )
        return value


def _require_text(value: str, field: str) -> str:
    if not value.strip():
        raise ValueError(f"promotion approval requires {field}")
    return value


def _refuse_link(path: Path) -> None:
    """Refuse a symlink, junction or other reparse point inside a skill tree.

    A link would let the digest cover one file while the copy reads another, or
    reach a file outside the client's skill directory entirely.
    """
    info = path.lstat()
    reparse = bool(
        getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT
    )
    if stat.S_ISLNK(info.st_mode) or reparse:
        raise PromotionDenied(
            f"skill tree must not contain a link or reparse point: {path}"
        )


def skill_tree(candidate: SkillCandidate) -> list[tuple[str, bytes]]:
    """Every file under the candidate's skill directory, read once.

    Returns (relative posix path, bytes), sorted by path. These are the exact
    bytes the digest covers, and `promote_skill` writes these same bytes into
    the library rather than re-reading the client's directory, so a file that
    changes after the screen cannot land in the library unscreened. Any link or
    reparse point in the tree is refused.
    """
    root = Path(candidate.source)
    _refuse_link(root)
    entries = sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())
    tree: list[tuple[str, bytes]] = []
    for path in entries:
        _refuse_link(path)
        if path.is_file():
            tree.append((path.relative_to(root).as_posix(), path.read_bytes()))
    return tree


def candidate_digest(
    candidate: PriorCandidate | SkillCandidate,
    *,
    tree: list[tuple[str, bytes]] | None = None,
) -> str:
    """A deterministic sha256 over everything that makes the candidate what it is.

    A prior digests its driver, business type, value and sorted support set; a
    skill digests its name, business type and whole tree (relative path and
    bytes of every file). Change any of it and the digest changes, which is
    what stops an approval recorded for one candidate covering another.

    Pass `tree` for a skill to digest bytes already captured by `skill_tree`
    instead of reading the directory again.
    """
    if isinstance(candidate, PriorCandidate):
        parts = [
            "prior",
            candidate.business_type,
            candidate.driver,
            repr(candidate.value),
            *resolved_support(candidate.support),
        ]
        return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    digest = hashlib.sha256()
    digest.update(f"skill\n{candidate.business_type}\n{candidate.name}\n".encode())
    for relative, data in skill_tree(candidate) if tree is None else tree:
        digest.update(f"{relative}\n{len(data)}\n".encode())
        digest.update(data)
    return digest.hexdigest()


def attest_validation(candidate_digest: str, n_folds: int, mean_delta: float) -> str:
    """Stamp a cross-client validation run so a promotion can recognise it.

    `validate_prior` is the only caller. The stamp is an HMAC over the candidate
    digest (which already fixes the driver, business type, value and support),
    the fold count and the mean delta, keyed by a value generated fresh in this
    process. It makes a hand-built or imported `ValidationResult` fail, and it
    is not a security control: the key lives in this module's memory, so any
    code that can import the module can also stamp. It also does not outlive the
    process, so validate and promote in one session.
    """
    payload = f"{candidate_digest}\n{n_folds}\n{mean_delta!r}".encode()
    return hmac.new(_ATTESTATION_KEY, payload, "sha256").hexdigest()


def validation_is_attested(
    candidate_digest: str, n_folds: int, mean_delta: float, attestation: str
) -> bool:
    """Whether `attestation` is this process's stamp for those validation facts."""
    expected = attest_validation(candidate_digest, n_folds, mean_delta)
    return hmac.compare_digest(expected, attestation)


def _narrative(text: str) -> str:
    """`text` without fenced code blocks, so a dollar amount in prose stands out."""
    kept: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            kept.append(line)
    return "\n".join(kept)


def _squash(text: str) -> str:
    return _NON_ALNUM.sub(" ", text.lower())


def normalised_business_name(name: str) -> str:
    """`name` reduced to the words that identify the business.

    Drops case, punctuation, bracketed qualifiers and trailing entity suffixes,
    so a copied workspace cannot become a second contributor by relabelling its
    profile heading. Returns "" when nothing identifying is left.
    """
    tokens = _squash(_BRACKETED.sub(" ", name)).split()
    while tokens and tokens[-1] in _ENTITY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _screened_text(
    candidate: PriorCandidate | SkillCandidate,
    tree: list[tuple[str, bytes]] | None,
) -> list[tuple[str, str]]:
    if isinstance(candidate, SkillCandidate):
        return [
            (relative, data.decode("utf-8", "replace"))
            for relative, data in (skill_tree(candidate) if tree is None else tree)
        ]
    return [
        (f"support entry for workspace {workspace_id(path)}", path)
        for path in candidate.support
    ]


def screen_candidate(
    candidate: PriorCandidate | SkillCandidate,
    *,
    tree: list[tuple[str, bytes]] | None = None,
) -> list[str]:
    """Screen a promotion candidate for client information, and report findings.

    Scans skill files, or a prior's support metadata, for ABN and TFN shaped
    numbers, email addresses, Australian phone numbers, bank BSB and account
    patterns, dollar amounts in narrative lines, and the business names of the
    contributing workspaces. Findings name the shape and the location, never
    the matched value, so they are safe to record in a shared library.

    This assists a human review and proves nothing. An empty list means the
    patterns found nothing, not that the candidate carries no client
    information.

    Pass `tree` for a skill to screen bytes already captured by `skill_tree`,
    which is what `promote_skill` screens and copies.
    """
    # The normalised name, so a mention without the entity suffix still hits.
    names = {
        workspace_id(path): normalised_business_name(name)
        for path in resolved_support(candidate.support)
        if (name := business_name(path)) is not None
    }
    findings: set[str] = set()
    for location, text in _screened_text(candidate, tree):
        for label, pattern in _SENSITIVE_PATTERNS:
            if pattern.search(text):
                findings.add(f"{label} in {location}")
        if _DOLLAR_AMOUNT.search(_narrative(text)):
            findings.add(f"dollar amount in narrative in {location}")
        squashed = _squash(text)
        for identifier, name in names.items():
            if name and name in squashed:
                findings.add(f"business name of workspace {identifier} in {location}")
    return sorted(findings)


def approval_path(library: str | Path, digest: str) -> Path:
    """Where the approval for `digest` lives: `<library>/approvals/<digest>.yaml`."""
    return Path(library) / "approvals" / f"{digest}.yaml"


def load_promotion_approval(
    library: str | Path, candidate_digest: str
) -> PromotionApproval | None:
    """The recorded approval for `candidate_digest`, or None when there is none."""
    path = approval_path(library, candidate_digest)
    if not path.is_file():
        return None
    return PromotionApproval.model_validate(read_yaml(path))


def record_promotion_approval(
    library: str | Path, approval: PromotionApproval
) -> Path:
    """Write one practitioner-recorded approval and return its path.

    This is the only way an approval file comes into being: no mining,
    validation or promotion step writes one. The write is an exclusive create, so
    a recorded decision cannot be quietly restated, and two writers racing on one
    digest cannot both believe they recorded it.
    """
    path = approval_path(library, approval.candidate_digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        create_yaml(path, approval.model_dump())
    except FileExistsError as error:
        raise FileExistsError(
            f"promotion approval already recorded: {path}"
        ) from error
    return path


def record_screen_findings(
    library: str | Path, approval: PromotionApproval, findings: list[str]
) -> None:
    """Stamp the screen's findings into a recorded approval after a promotion.

    It replaces `confidentiality_review.automated_checks` with what the screen
    actually saw, which the gate has already established the reviewer covered.
    Nothing else in the approval changes.
    """
    path = approval_path(library, approval.candidate_digest)
    updated = approval.model_copy(deep=True)
    updated.confidentiality_review.automated_checks = list(findings)
    write_yaml(path, updated.model_dump())


def _check_scope(approval: PromotionApproval, candidate: PriorCandidate | SkillCandidate) -> None:
    scope = approval.scope
    if scope.business_type != candidate.business_type:
        raise PromotionDenied(
            f"approval covers business type {scope.business_type!r}, "
            f"candidate is {candidate.business_type!r}"
        )
    if isinstance(candidate, PriorCandidate):
        if scope.driver != candidate.driver:
            raise PromotionDenied(
                f"approval covers driver {scope.driver!r}, candidate is {candidate.driver!r}"
            )
        return
    if scope.skill != candidate.name:
        raise PromotionDenied(
            f"approval covers skill {scope.skill!r}, candidate is {candidate.name!r}"
        )


def _check_contributors(approval: PromotionApproval, support: list[str]) -> None:
    identifiers = sorted({workspace_id(path) for path in support})
    if approval.contributing_workspaces != identifiers:
        raise PromotionDenied(
            "approval contributing_workspaces do not match the candidate's support: "
            f"approved {approval.contributing_workspaces}, candidate {identifiers}"
        )
    if len(support) < 2:
        raise PromotionDenied(
            "cross-client promotion needs at least two contributing workspaces"
        )


def _check_aliases(approval: PromotionApproval, support: list[str]) -> None:
    """Count distinct clients, not distinct paths, and require at least two.

    A copied or re-pointed workspace has a different path, so the manifest's
    distinct-path check passes while the support set counts one client twice.
    Headings are compared after `normalised_business_name` strips case,
    punctuation, bracketed qualifiers and entity suffixes, so `Wattlebank
    Joinery Pty Ltd` and `Wattlebank Joinery (Newcastle)` are one contributor.
    A workspace with no profile heading establishes no identity, so it counts
    towards nothing.

    Promoting across two workspaces that normalise to one name takes both
    workspace ids in `aliases_acknowledged` and review notes saying why they are
    separate clients. Editing a copy's heading no longer buys a second
    contributor, and notes alone no longer satisfy the check.
    """
    grouped: dict[str, list[str]] = {}
    unestablished: list[str] = []
    for path in support:
        name = business_name(path)
        if name is None or not normalised_business_name(name):
            unestablished.append(workspace_id(path))
            continue
        grouped.setdefault(normalised_business_name(name), []).append(path)
    acknowledged = set(approval.aliases_acknowledged)
    reviewed = bool(approval.confidentiality_review.notes.strip())
    contributors = 0
    unresolved: list[list[str]] = []
    for paths in grouped.values():
        identifiers = sorted(workspace_id(path) for path in paths)
        if len(paths) == 1:
            contributors += 1
        elif reviewed and set(identifiers) <= acknowledged:
            contributors += len(paths)
        else:
            unresolved.append(identifiers)
            contributors += 1
    if unresolved:
        raise PromotionDenied(
            "these workspaces hold the same business name, so they count as one "
            f"contributor: {sorted(unresolved)}. Approving across them takes every "
            "one of those ids in aliases_acknowledged and review notes saying why "
            "they are separate clients."
        )
    if contributors < 2:
        raise PromotionDenied(
            f"support establishes {contributors} distinct client(s), not two. "
            f"Workspaces with no business-profile heading establish none: {unestablished}"
        )


def _check_allowed_files(
    approval: PromotionApproval, tree: list[tuple[str, bytes]]
) -> None:
    allowed = set(approval.allowed_files)
    extra = sorted(relative for relative, _ in tree if relative not in allowed)
    if extra:
        raise PromotionDenied(
            f"skill tree holds files the approval does not list in allowed_files: {extra}"
        )


def check_promotion_approval(
    library: str | Path,
    candidate: PriorCandidate | SkillCandidate,
    *,
    tree: list[tuple[str, bytes]] | None = None,
) -> tuple[PromotionApproval, list[str]]:
    """Require a recorded approval for `candidate`, and return it with the screen.

    Denies unless an approval exists for this candidate's digest, covers this
    exact business type and driver or skill, names exactly the candidate's
    support set by workspace id, establishes at least two distinct clients by
    business-profile heading, lists every file a skill tree would copy, and
    records every confidentiality finding as reviewed.

    Pass `tree` for a skill so the digest, the allowed-file check, the screen and
    the copy all cover one set of captured bytes.
    """
    digest = candidate_digest(candidate, tree=tree)
    approval = load_promotion_approval(library, digest)
    if approval is None:
        raise PromotionDenied(
            f"no promotion approval recorded for candidate digest {digest}. "
            "Record one with record_promotion_approval; mining and validation "
            "do not authorise moving one client's information into another's work."
        )
    support = resolved_support(candidate.support)
    _check_scope(approval, candidate)
    _check_contributors(approval, support)
    _check_aliases(approval, support)
    if isinstance(candidate, SkillCandidate):
        _check_allowed_files(approval, skill_tree(candidate) if tree is None else tree)
    findings = screen_candidate(candidate, tree=tree)
    unreviewed = sorted(set(findings) - set(approval.confidentiality_review.automated_checks))
    if unreviewed:
        raise PromotionDenied(
            "confidentiality screen findings are not recorded as reviewed in the "
            f"approval: {unreviewed}"
        )
    return approval, findings
