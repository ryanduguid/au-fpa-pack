from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_codex_and_claude_share_onboarding_contract():
    agents = (ROOT / "AGENTS.md").read_text()
    claude = (ROOT / "CLAUDE.md").read_text()
    skill = (ROOT / "skills/fpa-learn-business/SKILL.md").read_text()

    assert claude.splitlines()[0] == "@AGENTS.md"
    agents_normalised = " ".join(agents.lower().split())
    skill_normalised = " ".join(skill.lower().split())
    assert "inspect supplied local files before asking questions" in agents_normalised
    assert "`pyfpa.next_intake_questions`, in rounds of at most 3 related questions" in agents_normalised
    assert "inspect local evidence first" in skill_normalised
    assert "files, documentation, and existing model code before asking questions" in skill_normalised
    assert "`openfpa intake-next <company-root>` and ask that related round of at most 3 questions" in skill_normalised
    assert "until the user approves the architecture proposal" in agents_normalised
    assert "stop for approval" in skill_normalised
    assert "narrow" in agents.lower()
    assert "narrow" in skill.lower()
    assert "before broad company work, run `openfpa context-pack" in " ".join(
        agents.lower().split()
    )


def test_research_contract_allows_autonomous_epochs_but_not_promotion():
    agents = (ROOT / "AGENTS.md").read_text().lower()
    skill = (ROOT / "skills/fpa-research-loop/SKILL.md").read_text().lower()

    assert "never replace the champion without explicit approval" in " ".join(agents.split())
    assert "only promotion to the active champion requires human approval" in " ".join(skill.split())
    assert "autonomously discard weak or failed challengers" in " ".join(agents.split())
    assert "ai may generate, test, and discard challengers autonomously" in " ".join(skill.split())
    assert "5 challengers" in skill
    assert "after scoring closed periods, run `openfpa scorecard-render" in " ".join(
        agents.split()
    )
