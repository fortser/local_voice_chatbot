"""Structured logging setup: console + rotating file.

Idempotent — safe to call ``setup_logging()`` more than once.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

from config import (
    LOG_BACKUP_COUNT,
    LOG_FILE,
    LOG_LEVEL,
    LOG_MAX_BYTES,
    LOGS_DIR,
    RECOGNIZED_LOG_FILE,
    UNRECOGNIZED_LOG_FILE,
)

_LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Имя dedicated-логгера для нераспознанных фраз. Не пишет в общий
# voice_ai.log и в консоль — только в свой файл, чтобы было удобно
# периодически просматривать «что чаще всего промахивается».
UNRECOGNIZED_LOGGER_NAME = "shura.unrecognized"
# Симметричный логгер для распознанных команд: пишет TSV-строки
# `command\tsynonym\tfull_text` в logs/recognized.log для подсчёта
# статистики использования (какие команды и формулировки чаще всего).
RECOGNIZED_LOGGER_NAME = "shura.recognized"


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

    # Отдельный логгер для нераспознанных команд — пишет ТОЛЬКО в
    # свой файл, не попадает в общий voice_ai.log и в консоль.
    unrec = logging.getLogger(UNRECOGNIZED_LOGGER_NAME)
    unrec.setLevel(logging.INFO)
    unrec.propagate = False  # критично: иначе всё уйдёт и в root → consoles
    unrec_formatter = logging.Formatter(
        "%(asctime)s\t%(message)s", datefmt=_DATE_FORMAT
    )
    unrec_handler = RotatingFileHandler(
        UNRECOGNIZED_LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    unrec_handler.setFormatter(unrec_formatter)
    unrec.addHandler(unrec_handler)

    rec = logging.getLogger(RECOGNIZED_LOGGER_NAME)
    rec.setLevel(logging.INFO)
    rec.propagate = False
    rec_formatter = logging.Formatter(
        "%(asctime)s\t%(message)s", datefmt=_DATE_FORMAT
    )
    rec_handler = RotatingFileHandler(
        RECOGNIZED_LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    rec_handler.setFormatter(rec_formatter)
    rec.addHandler(rec_handler)

    root._voice_ai_configured = True  # type: ignore[attr-defined]
    return root
