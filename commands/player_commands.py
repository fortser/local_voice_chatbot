"""Команды управления плеером и громкостью (M4).

Все маршрутизируются в `system.media_keys` (Win32 multimedia keys) или
`system.audio_session_mute` (pycaw per-session mute, исключая нас).

Pause/Resume — обе шлют `VK_MEDIA_PLAY_PAUSE` (физически это toggle).
В контексте голоса это естественно: пользователь произносит правильную
команду для текущего состояния плеера, и нажатие переводит его в
противоположное.

Mute/Unmute — реальный селектив: заглушаем чужие аудио-сессии,
оставляя голос Шурочки. На «включи звук» снимаем mute с тех же
сессий, что мы сами заглушили.

Volume Up/Down — мастер-громкость Windows (с привычным OSD).
"""

from __future__ import annotations

import logging

from commands.base import BaseCommand, CommandContext, CommandType
from system import media_keys

logger = logging.getLogger(__name__)


class PauseCommand(BaseCommand):
    name = "pause"
    command_type = CommandType.INSTANT
    synonyms = (
        "поставь паузу",
        "поставь на паузу",
        "поставить на паузу",
        "сделай паузу",
    )
    ack_after = "pause_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        media_keys.play_pause()
        return True


class ResumeCommand(BaseCommand):
    name = "resume"
    command_type = CommandType.INSTANT
    synonyms = (
        "сними паузу",
        "продолжи воспроизведение",
        "продолжим воспроизведение",
        "продолжите воспроизведение",
        "продолжай играть",
        "включи кино",
        "кино дальше",
    )
    ack_after = "resume_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        # Та же физическая клавиша, что и Pause — Windows toggle.
        media_keys.play_pause()
        return True


class VolumeUpCommand(BaseCommand):
    name = "volume_up"
    command_type = CommandType.INSTANT
    synonyms = (
        "сделай громче",
        "сделай погромче",
        "прибавь громкость",
        "увеличь громкость",
        "добавь громкость",
        "добавь громкости",
        "добавить громкость",
    )
    ack_after = "volume_up_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        media_keys.volume_up()
        return True


class VolumeDownCommand(BaseCommand):
    name = "volume_down"
    command_type = CommandType.INSTANT
    synonyms = (
        "сделай тише",
        "сделай потише",
        "убавь громкость",
        "уменьши громкость",
    )
    ack_after = "volume_down_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        media_keys.volume_down()
        return True


class MuteCommand(BaseCommand):
    name = "mute"
    command_type = CommandType.INSTANT
    synonyms = ("выключи звук", "убери звук", "заглуши плеер", "без звука")
    ack_after = "mute_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        controller = getattr(ctx.pipeline, "audio_mute", None)
        if controller is None:
            logger.warning("MuteCommand: audio_mute не доступен")
            return False
        n = controller.mute_others()
        print(f"🔇 Заглушено сессий: {n}")
        # Подсказка пользователю — где искать состояние, как снять руками.
        # Mute живёт на уровне аудио-сессии Windows, в самом плеере иконка
        # громкости остаётся в обычном состоянии — это сбивает с толку.
        if n > 0:
            print(
                "   ↳ голосом: «верни звук» / «включи звук»;"
                " вручную: Win+A → per-app микшер, или Win+R → sndvol;"
                " при выходе из Шурочки звук вернётся сам."
            )
        return True


class UnmuteCommand(BaseCommand):
    name = "unmute"
    command_type = CommandType.INSTANT
    synonyms = ("включи звук", "верни звук", "со звуком")
    ack_after = "unmute_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        controller = getattr(ctx.pipeline, "audio_mute", None)
        if controller is None:
            logger.warning("UnmuteCommand: audio_mute не доступен")
            return False
        n = controller.unmute_others()
        print(f"🔊 Снят mute с {n} сессий")
        return True
