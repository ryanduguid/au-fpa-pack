from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, model_validator

from pyfpa.io.loaders import read_yaml


class ClientRef(BaseModel):
    path: str          # client workspace root (contains .fpa/ and skills/)
    type: str          # business-type tag (the clustering key)


def canonical_client_path(path: str) -> str:
    """The workspace identity used to count support: one workspace, one client."""
    return str(Path(path).expanduser().resolve())


def require_distinct_clients(clients: list[ClientRef]) -> list[ClientRef]:
    """Reject a client list that names the same workspace more than once.

    Repeated entries are the same evidence counted twice: they would inflate
    prior support and fill leave-one-out folds with copies of the held-out
    client. Raising keeps the duplication visible instead of averaging it in.

    This check sees paths only. Two copies of one client under different paths
    pass it, so the promotion gate counts distinct clients again by normalised
    business-profile heading, and treats a workspace with no heading as
    establishing no client (`pyfpa.portfolio.approval.check_promotion_approval`).
    """
    seen: dict[str, str] = {}
    for client in clients:
        key = canonical_client_path(client.path)
        if key in seen:
            raise ValueError(
                f"portfolio lists the same workspace twice: {seen[key]!r} and {client.path!r}"
            )
        seen[key] = client.path
    return clients


class Portfolio(BaseModel):
    library: str
    clients: list[ClientRef]

    @model_validator(mode="after")
    def _clients_are_distinct(self) -> Portfolio:
        require_distinct_clients(self.clients)
        return self


def load_portfolio(path: str | Path) -> Portfolio:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"portfolio manifest not found: {p}")
    return Portfolio.model_validate(read_yaml(p))


def clients_of_type(portfolio: Portfolio, business_type: str) -> list[ClientRef]:
    return [c for c in portfolio.clients if c.type == business_type]
