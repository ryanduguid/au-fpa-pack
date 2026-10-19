"""Stage file exports beside their destination before replacing it."""

from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def staged_output(path: str | Path) -> Iterator[Path]:
    """Keep the previous export until the producer has closed a complete file.

    Resolve symlinks as direct file writes did. Replacement affects this one
    path; other hard links continue to refer to the previous file.
    """
    destination = Path(path).resolve()
    with tempfile.TemporaryDirectory(prefix=".fpa-export-", dir=destination.parent) as folder:
        staged = Path(folder) / destination.name
        yield staged
        if os.name != "nt" and destination.exists():
            staged.chmod(stat.S_IMODE(destination.stat().st_mode))
        os.replace(staged, destination)
