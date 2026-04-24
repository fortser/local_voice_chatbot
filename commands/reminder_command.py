"""ReminderCommand — «поставь напоминание …» (Этап 10).

Паттерн такой же, как у :class:`NoteCommand` / :class:`QuestionCommand`:

1. Роутер сматчил триггер («поставь напоминание», «добавь напоминание» …).
2. Играется ack-WAV ``reminder_before.wav`` («я готова добавить новое
   напоминание, диктуйте») — так у пользователя есть явная точка, после
   которой он произносит тело, как у заметки и вопроса.
3. ``pipeline.dictate()`` ловит тело («напомни через 5 минут проверить
   кашу» или просто «через 5 минут проверить кашу»).
4. Regex-парсер (``core.reminders.parser``) извлекает число, единицу и
   текст. При неудаче — голосовая подсказка, LLM не трогаем (см.
   feedback memory ``feedback_explicit_llm_only``).
5. Scheduler.add() записывает абсолютный fire_at в JSON и ставит Timer.
6. Подтверждение: «поставила напоминание через N минут <текст>».
"""

from __future__ import annotations

import logging

from commands.base import BaseCommand, CommandContext, CommandType
from core.reminders.num_to_words import humanize_duration
from core.reminders.parser import parse_reminder_tail, unit_to_seconds
from utils.errors import STTError

logger = logging.getLogger(__name__)


class ReminderCommand(BaseCommand):
    name = "reminder"
    command_type = CommandType.CONTENT
    ack_before = "reminder_before.wav"
    # ack_after намеренно None: команда сама синтезирует фразу
    # «поставила напоминание через …», включающую количество и текст.
    ack_after = None
    # Все синонимы ≥2 слов (feedback memory `feedback_two_word_commands`).
    # Триггеры — только «имя команды», без фрагментов тела («напомни через»
    # теперь живёт в диктовке, а не в синониме), так что путь всегда один:
    # трigger → ack → диктовка → парсинг → подтверждение.
    synonyms = (
        "поставь напоминание",
        "добавь напоминание",
        "создай напоминание",
        "новое напоминание",
        "поставь таймер",
    )

    def execute(self, ctx: CommandContext) -> bool:
        pipeline = ctx.pipeline
        scheduler = getattr(pipeline, "reminder_scheduler", None)
        if scheduler is None:
            logger.warning("ReminderCommand: scheduler не инициализирован")
            return False

        # Диктуем тело. pipeline.dictate() сам проигрывает ack_before
        # (если файл есть) или fallback-бип, и ждёт речь.
        try:
            body = pipeline.dictate(ack_filename=self.ack_before)
        except STTError:
            logger.exception("ReminderCommand: STT упал во время диктовки")
            print("⚠ Тело напоминания не распознано.")
            return True
        body = (body or "").strip()
        if not body:
            logger.info("ReminderCommand: пустая диктовка — напоминание не создано")
            print("⚠ Нечего планировать (тишина).")
            return True

        print(f"   тело: «{body}»")
        parsed = parse_reminder_tail(body)
        if parsed is None:
            logger.info("ReminderCommand: не распарсили тело: %r", body)
            print("⚠ Не поняла напоминание.")
            pipeline._speak_safely(
                "Не поняла напоминание. Скажите, например: "
                "напомни через двадцать минут проверить кашу."
            )
            return True

        count, unit, text = parsed
        delay_seconds = unit_to_seconds(count, unit)
        try:
            human_delay = humanize_duration(count, unit)
        except Exception:
            logger.exception("humanize_duration failed for (%d, %s)", count, unit)
            human_delay = f"{count} {unit}"

        scheduler.add(delay_seconds, text)
        confirmation = f"поставила напоминание через {human_delay} {text}"
        print(f"⏰ {confirmation}")
        pipeline._speak_safely(confirmation)
        return True
