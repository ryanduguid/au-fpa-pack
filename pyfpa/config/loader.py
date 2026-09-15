from __future__ import annotations

from pathlib import Path

import yaml

from pyfpa.config.schemas import EntityConfig


def load_config(path: str | Path) -> EntityConfig:
    """Load and validate an EntityConfig from a YAML file.

    Read as UTF-8, not the platform's preferred encoding, so a config written
    on one machine loads on another.
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return EntityConfig.model_validate(raw)
