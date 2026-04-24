"""Планировщик напоминаний на ``threading.Timer``.

Каждое активное напоминание держит собственный таймер. При срабатывании
таймер дергает ``fire_callback(text)`` — обычно он ставится так, чтобы
под общим pipeline-lock'ом озвучить фразу «вы просили напомнить …».
Если в момент срабатывания идёт другой турн, вызов callback'а блокируется
на acquire() — напоминание проигрывается сразу после окончания текущего
разговора (дизайн-решение: ставим в очередь, а не перебиваем).

Просроченные напоминания при старте проигрываются последовательно через
тот же callback; порядок — по возрастанию ``fire_at``.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Callable

from core.reminders.storage import ReminderStorage

logger = logging.getLogger(__name__)

FireCallback = Callable[[str], None]


class ReminderScheduler:
    def __init__(
        self,
        storage: ReminderStorage,
        fire_callback: FireCallback,
    ) -> None:
        self._storage = storage
        self._fire_callback = fire_callback
        self._timers: dict[str, threading.Timer] = {}
        self._mutex = threading.Lock()

    def add(self, delay_seconds: int, text: str) -> str:
        """Создать напоминание на ``now + delay_seconds`` секунд."""
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        reminder_id = uuid.uuid4().hex[:12]
        fire_at = time.time() + delay_seconds
        reminder = {
            "id": reminder_id,
            "fire_at": fire_at,
            "text": text,
        }
        self._storage.add(reminder)
        with self._mutex:
            self._schedule_timer(reminder)
        logger.info(
            "Reminder scheduled: id=%s in=%ds text=%r",
            reminder_id, delay_seconds, text[:80],
        )
        return reminder_id

    def load_and_restore(self) -> tuple[int, int]:
        """Прочитать файл, запустить активные, проиграть просроченные.

        Возвращает ``(active_count, overdue_count)``.
        """
        now = time.time()
        overdue: list[dict] = []
        active: list[dict] = []
        for r in self._storage.load_all():
            if float(r["fire_at"]) <= now:
                overdue.append(r)
            else:
                active.append(r)
        overdue.sort(key=lambda r: r["fire_at"])

        with self._mutex:
            for r in active:
                self._schedule_timer(r)

        for r in overdue:
            logger.info(
                "Overdue reminder at startup: id=%s text=%r",
                r["id"], r["text"][:80],
            )
            self._storage.remove(r["id"])
            try:
                self._fire_callback(r["text"])
            except Exception:
                logger.exception("Overdue fire_callback failed: %s", r["id"])

        logger.info(
            "Reminders restored: active=%d, overdue_played=%d",
            len(active), len(overdue),
        )
        return len(active), len(overdue)

    def active_ids(self) -> list[str]:
        with self._mutex:
            return list(self._timers.keys())

    def shutdown(self) -> None:
        with self._mutex:
            for t in self._timers.values():
                t.cancel()
            self._timers.clear()

    # ---- внутреннее ----

    def _schedule_timer(self, reminder: dict) -> None:
        delay = max(0.0, float(reminder["fire_at"]) - time.time())
        t = threading.Timer(delay, self._fire, args=(reminder,))
        t.daemon = True
        t.name = f"Reminder-{reminder['id']}"
        t.start()
        self._timers[reminder["id"]] = t

    def _fire(self, reminder: dict) -> None:
        rid = reminder["id"]
        with self._mutex:
            self._timers.pop(rid, None)
        self._storage.remove(rid)
        try:
            self._fire_callback(reminder["text"])
        except Exception:
            logger.exception("Reminder fire_callback failed: %s", rid)
