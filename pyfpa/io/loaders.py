from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pyfpa.analysis.sku import Sku
from pyfpa.cash13.schemas import Cash13Config


def read_yaml(path: str | Path) -> Any:
    """Parse a YAML file as UTF-8, whatever the platform's preferred encoding is.

    `pyfpa.memory` already reads and writes its YAML as UTF-8 explicitly. This
    pair is the same contract for the research and portfolio stores, so a
    workspace written on one machine reads back on another.
    """
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def write_yaml(path: str | Path, data: Any) -> None:
    """Write `data` as UTF-8 YAML, preserving key order."""
    Path(path).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def load_cash13_config(path: str | Path) -> Cash13Config:
    """Load and validate a Cash13Config from a YAML file."""
    p = Path(path)
    with p.open() as f:
        raw = yaml.safe_load(f)
    return Cash13Config.model_validate(raw)


def load_skus(path: str | Path) -> list[Sku]:
    """Load a list of Sku from a YAML file with a top-level `skus:` list."""
    p = Path(path)
    with p.open() as f:
        raw = yaml.safe_load(f)
    return [Sku.model_validate(item) for item in raw["skus"]]
