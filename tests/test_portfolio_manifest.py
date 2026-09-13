import pytest

from pyfpa.portfolio.manifest import ClientRef, clients_of_type, load_portfolio


def test_load_portfolio_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_portfolio(tmp_path / "portfolio.yaml")


def test_load_portfolio_and_filter(tmp_path):
    (tmp_path / "p.yaml").write_text(
        "library: ~/.fpa/library\n"
        "clients:\n"
        "  - { path: ~/clients/acme, type: d2c-inventory }\n"
        "  - { path: ~/clients/haul, type: trucking }\n"
        "  - { path: ~/clients/peak, type: d2c-inventory }\n"
    )
    pf = load_portfolio(tmp_path / "p.yaml")
    assert pf.library == "~/.fpa/library"
    assert len(pf.clients) == 3
    d2c = clients_of_type(pf, "d2c-inventory")
    assert [c.path for c in d2c] == ["~/clients/acme", "~/clients/peak"]
    assert all(isinstance(c, ClientRef) for c in d2c)


def test_repeated_workspace_is_rejected(tmp_path):
    # F080: one workspace listed three times used to yield support 3 from a
    # single distinct source.
    (tmp_path / "dup.yaml").write_text(
        "library: ~/.fpa/library\n"
        "clients:\n"
        f"  - {{ path: {tmp_path.as_posix()}/acme, type: d2c }}\n"
        f"  - {{ path: {tmp_path.as_posix()}/acme, type: d2c }}\n"
    )
    with pytest.raises(ValueError, match="same workspace twice"):
        load_portfolio(tmp_path / "dup.yaml")


def test_the_same_workspace_spelt_two_ways_is_still_one_client(tmp_path):
    (tmp_path / "alias.yaml").write_text(
        "library: ~/.fpa/library\n"
        "clients:\n"
        f"  - {{ path: {tmp_path.as_posix()}/acme, type: d2c }}\n"
        f"  - {{ path: {tmp_path.as_posix()}/./acme, type: d2c }}\n"
    )
    with pytest.raises(ValueError, match="same workspace twice"):
        load_portfolio(tmp_path / "alias.yaml")
