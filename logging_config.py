"""Structured logging setup: console + rotating file.

Idempotent — safe to call ``setup_logging()`` more than once.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

from config import LOG_BACKUP_COUNT, LOG_FILE, LOG_LEVEL, LOG_MAX_BYTES, LOGS_DIR

_LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str | int | None = None) -> logging.Logger:
    """Configure the root logger with console + rotating file handlers.

    Returns the root logger. Calling twice won't duplicate handlers.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    resolved_level = level if level is not None else LOG_LEVEL
    root.setLevel(resolved_level)

    if getattr(root, "_voice_ai_configured", False):
        return root

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    root._voice_ai_configured = True  # type: ignore[attr-defined]
    return root
