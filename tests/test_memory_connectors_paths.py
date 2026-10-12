"""Refusal and recovery paths in pyfpa.memory.connectors."""

from pathlib import Path
from typing import Any

import pytest

from pyfpa.memory import connectors
from pyfpa.memory.connectors import (
    ConnectorManifest,
    _ensure_plain_directory,
    _replace_generated_tree,
    load_connector_manifest,
    load_connector_manifests,
    save_connector_manifest,
    scaffold_connector_bundle,
    validate_connector_bundle,
)
from pyfpa.memory.lineage import MappingRegistry, MappingRule
from pyfpa.memory.workspace import Workspace

NAME = "quickbooks-pl"


def _mappings() -> MappingRegistry:
    return MappingRegistry(mappings=[
        MappingRule(source_id="gl-actuals", source_value="Product Revenue", target="revenue.product"),
        MappingRule(source_id="gl-actuals", source_value="Rent", target="opex.rent"),
        MappingRule(
            source_id="gl-actuals",
            source_value="Suspense",
            target="",
            status="ignored",
            rationale="Cleared before close",
        ),
    ])


def _fixture(path: Path, body: str = "Product Revenue,100\nRent,(20)\n") -> Path:
    path.write_text("Account,Amount\n" + body, encoding="utf-8")
    return path


def _manifest_values(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "name": NAME,
        "source_id": "gl-actuals",
        "description": "Pull the monthly P&L.",
        "auth_method": "host_environment",
        "source_account_column": "Account",
        "source_amount_column": "Amount",
        "fixture_path": "fixtures/source.csv",
        "expected_totals": {"revenue.product": 100.0},
    }
    values.update(changes)
    return values


def _scaffold(company_root: Path, fixture: Path, **changes: Any):
    kwargs: dict[str, Any] = {
        "name": NAME,
        "source_id": "gl-actuals",
        "description": "Pull and normalize the monthly P&L.",
        "auth_method": "host_environment",
        "fixture": fixture,
        "account_column": "Account",
        "amount_column": "Amount",
        "mappings": _mappings(),
    }
    kwargs.update(changes)
    return scaffold_connector_bundle(company_root, **kwargs)


def _generated(root: Path) -> Path:
    return Workspace.open(root).generated_path("connectors")


def _leftovers(root: Path) -> list[Path]:
    return sorted(_generated(root).glob(f".{NAME}.*"))


# --- _ensure_plain_directory -------------------------------------------------

def test_directory_created_by_another_process_is_accepted(tmp_path, monkeypatch):
    # The lstat reports the directory missing, then mkdir finds it already made.
    (tmp_path / "connectors").mkdir()
    monkeypatch.setattr(connectors, "_lstat", lambda path: None)

    _ensure_plain_directory(tmp_path, tmp_path / "connectors")

    assert (tmp_path / "connectors").is_dir()  # nosec B101: pytest outcome assertion


def test_linked_directory_is_refused_before_creating_children(tmp_path, directory_link):
    root = tmp_path / "company"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    directory_link(root / "connectors", outside)

    with pytest.raises(ValueError, match="must not contain symlinks or reparse points"):
        _ensure_plain_directory(root, root / "connectors" / "generated")

    assert list(outside.iterdir()) == []  # nosec B101: pytest outcome assertion


def test_file_in_directory_chain_is_refused(tmp_path):
    (tmp_path / "connectors").write_text("not a directory", encoding="utf-8")

    with pytest.raises(NotADirectoryError, match="connector workspace path is not a directory"):
        _ensure_plain_directory(tmp_path, tmp_path / "connectors" / "generated")


# --- _replace_generated_tree -------------------------------------------------

def test_existing_bundle_tree_with_link_is_refused_on_overwrite(tmp_path, directory_link):
    root = tmp_path / "company"
    bundle = _generated(root) / NAME
    bundle.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    directory_link(bundle / "fixtures", outside)

    with pytest.raises(ValueError, match="bundle trees must not contain symlinks"):
        _scaffold(root, _fixture(tmp_path / "redacted.csv"), overwrite=True)

    assert sentinel.read_text(encoding="utf-8") == "keep"  # nosec B101: pytest outcome assertion
    assert _leftovers(root) == []  # nosec B101: pytest outcome assertion


def test_existing_bundle_file_is_refused(tmp_path):
    bundle = _generated(tmp_path) / NAME
    bundle.parent.mkdir(parents=True)
    bundle.write_text("not a bundle", encoding="utf-8")

    with pytest.raises(NotADirectoryError, match="connector bundle is not a directory"):
        _scaffold(tmp_path, _fixture(tmp_path / "redacted.csv"), overwrite=True)

    assert bundle.read_text(encoding="utf-8") == "not a bundle"  # nosec B101: pytest outcome assertion


def test_bundle_created_during_build_is_not_replaced_without_overwrite(tmp_path):
    workspace = Workspace.open(tmp_path)
    bundle = _generated(tmp_path) / NAME

    def build(staging: Path) -> None:
        (staging / "README.md").write_text("staged", encoding="utf-8")
        bundle.mkdir()
        (bundle / "README.md").write_text("concurrent", encoding="utf-8")

    with pytest.raises(FileExistsError, match="connector bundle already exists"):
        _replace_generated_tree(workspace, bundle, overwrite=False, build_fn=build)

    assert (bundle / "README.md").read_text(encoding="utf-8") == "concurrent"  # nosec B101: pytest outcome assertion
    assert _leftovers(tmp_path) == []  # nosec B101: pytest outcome assertion


