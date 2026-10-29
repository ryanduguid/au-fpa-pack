"""Describe validated model inputs without running the financial model."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from pyfpa.config.schemas import EntityConfig


def _segment(name: object) -> str:
    return str(name).replace('~', '~0').replace('/', '~1')


def _inputs(model: BaseModel, prefix: str = '', supplied: bool = True) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for field in type(model).model_fields:
        value = getattr(model, field)
        path = f'{prefix}/{field}'
        explicit = supplied and field in model.model_fields_set
        origin = 'supplied' if explicit else 'default'
        # Objects, named lines and payment months also get their own row, so an explicit
        # empty object, an emptied list or a null-to-object change is reported as such.
        if isinstance(value, BaseModel):
            rows[path] = {'value': 'present', 'origin': origin}
            rows.update(_inputs(value, path, explicit))
        elif isinstance(value, list) and value and all(isinstance(item, BaseModel) for item in value):
            rows[path] = {'value': [str(item.name) for item in value], 'origin': origin}
            for item in value:
                # Named lines stay aligned if a scenario reorders or adds channels.
                rows.update(_inputs(item, f'{path}/{_segment(item.name)}', explicit))
        elif isinstance(value, dict):
            rows[path] = {'value': sorted(value), 'origin': origin}
            for key, item in value.items():
                rows[f'{path}/{_segment(key)}'] = {'value': item, 'origin': origin}
        else:
            rows[path] = {'value': value, 'origin': origin}
    return rows


def _methods(config: EntityConfig) -> dict[str, str]:
    return {
        'receipts': 'Collection profile' if config.working_capital.collection_profile is not None else 'DSO days',
        'inventory': config.working_capital.inventory_basis,
        'income_tax': ('Income-year provision with explicit cash payments' if config.income_tax is not None
                       else 'Monthly tax approximation'),
    }


def assumption_report(config: EntityConfig, previous: EntityConfig | None = None) -> dict[str, Any]:
    """Show effective assumptions, their origins and changes for human review."""
    current = _inputs(config)
    old = _inputs(previous) if previous is not None else {}
    rows = []
    for path in sorted(current.keys() | old.keys()):
        now, before = current.get(path), old.get(path)
        change = ('not_compared' if previous is None else 'removed' if now is None else
                  'added' if before is None else 'unchanged' if now == before else 'changed')
        rows.append({'path': path, 'value': now['value'] if now else None,
                     'origin': now['origin'] if now else None,
                     'previous_value': before['value'] if before else None,
                     'previous_origin': before['origin'] if before else None, 'change': change})
    scope = [key for key in ('name', 'start_month', 'horizon_months')
             if previous is not None and getattr(config, key) != getattr(previous, key)]
    methods = _methods(config)
    old_methods = _methods(previous) if previous is not None else {}
    method_changes = [key for key in methods if previous is not None and methods[key] != old_methods[key]]
    return {
        'assumption_schema': 1,
        'requires_review': True,
        'comparable': previous is not None and not scope and not method_changes,
        'scope_changes': scope,
        'method_changes': method_changes,
        'methods': methods,
        'previous_methods': old_methods,
        'meaning': 'Effective configuration inputs only. Supplied does not mean sourced or approved. '
                   'Defaults require review. No forecast or statutory calculation is performed.',
        'assumptions': rows,
    }
