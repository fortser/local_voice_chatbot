"""Persistent startup durations, independent of Qt and model providers."""

from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from statistics import mean

logger = logging.getLogger(__name__)

DEFAULT_STARTUP_SECONDS = 25.0
STARTUP_HISTORY_SIZE = 5


class StartupTimings:
    """Append-only JSONL journal; estimate from the last five ready startups."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def recent_durations(self) -> list[float]:
        durations: deque[float] = deque(maxlen=STARTUP_HISTORY_SIZE)
        try:
            with self.path.open(encoding="utf-8") as source:
                for line in source:
                    try:
                        entry = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(entry, dict) or entry.get("status") != "ready":
                        continue
                    duration = entry.get("duration_s")
                    if (isinstance(duration, (int, float)) and not isinstance(duration, bool)
                            and isfinite(duration) and duration > 0):
                        durations.append(float(duration))
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError):
            logger.warning("Could not read startup journal: %s", self.path, exc_info=True)
        return list(durations)

    def estimate_seconds(self) -> float:
        durations = self.recent_durations()
        return mean(durations) if durations else DEFAULT_STARTUP_SECONDS

    def record(self, duration_s: float, status: str) -> None:
        if not isfinite(duration_s) or duration_s <= 0:
            raise ValueError("Startup duration must be positive and finite")
        if status not in {"ready", "error", "cancelled"}:
            raise ValueError(f"Unknown startup status: {status}")
        durations = self.recent_durations()
        if status == "ready":
            durations = [*durations, duration_s][-STARTUP_HISTORY_SIZE:]
        entry = {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "duration_s": duration_s,
            "average_s": mean(durations) if durations else DEFAULT_STARTUP_SECONDS,
            "sample_count": len(durations),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Leading newline isolates a partial record after an interrupted write.
            with self.path.open("a", encoding="utf-8") as target:
                target.write("\n" + json.dumps(entry, ensure_ascii=False, allow_nan=False) + "\n")
        except OSError:
            logger.warning("Could not write startup journal: %s", self.path, exc_info=True)