def test_file_created_at_bundle_during_build_is_not_replaced(tmp_path):
    workspace = Workspace.open(tmp_path)
    bundle = _generated(tmp_path) / NAME

    def build(staging: Path) -> None:
        bundle.write_text("concurrent file", encoding="utf-8")

    with pytest.raises(NotADirectoryError, match="connector bundle is not a directory"):
        _replace_generated_tree(workspace, bundle, overwrite=True, build_fn=build)

    assert bundle.read_text(encoding="utf-8") == "concurrent file"  # nosec B101: pytest outcome assertion
    assert _leftovers(tmp_path) == []  # nosec B101: pytest outcome assertion


def test_failed_first_install_removes_staging(tmp_path, monkeypatch):
    real_rename = Path.rename

    def fail_staging_swap(path, target):
        if path.name.startswith(f".{NAME}.staging-"):
            raise OSError("simulated install failure")
        return real_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_staging_swap)

    with pytest.raises(OSError, match="simulated install failure"):
        _scaffold(tmp_path, _fixture(tmp_path / "redacted.csv"))

    assert not (_generated(tmp_path) / NAME).exists()  # nosec B101: pytest outcome assertion
    assert _leftovers(tmp_path) == []  # nosec B101: pytest outcome assertion


# --- manifest -----------------------------------------------------------------

@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"expected_totals": {" ": 1.0}}, "expected total names must not be empty"),
        ({"expected_totals": {"revenue.product": float("nan")}}, "expected totals must be finite"),
        ({"expected_totals": {"revenue.product": float("inf")}}, "expected totals must be finite"),
        ({"source_amount_column": "Account"}, "source account and amount columns must differ"),
    ],
)
def test_manifest_rejects_invalid_contract(changes, message):
    with pytest.raises(ValueError, match=message):
        ConnectorManifest(**_manifest_values(**changes))


def test_manifest_round_trips_through_an_explicit_yaml_path(tmp_path):
    manifest = ConnectorManifest(**_manifest_values())
    path = tmp_path / "nested" / "custom.yaml"

    save_connector_manifest(manifest, path)

    assert path.is_file()  # nosec B101: pytest outcome assertion
    assert load_connector_manifest(path) == manifest  # nosec B101: pytest outcome assertion


def test_listing_without_connector_root_is_empty(tmp_path):
    assert load_connector_manifests(tmp_path) == []  # nosec B101: pytest outcome assertion


def test_listing_rejects_manifest_named_for_another_directory(tmp_path):
    save_connector_manifest(ConnectorManifest(**_manifest_values()), _generated(tmp_path) / "renamed")

    with pytest.raises(ValueError, match="'renamed' contains manifest for 'quickbooks-pl'"):
        load_connector_manifests(tmp_path)


# --- scaffold_connector_bundle -----------------------------------------------

def test_scaffold_requires_an_existing_fixture(tmp_path):
    with pytest.raises(FileNotFoundError, match="connector fixture not found"):
        _scaffold(tmp_path, tmp_path / "absent.csv")


def test_scaffold_requires_a_csv_fixture(tmp_path):
    fixture = tmp_path / "redacted.txt"
    fixture.write_text("Account,Amount\nRent,1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="requires a CSV fixture"):
        _scaffold(tmp_path, fixture)


def test_scaffold_requires_a_mapped_total(tmp_path):
    fixture = _fixture(tmp_path / "redacted.csv", "Suspense,5\n")

    with pytest.raises(ValueError, match="at least one mapped total"):
        _scaffold(tmp_path, fixture)

    assert not (_generated(tmp_path) / NAME).exists()  # nosec B101: pytest outcome assertion


# --- validate_connector_bundle -----------------------------------------------

def test_validation_requires_the_bundle(tmp_path):
    with pytest.raises(FileNotFoundError, match="connector bundle not found"):
        validate_connector_bundle(tmp_path, name=NAME, mappings=_mappings())


def test_validation_refuses_a_bundle_file(tmp_path):
    bundle = _generated(tmp_path) / NAME
    bundle.parent.mkdir(parents=True)
    bundle.write_text("not a bundle", encoding="utf-8")

    with pytest.raises(NotADirectoryError, match="connector bundle is not a directory"):
        validate_connector_bundle(tmp_path, name=NAME, mappings=_mappings())


def test_validation_refuses_manifest_named_for_another_bundle(tmp_path):
    save_connector_manifest(ConnectorManifest(**_manifest_values()), _generated(tmp_path) / "renamed")

    with pytest.raises(ValueError, match="'renamed' contains manifest for 'quickbooks-pl'"):
        validate_connector_bundle(tmp_path, name="renamed", mappings=_mappings())


def test_validation_requires_the_bundle_fixture(tmp_path):
    _scaffold(tmp_path, _fixture(tmp_path / "redacted.csv"))
    (_generated(tmp_path) / NAME / "fixtures" / "source.csv").unlink()

    with pytest.raises(FileNotFoundError, match="connector fixture not found"):
        validate_connector_bundle(tmp_path, name=NAME, mappings=_mappings())


def test_validation_refuses_a_fixture_outside_the_bundle(tmp_path, monkeypatch):
    # The manifest validator refuses absolute and '..' paths, so this stands in
    # for a manifest that reached validation without passing through it.
    root = Workspace.open(tmp_path).root
    _scaffold(root, _fixture(tmp_path / "redacted.csv"))
    outside = _fixture(root / "outside.csv")
    forged = ConnectorManifest.model_construct(**_manifest_values(fixture_path=str(outside)))
    monkeypatch.setattr(connectors, "load_connector_manifest", lambda path: forged)

    with pytest.raises(ValueError, match="fixture path escapes connector bundle"):
        validate_connector_bundle(root, name=NAME, mappings=_mappings())
