from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_declares_the_published_package_lifecycle() -> None:
    # F443: 0.1.1 is on PyPI with an immutable release, so the README must not
    # tell a reader the package is unpublished.
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())

    assert "**Package lifecycle:** published." in readme
    assert "not published to PyPI" not in readme
    assert "source-only" not in readme
    assert "pip install openfpa" not in readme
    assert "`au-fpa-pack`" in readme
