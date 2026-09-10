from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_codex_and_claude_share_onboarding_contract():
    agents = (ROOT / "AGENTS.md").read_text()
    claude = (ROOT / "CLAUDE.md").read_text()
    skill = (ROOT / "skills/fpa-learn-business/SKILL.md").read_text()

    assert claude.splitlines()[0] == "@AGENTS.md"
    for text in (agents, skill):
        assert "local" in text.lower()
        assert "three" in text.lower() or "limit=3" in text
        assert "approval" in text.lower()
    assert "narrow" in agents.lower()
    assert "narrow" in skill.lower()
    assert "before broad company work, run `openfpa context-pack" in " ".join(
        agents.lower().split()
    )


def test_research_contract_allows_autonomous_epochs_but_not_promotion():
    agents = (ROOT / "AGENTS.md").read_text().lower()
    skill = (ROOT / "skills/fpa-research-loop/SKILL.md").read_text().lower()

    for text in (agents, skill):
        assert "autonomous" in text or "autonomously" in text
        assert "promotion" in text
        assert "approval" in text
    assert "five challengers" in skill
    assert "after scoring closed periods, run `openfpa scorecard-render" in " ".join(
        agents.split()
    )
