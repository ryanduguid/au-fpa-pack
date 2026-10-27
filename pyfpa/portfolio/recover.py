from __future__ import annotations

import math
from pathlib import Path

from pyfpa.backtest.snapshot import Snapshot, load_snapshot
from pyfpa.memory.workspace import Workspace


def recover_actuals(snapshot: Snapshot) -> dict[str, float]:
    """Recover the realised actuals from a scored snapshot by inverting the stored
    per-line error, (predicted - actual) / |actual|: actual = predicted / (1 + error)
    for a positive actual and predicted / (1 - error) for a negative one.

    A score that records `actual_signs` is inverted by each line's sign, and each
    recovered actual must be nonzero with that sign. A score without them was
    written either by 0.3.0 or earlier, which divided by the signed actual so that
    actual = predicted / (1 + error) for either sign, or by an unreleased build
    that divided by |actual|. Such a line is recovered only when both readings
    give the same actual; a line that also fits a different negative actual raises
    ValueError naming it, and rescoring the snapshot records its signs.

    Only scored lines are recoverable; an unscored snapshot yields {}. A line
    whose error makes the divisor 0 is unrecoverable and raises ValueError.
    Consumed predictions, errors and recovered actuals must be finite."""
    score = snapshot.score
    if score is None:
        return {}
    signs = score.actual_signs
    unresolved = [line for line, error in score.per_line.items()
                  if line not in snapshot.predicted or (signs is not None and line not in signs)
                  or error == -(1 if signs is None else signs[line])]
    if unresolved:
        raise ValueError(f"cannot recover actuals for lines: {unresolved}")
    out: dict[str, float] = {}
    refused: list[str] = []
    for line, error in score.per_line.items():
        predicted = snapshot.predicted[line]
        sign = 1 if signs is None else signs[line]
        message = f"recovered actual {line!r} must have finite operands and result"
        try:
            if not math.isfinite(predicted) or not math.isfinite(error):
                raise ValueError(message)
            out[line] = predicted / (1.0 + sign * error)
            if not math.isfinite(out[line]):
                raise ValueError(message)
        except (TypeError, OverflowError) as invalid:
            raise ValueError(message) from invalid
        if signs is None:
            # predicted / (1 - error) is a second, negative fit when it is below 0
            # and differs from predicted / (1 + error); with predicted 0 and error 1
            # every negative actual fits.
            if ((predicted > 0 and error > 1) or (predicted < 0 and error < 1 and error != 0)
                    or (predicted == 0 and error == 1)):
                refused.append(line)
        elif out[line] == 0 or (out[line] > 0) != (sign > 0):
            refused.append(line)
    if refused:
        reason = ("the score records no actual signs and each also fits a different "
                  "negative actual; rescore the snapshot" if signs is None
                  else "the recovered value does not have the recorded sign")
        raise ValueError(f"cannot recover actuals for lines {refused}: {reason}")
    return out


def best_snapshot(client_path: str | Path) -> Snapshot | None:
    """The lowest-fitness scored snapshot in <client>/.fpa/forecasts/ - the
    assumptions that worked best for that client. None if no snapshot has a finite,
    non-negative fitness."""
    forecasts = Workspace.open(client_path).memory / "forecasts"
    if not forecasts.exists():
        return None
    snaps = [load_snapshot(f) for f in sorted(forecasts.glob("*.snapshot.yaml"))]
    scored = [(s.score.fitness, s) for s in snaps
              if s.score is not None and math.isfinite(s.score.fitness) and s.score.fitness >= 0]
    return min(scored, key=lambda pair: pair[0])[1] if scored else None
