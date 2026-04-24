"""JSON-персистентность списка напоминаний.

Формат файла — массив объектов:

    [{"id": "<hex>", "fire_at": 1735686000.0, "text": "проверить кашу"}, ...]

``fire_at`` — абсолютный POSIX timestamp (UTC). Пересчёт оставшегося
времени при старте не нужен: время срабатывания зафиксировано в момент
создания напоминания.

Запись атомарная (через .tmp + replace), чтобы kill -9 посередине не
оставил файл повреждённым. Список небольшой (единицы–десятки записей),
поэтому перезаписываем целиком на каждое add/remove — проще и надёжнее
частичных правок.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


class ReminderStorage:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        # Сериализует конкурентные add/remove из потоков таймеров.
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def load_all(self) -> list[dict]:
        if not self._path.is_file():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Повреждённый файл напоминаний: %s", self._path)
            return []
        if not isinstance(data, list):
            logger.warning("Файл напоминаний не-список, игнорирую: %s", self._path)
            return []
        return [r for r in data if self._is_valid(r)]

    def save_all(self, reminders: Iterable[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = list(reminders)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    def add(self, reminder: dict) -> None:
        with self._lock:
            items = self.load_all()
            items.append(reminder)
            self.save_all(items)

    def remove(self, reminder_id: str) -> None:
        with self._lock:
            items = [r for r in self.load_all() if r.get("id") != reminder_id]
            self.save_all(items)

    @staticmethod
    def _is_valid(r: object) -> bool:
        return (
            isinstance(r, dict)
            and isinstance(r.get("id"), str)
            and isinstance(r.get("text"), str)
            and isinstance(r.get("fire_at"), (int, float))
        )
