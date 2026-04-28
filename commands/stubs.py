"""Реальные команды, не поместившиеся в тематические модули (M6).

Cancel — клавишный (Esc в UI), не голосовой: слишком легко поймать ложное
срабатывание «отмени» на шум Whisper'а и сорвать диктовку/ответ.
"""

from __future__ import annotations

import logging

from commands.base import BaseCommand, CommandContext, CommandType
from system import media_keys

logger = logging.getLogger(__name__)


# ---- GLOBAL ----------------------------------------------------------------

class StopCommand(BaseCommand):
    """«Закончи работу» — выключает дежурный режим (wake-word listener).

    Не выход из процесса: окно живёт, заметки и история сохранены, можно
    снова включить дежурный режим кнопкой «🛌 Дежурный» или закрыть окно.
    Причина — случайное срабатывание Whisper'а на шум не должно убивать
    процесс и терять контекст.
    """

    name = "stop"
    command_type = CommandType.GLOBAL
    synonyms = ("остановись пожалуйста", "закончи работу", "отключись пока")
    ack_after = "stop_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        listener = getattr(ctx.pipeline, "wake_listener", None)
        if listener is None:
            logger.warning("StopCommand: wake_listener не подключён к pipeline")
            return True
        if listener.is_enabled:
            logger.info("StopCommand: выключаю дежурный режим")
            listener.disable()
        else:
            logger.info("StopCommand: дежурный режим уже выключен")
        return True


# ---- INSTANT ---------------------------------------------------------------

class SeekForwardCommand(BaseCommand):
    """«Перемотай вперёд» — шлёт VK_MEDIA_NEXT_TRACK.

    В YouTube/Spotify это «следующий трек/видео». Универсальной системной
    клавиши для перемотки внутри видео в Windows нет — если понадобится,
    делается через focus+arrow_key в отдельном этапе.
    """

    name = "seek_forward"
    command_type = CommandType.INSTANT
    synonyms = ("перемотай вперёд", "промотай вперёд", "следующий трек")
    ack_after = "seek_forward_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        media_keys.next_track()
        return True


class SeekBackwardCommand(BaseCommand):
    name = "seek_backward"
    command_type = CommandType.INSTANT
    synonyms = ("перемотай назад", "промотай назад", "предыдущий трек")
    ack_after = "seek_backward_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        media_keys.prev_track()
        return True


class SkipForwardCommand(BaseCommand):
    """«Чуть вперёд» — стрелка → активное окно. На YouTube это +5 секунд.

    В отличие от seek_forward (VK_MEDIA_NEXT_TRACK, маршрутизируется глобально),
    стрелка уходит туда, где сейчас фокус. Целевой сценарий — полноэкранный
    YouTube; в любом другом окне нажатие просто перенесёт курсор/выделение.
    """

    name = "skip_forward"
    command_type = CommandType.INSTANT
    synonyms = ("чуть вперёд", "немного вперёд", "пять секунд вперёд")
    ack_after = "seek_forward_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        media_keys.arrow_right()
        return True


class SkipBackwardCommand(BaseCommand):
    name = "skip_backward"
    command_type = CommandType.INSTANT
    synonyms = ("чуть назад", "немного назад", "пять секунд назад")
    ack_after = "seek_backward_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        media_keys.arrow_left()
        return True
