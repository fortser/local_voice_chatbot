"""General-purpose helpers.

Currently hosts ``save_state_atomic`` — the tmp-file → ``os.replace`` pattern
borrowed from benchmark_runner.py. Using ``os.replace`` guarantees that a crash
mid-write never leaves a half-written state file on disk (either the old file
remains intact, or the new file has fully landed).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def save_state_atomic(path: str | os.PathLike[str], payload: Any) -> None:
    """Serialise ``payload`` to JSON at ``path`` atomically.

    Writes to a tmp file in the same directory, then ``os.replace``-s over the
    target. On POSIX and modern Windows, ``os.replace`` is atomic — readers
    either see the old file or the new file, never a truncated one.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=str(target.parent),
    )
    tmp = Path(tmp_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
