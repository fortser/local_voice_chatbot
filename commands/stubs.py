"""M1 stub commands.

Каждая команда логирует диспетч и возвращает True. Реальные реализации
вырастают по этапам: M3 (Screenshot), M4 (Pause/Resume/Seek), M5 (volume),
M6 (Stop/Cancel). Note и Question — уже настоящие, см. одноимённые модули.

Принцип синонимов: **минимум 2 слова в каждой фразе**. Однословные триггеры
(«пауза», «громче», «стоп») цепляются на любой шум Whisper'а; двухсловные
формы радикально снижают ложные срабатывания.
"""

from __future__ import annotations

import logging

from commands.base import BaseCommand, CommandContext, CommandType

logger = logging.getLogger(__name__)


def _stub_log(cmd: BaseCommand, ctx: CommandContext) -> None:
    logger.info(
        "[STUB] %s executed (type=%s, matched=%r, full=%r)",
        cmd.name, cmd.command_type.value, ctx.matched_synonym, ctx.full_text,
    )


# ---- GLOBAL ----------------------------------------------------------------

class StopCommand(BaseCommand):
    name = "stop"
    command_type = CommandType.GLOBAL
    synonyms = ("остановись пожалуйста", "закончи работу", "отключись пока")
    ack_after = "stop_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        _stub_log(self, ctx)
        return True


class CancelCommand(BaseCommand):
    name = "cancel"
    command_type = CommandType.GLOBAL
    synonyms = ("отмени команду", "отмени действие", "отмени запись")
    ack_after = "cancel_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        _stub_log(self, ctx)
        return True


# ---- INSTANT — плеер ------------------------------------------------------

class PauseCommand(BaseCommand):
    name = "pause"
    command_type = CommandType.INSTANT
    synonyms = ("поставь паузу", "поставь на паузу", "сделай паузу")
    ack_after = "pause_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        _stub_log(self, ctx)
        return True


class ResumeCommand(BaseCommand):
    name = "resume"
    command_type = CommandType.INSTANT
    synonyms = ("сними паузу", "продолжи воспроизведение", "продолжай играть")
    ack_after = "resume_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        _stub_log(self, ctx)
        return True


class SeekForwardCommand(BaseCommand):
    name = "seek_forward"
    command_type = CommandType.INSTANT
    synonyms = ("перемотай вперёд", "промотай вперёд", "перемотка вперёд")
    ack_after = "seek_forward_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        _stub_log(self, ctx)
        return True


class SeekBackwardCommand(BaseCommand):
    name = "seek_backward"
    command_type = CommandType.INSTANT
    synonyms = ("перемотай назад", "промотай назад", "перемотка назад")
    ack_after = "seek_backward_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        _stub_log(self, ctx)
        return True


# ---- INSTANT — громкость --------------------------------------------------

class VolumeUpCommand(BaseCommand):
    name = "volume_up"
    command_type = CommandType.INSTANT
    synonyms = ("сделай громче", "прибавь громкость", "увеличь громкость")
    ack_after = "volume_up_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        _stub_log(self, ctx)
        return True


class VolumeDownCommand(BaseCommand):
    name = "volume_down"
    command_type = CommandType.INSTANT
    synonyms = ("сделай тише", "убавь громкость", "уменьши громкость")
    ack_after = "volume_down_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        _stub_log(self, ctx)
        return True


class MuteCommand(BaseCommand):
    name = "mute"
    command_type = CommandType.INSTANT
    synonyms = ("выключи звук", "заглуши плеер", "без звука")
    ack_after = "mute_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        _stub_log(self, ctx)
        return True


class UnmuteCommand(BaseCommand):
    name = "unmute"
    command_type = CommandType.INSTANT
    synonyms = ("включи звук", "верни звук", "со звуком")
    ack_after = "unmute_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        _stub_log(self, ctx)
        return True


# ScreenshotCommand → commands/screenshot_command.py (M3)


# ---- CONTENT --------------------------------------------------------------
# NoteCommand → commands/note_command.py
# QuestionCommand → commands/question_command.py
