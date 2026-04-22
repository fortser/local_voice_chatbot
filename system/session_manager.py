"""SessionManager — единая папка для заметок, скриншотов и прочего вывода.

Сессия создаётся **лениво** при первом сохранении (не при инициализации
ассистента) — пустые папки не плодим, а за весь жизненный цикл процесса
обычно одна сессия. Имя папки — `YYYY-MM-DD_HH-MM` (минут хватает,
коллизии в реальности случаются разве что при ручном повторном запуске
в ту же минуту, тогда добавляется суффикс ``_2``, ``_3``, …).

Потокобезопасность: все мутирующие операции (`save_note`, `save_screenshot`)
сериализуются внутренним `threading.Lock`. Чтения (`current_dir`) могут
вернуть None пока сессия не создана — это валидное состояние.

Layout:

    <SESSION_BASE_DIR>/
        2026-04-22_14-30/
            notes.txt              (накопительный лог заметок, M2)
            screenshot_<ts>.png    (M3)
            screenshot_note_<ts>.png + .txt  (M7)
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

NOTES_FILE = "notes.txt"
SESSION_DIR_FORMAT = "%Y-%m-%d_%H-%M"


class SessionManager:
    """Хранит «текущую сессию» и пишет в неё артефакты команд."""

    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir).expanduser()
        self._current_dir: Path | None = None
        self._lock = threading.Lock()

    # ---- public ----

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def current_dir(self) -> Path | None:
        """Папка текущей сессии или None, если ещё ничего не сохраняли."""
        return self._current_dir

    def ensure_session(self) -> Path:
        """Создать (или переиспользовать) папку текущей сессии и вернуть её."""
        with self._lock:
            return self._ensure_session_locked()

    def save_screenshot(self, png_data: bytes, *, prefix: str = "screenshot") -> Path:
        """Записать PNG-байты в новый файл сессии и вернуть путь.

        Имя — ``<prefix>_YYYYMMDD_HHMMSS.png``. Коллизия в одну секунду
        (быстрая серия) разрешается суффиксом ``_2``, ``_3``, ….
        """
        if not png_data:
            raise ValueError("save_screenshot: пустые данные")
        with self._lock:
            session_dir = self._ensure_session_locked()
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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

        Каждая заметка идёт отдельным блоком: `[HH:MM:SS] <text>\\n`.
        Дописываем, а не перетираем — пользователь за сессию обычно
        накапливает несколько (см. M2 чек-лист «Повторный запиши заметку…»).
        """
        text = (text or "").strip()
        if not text:
            raise ValueError("save_note: пустой текст")
        with self._lock:
            session_dir = self._ensure_session_locked()
            notes_path = session_dir / NOTES_FILE
            stamp = datetime.now().strftime("%H:%M:%S")
            with notes_path.open("a", encoding="utf-8") as f:
                f.write(f"[{stamp}] {text}\n")
            logger.info("Заметка сохранена: %s (%d символов)", notes_path, len(text))
            return notes_path

    # ---- internals ----

    def _ensure_session_locked(self) -> Path:
        if self._current_dir is not None:
            return self._current_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)
        stem = datetime.now().strftime(SESSION_DIR_FORMAT)
        candidate = self._base_dir / stem
        # Обработка коллизии (повторный запуск в ту же минуту).
        n = 2
        while candidate.exists():
            candidate = self._base_dir / f"{stem}_{n}"
            n += 1
        candidate.mkdir(parents=True, exist_ok=False)
        self._current_dir = candidate
        logger.info("Создана новая сессия: %s", candidate)
        return candidate
