from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import yaml

from pyfpa.cli_helpers import _failure, _require_initialized, _root, _success
from pyfpa.memory.workspace import Workspace


def command_model_assumptions(args: argparse.Namespace) -> int:
    from pyfpa.analysis.assumptions import assumption_report
    from pyfpa.config.loader import load_config

    root = Workspace.open(args.path).root
    if (failure := _require_initialized('model-assumptions', args, 'reviewing model assumptions')) is not None:
        return failure
    try:
        paths = [Path(args.config)] + ([Path(args.previous_config)] if args.previous_config else [])
        original = [path.read_bytes() for path in paths]
        configs = [load_config(path) for path in paths]
        if any(path.read_bytes() != raw for path, raw in zip(paths, original, strict=True)):
            raise ValueError('configuration changed while being read')
        report = assumption_report(configs[0], configs[1] if len(configs) == 2 else None)
        report['config_sha256'] = hashlib.sha256(original[0]).hexdigest()
        report['previous_config_sha256'] = hashlib.sha256(original[1]).hexdigest() if len(original) == 2 else None
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return _failure('model-assumptions', root, 'invalid_config', str(exc))
    return _success('model-assumptions', root, report)


def command_model_export(args: argparse.Namespace) -> int:
    from pyfpa.config.loader import load_config
    from pyfpa.excel.model_workbook import model_to_excel

    opened = Workspace.open(args.path)
    root = opened.root
    if (failure := _require_initialized("model-export", args, "exporting a model workbook")) is not None:
        return failure
    try:
        cfg = load_config(args.config)
    except Exception as exc:
        return _failure("model-export", root, "invalid_config", str(exc))
    try:
        out_path = _root(args.out)
        if out_path.suffix.lower() != ".xlsx":
            raise ValueError("model export requires an .xlsx output path")
        if out_path.exists() and out_path.samefile(args.config):
            raise ValueError("model export must not overwrite the source configuration")
        model_to_excel(cfg, out_path)
    except Exception as exc:
        return _failure("model-export", root, "export_failed", str(exc))
    return _success(
        "model-export",
        root,
        {
            "workbook_path": str(out_path),
            "sheets": ["Assumptions", "Model"],
            "config": str(args.config),
            "entity": cfg.name,
        },
    )
