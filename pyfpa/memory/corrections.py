from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

from pyfpa.config.schemas import EntityConfig
from pyfpa.memory.paths import apply_override

CorrectionType = Literal["parametric", "structural", "context"]
CorrectionStatus = Literal["open", "applied", "superseded"]


class Override(BaseModel):
    path: str
    value: float


class Correction(BaseModel):
    """One human correction. Frontmatter fields are the machine-readable contract;
    `notes` is the human-readable markdown body."""
    slug: str
    type: CorrectionType
    target: str
    status: CorrectionStatus = "open"
    date: str
    override: Override | None = None
    notes: str = ""


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) != 3:
            raise ValueError("missing closing frontmatter delimiter")
        _, frontmatter, body = parts
        data = yaml.safe_load(frontmatter) or {}
        if not isinstance(data, dict):
            raise ValueError("frontmatter must be a mapping")
        return data, body.strip()
    return {}, text.strip()


def save_correction(correction: Correction, directory: str | Path, *, overwrite: bool = False) -> None:
    """Write `<slug>.md` (YAML frontmatter + markdown body) into `directory`."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    data = correction.model_dump(exclude_none=True)
    body = data.pop("notes", "")
    data.pop("slug")
    text = "---\n" + yaml.safe_dump(data, sort_keys=False) + "---\n" + body + "\n"
    with (directory / f"{correction.slug}.md").open("w" if overwrite else "x", encoding="utf-8") as output:
        output.write(text)


def load_corrections(directory: str | Path) -> list[Correction]:
    """Load every `*.md` correction in `directory` (slug = filename stem).
    A missing directory returns an empty list."""
    directory = Path(directory)
    if not directory.exists():
        return []
    out: list[Correction] = []
    for path in sorted(directory.glob("*.md")):
        try:
            frontmatter, body = _split_frontmatter(path.read_text(encoding="utf-8"))
        except (ValueError, yaml.YAMLError) as exc:
            raise ValueError(f"invalid correction {path}: {exc}") from exc
        out.append(Correction.model_validate({**frontmatter, "slug": path.stem, "notes": body}))
    return out


def apply_corrections(cfg: EntityConfig, corrections: list[Correction]) -> EntityConfig:
    """Return a NEW config with every `applied` + `parametric` correction's override
    written in. `open`, `structural`, and `context` corrections are ignored (the
    latter two are routed by the skill, not applied to the model). Input unmutated."""
    data = cfg.model_dump()
    for correction in corrections:
        if correction.status == "applied" and correction.type == "parametric" and correction.override:
            apply_override(data, correction.override.path, correction.override.value)
    return EntityConfig.model_validate(data)
