"""SessionManager — общая папка для заметок, скриншотов и прочего вывода.

Поддерживаются два layout-режима (см. ``SESSION_LAYOUT`` в ``config.py``):

* ``"monthly"`` (по умолчанию) — все артефакты за календарный месяц
  складываются в одну папку ``YYYY-MM``. Удобно бегло пролистать заметки
  за месяц; на стыке месяцев следующий вызов автоматически создаёт новую
  папку.
* ``"per_session"`` — старое поведение: отдельная папка
  ``YYYY-MM-DD_HH-MM`` на каждый запуск процесса.

Папка создаётся **лениво** при первом сохранении — пустые директории
не плодим.

Потокобезопасность: все мутирующие операции (`save_note`, `save_screenshot`)
сериализуются внутренним `threading.Lock`. Чтения (`current_dir`) могут
вернуть None пока ничего не сохраняли — это валидное состояние.

Layout (monthly):

    <SESSION_BASE_DIR>/
        2026-04/
            notes.txt                                    (все заметки месяца)
            screenshot_2026-04-29_14-30-12.png           (M3)
            screenshot_note_2026-04-29_14-30-12.png      (M7)
            screenshot_note_2026-04-29_14-30-12.txt
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

NOTES_FILE = "notes.txt"
PER_SESSION_DIR_FORMAT = "%Y-%m-%d_%H-%M"
MONTHLY_DIR_FORMAT = "%Y-%m"
FILE_STAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"

# locale-независимые сокращения дней недели (Mon=0)
_WEEKDAY_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

Layout = Literal["per_session", "monthly"]


class SessionManager:
    """Хранит «текущую сессию» и пишет в неё артефакты команд."""

    def __init__(
        self, base_dir: str | Path, *, layout: Layout = "monthly"
    ) -> None:
        if layout not in ("per_session", "monthly"):
            raise ValueError(f"SessionManager: неизвестный layout {layout!r}")
        self._base_dir = Path(base_dir).expanduser()
        self._layout: Layout = layout
        self._current_dir: Path | None = None
        self._current_month: str | None = None  # для авто-перехода месяца
        self._lock = threading.Lock()

    # ---- public ----

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def layout(self) -> Layout:
        return self._layout

    @property
    def current_dir(self) -> Path | None:
        """Папка текущей сессии или None, если ещё ничего не сохраняли."""
        return self._current_dir

    def latest_dir(self) -> Path | None:
        """Папка для кнопки «Открыть»: текущая, либо самая свежая на диске.
        Ничего не создаёт. Возвращает ``None``, если `base_dir` пуст."""
        if self._current_dir is not None:
            return self._current_dir
        if not self._base_dir.exists():
            return None
        try:
            subdirs = [p for p in self._base_dir.iterdir() if p.is_dir()]
        except OSError:
            return None
        if not subdirs:
            return None
        return max(subdirs, key=lambda p: p.stat().st_mtime)

    def ensure_session(self) -> Path:
        """Создать (или переиспользовать) папку и вернуть её."""
        with self._lock:
            return self._ensure_session_locked()

    def save_screenshot(self, png_data: bytes, *, prefix: str = "screenshot") -> Path:
        """Записать PNG-байты в новый файл и вернуть путь.

        Имя — ``<prefix>_YYYY-MM-DD_HH-MM-SS.png``. Коллизия в одну секунду
        (быстрая серия) разрешается суффиксом ``_2``, ``_3``, …."""
        if not png_data:
            raise ValueError("save_screenshot: пустые данные")
        with self._lock:
            session_dir = self._ensure_session_locked()
            stamp = datetime.now().strftime(FILE_STAMP_FORMAT)
            candidate = session_dir / f"{prefix}_{stamp}.png"
            n = 2
            while candidate.exists():
                candidate = session_dir / f"{prefix}_{stamp}_{n}.png"
                n += 1
            candidate.write_bytes(png_data)
            logger.info(
                "Скриншот сохранён: %s (%d KB)", candidate, len(png_data) // 1024
            )
            return candidate

    def save_note(self, text: str) -> Path:
        """Дописать заметку в `notes.txt` и вернуть путь к файлу.

        Каждая заметка идёт отдельной строкой со штампом
        ``[YYYY-MM-DD Пн HH:MM:SS] <text>``."""
        text = (text or "").strip()
        if not text:
            raise ValueError("save_note: пустой текст")
        with self._lock:
            session_dir = self._ensure_session_locked()
            notes_path = session_dir / NOTES_FILE
            now = datetime.now()
            stamp = f"{now.strftime('%Y-%m-%d')} {_WEEKDAY_RU[now.weekday()]} {now.strftime('%H:%M:%S')}"
            with notes_path.open("a", encoding="utf-8") as f:
                f.write(f"[{stamp}] {text}\n")
            logger.info("Заметка сохранена: %s (%d символов)", notes_path, len(text))
            return notes_path

    # ---- internals ----

    def _ensure_session_locked(self) -> Path:
        now = datetime.now()
        if self._layout == "monthly":
            month_key = now.strftime(MONTHLY_DIR_FORMAT)
            # авто-переход на новый месяц для долгоживущего процесса
            if self._current_dir is not None and self._current_month == month_key:
                return self._current_dir
            self._base_dir.mkdir(parents=True, exist_ok=True)
            candidate = self._base_dir / month_key
            candidate.mkdir(parents=True, exist_ok=True)
            if self._current_month != month_key:
                logger.info("Папка месяца: %s", candidate)
            self._current_dir = candidate
            self._current_month = month_key
            return candidate

        # per_session
        if self._current_dir is not None:
            return self._current_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)
        stem = now.strftime(PER_SESSION_DIR_FORMAT)
        candidate = self._base_dir / stem
        n = 2
        while candidate.exists():
            candidate = self._base_dir / f"{stem}_{n}"
            n += 1
        candidate.mkdir(parents=True, exist_ok=False)
        self._current_dir = candidate
        logger.info("Создана новая сессия: %s", candidate)
        return candidate
