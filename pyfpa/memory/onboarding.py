from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from pyfpa.memory.intake import Intake, intake_ready, is_fact_known


class ArchitectureProposal(BaseModel):
    summary: str
    connectors: list[str] = Field(default_factory=list)
    model_components: list[str] = Field(default_factory=list)
    generated_skills: list[str] = Field(default_factory=list)
    validation_checks: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


PROFILE_HEADINGS: dict[str, str] = {
    "business": "Business Model And Revenue",
    "cash_cycle": "Cash Cycle And Seasonality",
    "finance_structure": "Entity, Financing, And Data Structure",
    "planning": "Planning Cadence And CFO Priorities",
}


def _bullet(items: list[str], *, empty: str = "None proposed.") -> str:
    if not items:
        return f"- {empty}\n"
    return "".join(f"- {item}\n" for item in items)


def render_business_profile(intake: Intake) -> str:
    """Render a cited business profile from the structured intake facts."""
    lines = [
        f"# {intake.business_name} Business Profile",
        "",
        "> Generated from `.fpa/intake.md`. Update the intake when facts change.",
        "",
    ]
    headings = list(PROFILE_HEADINGS.items())
    if any(fact.topic not in PROFILE_HEADINGS for fact in intake.facts):
        headings.append(("__other__", "Other Context"))
    for topic, heading in headings:
        lines.extend([f"## {heading}", ""])
        facts = [fact for fact in intake.facts if (
            fact.topic not in PROFILE_HEADINGS if topic == "__other__" else fact.topic == topic
        )]
        if not facts:
            lines.extend(["- Not yet known.", ""])
            continue
        for fact in facts:
            confidence = f"{fact.confidence:.0%}"
            sources = ", ".join(fact.sources) if fact.sources else fact.source_type
            lines.append(
                f"- **{fact.question}** {fact.answer} "
                f"_(status: {fact.status}; confidence: {confidence}; source: {sources})_"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_architecture_proposal(
    intake: Intake,
    proposal: ArchitectureProposal,
) -> str:
    """Render the human-review gate before model or connector generation."""
    knowns = [
        f"{fact.question}: {fact.answer}"
        for fact in intake.facts
        if is_fact_known(fact)
    ]
    unresolved = [
        f"{fact.question}: {fact.answer}"
        for fact in intake.facts
        if not is_fact_known(fact)
    ]
    return (
        "# Initial Model Architecture Proposal\n\n"
        "**Status:** Proposed. Human approval required before scaffolding.\n\n"
        "## Objective\n\n"
        f"{proposal.summary.strip()}\n\n"
        "## Known Facts\n\n"
        f"{_bullet(knowns, empty='No confirmed facts recorded.')}\n"
        "## Remaining Unknowns\n\n"
        f"{_bullet(unresolved, empty='No architecture-critical unknowns remain.')}\n"
        "## Proposed Connectors\n\n"
        f"{_bullet(proposal.connectors)}\n"
        "## Proposed Model Components\n\n"
        f"{_bullet(proposal.model_components)}\n"
        "## Proposed Generated Skills\n\n"
        f"{_bullet(proposal.generated_skills)}\n"
        "## Risks And Judgment Areas\n\n"
        f"{_bullet(proposal.risks, empty='No additional risks recorded.')}\n"
        "## Validation Checks\n\n"
        f"{_bullet(proposal.validation_checks)}\n"
        "## Decision\n\n"
        "- [ ] Approved to scaffold\n"
        "- [ ] Revise proposal\n"
        "- [ ] Stop after business profile\n"
    )


def write_onboarding_outputs(
    intake: Intake,
    workspace: str | Path,
    proposal: ArchitectureProposal,
    *,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Write the business profile and architecture proposal after intake is ready."""
    if not intake_ready(intake):
        raise ValueError("intake is not ready for architecture proposal")
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    decisions = workspace / "decisions"
    decisions.mkdir(exist_ok=True)
    profile_path = workspace / "business-profile.md"
    proposal_path = decisions / "initial-model-architecture.md"
    if not overwrite:
        for path in (profile_path, proposal_path):
            if path.exists():
                raise FileExistsError(f"onboarding output already exists: {path}")
    for path, text in (
        (profile_path, render_business_profile(intake)),
        (proposal_path, render_architecture_proposal(intake, proposal)),
    ):
        with path.open("w" if overwrite else "x", encoding="utf-8") as output:
            output.write(text)
    return profile_path, proposal_path
