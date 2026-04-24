"""Подсистема напоминаний (Этап 10).

* :mod:`parser` — regex-парсер фраз «напомни через N минут …».
* :mod:`storage` — JSON-персистентность (абсолютный ``fire_at``).
* :mod:`scheduler` — ``threading.Timer`` на каждое активное напоминание.
* :mod:`num_to_words` — конвертер «20 минут» → «двадцать минут» для
  синтезатора (Silero не проговаривает арабские цифры корректно).
"""

from core.reminders.parser import parse_reminder_tail
from core.reminders.scheduler import ReminderScheduler
from core.reminders.storage import ReminderStorage

__all__ = ["parse_reminder_tail", "ReminderScheduler", "ReminderStorage"]
