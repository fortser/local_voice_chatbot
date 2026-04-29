"""ListRemindersCommand — «перечисли напоминания» (Этап 10+).

INSTANT-команда: читает активные напоминания из ``ReminderScheduler``,
собирает одну русскую фразу через ``core.reminders.listing`` и отдаёт
её в ``pipeline._speak_safely()``. LLM не вовлекаем (см. feedback memory
``feedback_explicit_llm_only``) — генерация детерминированная.

Один TTS-проход вместо N отдельных озвучек: при ``TTS_PROVIDER=xtts +
CUDA`` каждый синтез — это unload Whisper / load XTTS / unload / reload,
поэтому склеиваем всё в одну строку. Заодно интонация естественнее.

Кэш WAV при создании напоминания осознанно не делаем:

* префикс «сейчас у вас N» всё равно динамический (счётчик меняется);
* «через сколько» меняется со временем (хранится абсолютный fire_at);
* напоминание озвучивается ровно один раз при срабатывании — кэш не
  окупается;
* при смене TTS_PROVIDER/speaker накопленные WAV «звучат другим голосом».
"""

from __future__ import annotations

import logging

from commands.base import BaseCommand, CommandContext, CommandType
from core.reminders.listing import format_reminders_list

logger = logging.getLogger(__name__)


class ListRemindersCommand(BaseCommand):
    name = "list_reminders"
    command_type = CommandType.INSTANT
    # ack_after намеренно None: команда сама произносит итоговую фразу,
    # отдельная подтверждающая фраза была бы избыточной.
    ack_after = None
    # Все синонимы ≥2 слов (feedback memory `feedback_two_word_commands`).
    synonyms = (
        "перечисли напоминания",
        "перечисли уведомления",
        "какие напоминания",
        "какие уведомления",
        "список напоминаний",
        "список уведомлений",
    )

    def execute(self, ctx: CommandContext) -> bool:
        pipeline = ctx.pipeline
        scheduler = getattr(pipeline, "reminder_scheduler", None)
        if scheduler is None:
            logger.warning("ListRemindersCommand: scheduler не инициализирован")
            return False

        items = scheduler.list_active()
        phrase = format_reminders_list(items)
        logger.info("ListRemindersCommand: %d active", len(items))
        print(f"📋 {phrase}")
        pipeline._speak_safely(phrase)
        return True
