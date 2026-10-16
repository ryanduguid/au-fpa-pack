from __future__ import annotations

import pandas as pd

from pyfpa.config._snapshot import _current_configuration
from pyfpa.config.schemas import EntityConfig


def cogs_from_config(cfg: EntityConfig, revenue_df: pd.DataFrame) -> pd.DataFrame:
    """Monthly COGS per channel (revenue * cogs_pct) + total."""
    current = _current_configuration(cfg)
    cfg = EntityConfig.model_validate(current)
    data = {}
    for ch, raw in zip(cfg.channels, current["channels"], strict=True):
        column = ch.name if ch.name in revenue_df.columns else raw["name"]
        data[ch.name] = revenue_df[column] * ch.cogs_pct
    df = pd.DataFrame(data, index=revenue_df.index)
    return df.assign(total=df.sum(axis=1))
