from __future__ import annotations

from collections.abc import Hashable
from copy import copy
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError, SafeConstructor
from yaml.nodes import MappingNode, Node, SequenceNode

from pyfpa.config.schemas import EntityConfig


class _UniqueKeySafeLoader(yaml.SafeLoader):
    def construct_document(self, node: Node) -> Any:
        """Preserve explicit scopes and compare inherited key objects after construction."""
        pending = [node]
        visited: set[Node] = set()
        merge_key = object()
        # Keep successful alias identities without retaining failed constructor state.
        compared: dict[Node, Hashable] = {}
        scopes: list[list[tuple[Node, bool]]] = []
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            if isinstance(current, SequenceNode):
                pending.extend(current.value)
            elif isinstance(current, MappingNode):
                scope: list[tuple[Node, bool]] = []
                scopes.append(scope)
                for key_node, value_node in current.value:
                    pending.extend((key_node, value_node))
                    is_merge = key_node.tag == "tag:yaml.org,2002:merge"
                    scope.append((key_node, is_merge))
                    if not is_merge and key_node not in compared:
                        comparison = key_node
                        if key_node.tag == "tag:yaml.org,2002:value":
                            comparison = copy(key_node)
                            comparison.tag = "tag:yaml.org,2002:str"
                        audit = SafeConstructor()
                        try:
                            key = audit.construct_object(comparison)
                        except (ConstructorError, KeyError, IndexError, ValueError,
                                AttributeError, TypeError, OverflowError, RecursionError):
                            # Inherited construction decides whether this key is used.
                            continue
                        if not isinstance(key, Hashable):
                            continue
                        compared[key_node] = key

        # Inherited construction populates this dictionary, then replaces its attribute.
        actual = self.constructed_objects
        data = super().construct_document(node)
        for scope in scopes:
            keys: dict[object, Node] = {}
            for key_node, is_merge in scope:
                if is_merge:
                    key = merge_key
                elif key_node in actual:
                    key = actual[key_node]
                elif key_node in compared:
                    key = compared[key_node]
                else:
                    continue
                if not isinstance(key, Hashable):
                    continue
                first = keys.get(key)
                if first is not None:
                    label = "<<" if key is merge_key else key
                    raise ConstructorError("first occurrence", first.start_mark,
                                           f"found duplicate YAML key {label!r}", key_node.start_mark)
                keys[key] = key_node
        return data


def load_config(path: str | Path) -> EntityConfig:
    """Load and validate an EntityConfig from a YAML file.

    Read as UTF-8, not the platform's preferred encoding, so a config written
    on one machine loads on another.
    """
    return config_from_bytes(Path(path).read_bytes())


def config_from_bytes(raw: bytes) -> EntityConfig:
    """Validate an EntityConfig from the exact bytes of a YAML file.

    Decoded as ``load_config`` reads a file: UTF-8 with universal newlines.
    """
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return EntityConfig.model_validate(yaml.load(text, Loader=_UniqueKeySafeLoader))
