"""ScreenshotCommand — «сделай скриншот» (M3).

INSTANT-команда: захватывает PNG основного экрана и кладёт в папку
текущей сессии. Ack-фраза «сделала скриншот» проигрывается внешним
обработчиком в :class:`VoicePipeline` после возврата из ``execute()``.
"""

from __future__ import annotations

import logging

from commands.base import BaseCommand, CommandContext, CommandType
from system.screenshot import take_screenshot

logger = logging.getLogger(__name__)


class ScreenshotCommand(BaseCommand):
    name = "screenshot"
    command_type = CommandType.INSTANT
    synonyms = (
        "сделай скриншот",
        "сними скриншот",
        "сохрани скриншот",
        "сохранить скриншот",
        "сними экран",
    )
    ack_after = "screenshot_after.wav"

    def execute(self, ctx: CommandContext) -> bool:
        session = ctx.session_manager
        if session is None:
            logger.warning("ScreenshotCommand: SessionManager не передан")
            return False
        png = take_screenshot()
        path = session.save_screenshot(png)
        print(f"📸 Скриншот сохранён: {path}")
        return True
