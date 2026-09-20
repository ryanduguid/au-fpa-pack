from __future__ import annotations

import copy
import statistics

from pydantic import BaseModel

from pyfpa.backtest.score import (
    DEFAULT_SCORE_LINES,
    ScoreResult,
    extract_lines,
    score_forecast,
)
from pyfpa.backtest.snapshot import Snapshot
from pyfpa.config.schemas import EntityConfig
from pyfpa.memory.paths import apply_override
from pyfpa.models.cashflow import cashflow_from_config
from pyfpa.portfolio.approval import candidate_digest, resolved_support
from pyfpa.portfolio.manifest import (
    ClientRef,
    canonical_client_path,
    require_distinct_clients,
)
from pyfpa.portfolio.mine import PriorCandidate, client_driver_value
from pyfpa.portfolio.recover import best_snapshot, recover_actuals


class ValidationResult(BaseModel):
    mean_delta: float
    n_folds: int
    validated: bool
    # The candidate this result validates. promote_prior refuses a result whose
    # digest is not the candidate's, so a result cannot be carried across to a
    # different or later candidate.
    candidate_digest: str = ""


def validate_prior(
    driver: str,
    type_clients: list[ClientRef],
    *,
    tolerance: float = 0.0,
    candidate: PriorCandidate | None = None,
) -> ValidationResult:
    """Leave-one-out cross-client check. For each usable client, derive `driver`'s
    value as the median across the OTHER clients, apply it to the held-out client's
    best-snapshot config, re-forecast, and score against that client's recovered
    actuals. A prior is `validated` if the mean fitness delta (new - original) is
    <= tolerance with >= 2 folds - a peer-derived value does not degrade held-out fit.
    Repeated workspaces are rejected: a fold whose peers include copies of the
    held-out client is not held out.

    Pass `candidate` to stamp its digest into the result. Without it the digest
    stays empty and `promote_prior` refuses the result: a fitness check on a
    driver is not evidence about a particular candidate."""
    require_distinct_clients(type_clients)
    digest = _candidate_digest_for(driver, type_clients, candidate)
    usable: list[tuple[float, Snapshot, ScoreResult]] = []
    for c in type_clients:
        snap = best_snapshot(c.path)
        value = client_driver_value(c, driver)
        if snap is not None and snap.score is not None and value is not None:
            recorded_lines = set(snap.score.per_line)
            try:
                recovered = recover_actuals(snap)
            except ValueError:
                continue
            if recorded_lines and recorded_lines == set(snap.score.weights) and all(
                line in recovered and recovered[line] != 0 for line in recorded_lines
            ):
                usable.append((value, snap, snap.score))
    n = len(usable)
    if n < 2:
        return ValidationResult(
            mean_delta=0.0, n_folds=n, validated=False, candidate_digest=digest
        )

    deltas = []
    for i, (_, snap, score) in enumerate(usable):
        peer_values = [usable[j][0] for j in range(n) if j != i]
        prior_value = statistics.median(peer_values)
        data = copy.deepcopy(snap.assumptions)
        apply_override(data, driver, prior_value)
        forecast = cashflow_from_config(EntityConfig.model_validate(data))
        # Score over the SAME lines/weights Loop A used for this snapshot, so the new
        # fitness and the stored fitness are apples-to-apples (not assumed defaults).
        scored_lines = list(score.per_line) or DEFAULT_SCORE_LINES
        predicted = extract_lines(forecast, scored_lines)
        new_fitness = score_forecast(
            predicted, recover_actuals(snap), weights=score.weights or None
        ).fitness
        deltas.append(new_fitness - score.fitness)

    mean_delta = statistics.fmean(deltas)
    return ValidationResult(
        mean_delta=mean_delta,
        n_folds=n,
        validated=mean_delta <= tolerance,
        candidate_digest=digest,
    )


def _candidate_digest_for(
    driver: str, type_clients: list[ClientRef], candidate: PriorCandidate | None
) -> str:
    """The digest to stamp, refusing a candidate this run does not validate."""
    if candidate is None:
        return ""
    if candidate.driver != driver:
        raise ValueError(
            f"candidate drives {candidate.driver!r}, validation is for {driver!r}"
        )
    known = {canonical_client_path(client.path) for client in type_clients}
    missing = [path for path in resolved_support(candidate.support) if path not in known]
    if missing:
        raise ValueError(
            f"candidate support includes {len(missing)} workspace(s) outside the "
            "validated client list, so the folds do not hold them out"
        )
    if candidate.business_type not in {client.type for client in type_clients}:
        raise ValueError("candidate business type does not match the validated clients")
    values = [client_driver_value(client, driver) for client in type_clients]
    values = [value for value in values if value is not None]
    if not values or candidate.value != statistics.median(values):
        raise ValueError("candidate value is not the value represented by the validated clients")
    return candidate_digest(candidate)
