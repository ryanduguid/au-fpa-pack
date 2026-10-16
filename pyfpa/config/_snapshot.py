from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from pyfpa.config.schemas import EntityConfig


def _current_state(value: object, ancestors: set[int]) -> object:
    """Copy current model storage without dropping unchecked fields or defaults."""
    if isinstance(value, (BaseModel, dict, list, tuple, range)):
        identity = id(value)
        if identity in ancestors:
            raise ValueError("configuration contains a cycle")
        ancestors.add(identity)
        try:
            if isinstance(value, BaseModel):
                fields = vars(value)
                missing = type(value).model_fields.keys() - fields.keys()
                if missing:
                    raise ValueError("configuration is missing fields: " + ", ".join(sorted(missing)))
                extra = value.__pydantic_extra__
                if extra is not None:
                    if not isinstance(extra, dict) or fields.keys() & extra.keys():
                        raise ValueError("configuration has malformed extra-field storage")
                    fields = fields | extra
                return {key: _current_state(item, ancestors) for key, item in fields.items()}
            if isinstance(value, dict):
                return {key: _current_state(item, ancestors) for key, item in value.items()}
            return [_current_state(item, ancestors) for item in value]
        finally:
            ancestors.remove(identity)
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        raise ValueError("configuration contains an unsupported iterable")
    return value


def _current_configuration(cfg: EntityConfig) -> dict[Any, Any]:
    """Copy current configuration storage for validation and source-name lookup."""
    if not isinstance(cfg, EntityConfig):
        raise ValueError("configuration must be an EntityConfig")
    current = _current_state(cfg, set())
    assert isinstance(current, dict)
    return current


def _validated_snapshot(cfg: EntityConfig) -> EntityConfig:
    """Validate all current fields and return an independently owned configuration."""
    return EntityConfig.model_validate(_current_configuration(cfg))
