"""Subscribe once to the author of the visible YouTube video."""
from __future__ import annotations

import logging
import threading
import time

from commands.base import BaseCommand, CommandContext, CommandType
from config import (
    BASE_DIR,
    WAKE_HINT_FADE_IN_MS,
    WAKE_HINT_HOLD_MS,
    WAKE_HINT_FADE_OUT_MS,
)
from system.youtube_subscription import ScreenControlError, YouTubeScreen

logger = logging.getLogger(__name__)
_SCREEN_LOCK = threading.Lock()
_OVERLAY_SECONDS = (
    WAKE_HINT_FADE_IN_MS + WAKE_HINT_HOLD_MS + WAKE_HINT_FADE_OUT_MS
) / 1000
_RETRIES = max(4, int(_OVERLAY_SECONDS * 1.5 / 0.5) + 1)
_ASSETS = BASE_DIR / "assets" / "youtube_subscription"


class SubscribeChannelCommand(BaseCommand):
    name = "subscribe_channel"
    command_type = CommandType.INSTANT
    synonyms = ("подпишись на канал",)
    ack_after = None

    def execute(self, ctx: CommandContext) -> bool:
        outcome = "fail"
        screen = None
        exited = False
        aborted = False
        if not _SCREEN_LOCK.acquire(blocking=False):
            self._reply(ctx, outcome)
            return True
        try:
            screen = YouTubeScreen(_ASSETS)
            screen.move_over_player()
            control = self._wait(screen.player_control)
            if control is None:
                raise ScreenControlError("Player controls not found")
            if control[0] == "exit":
                exited = True  # Restore even if an input call has an unknown outcome.
                screen.exit_fullscreen()
                time.sleep(0.4)
                screen.refresh_geometry()
                screen.move_over_player()
                control = self._wait(screen.player_control)
                if control is None or control[0] != "enter":
                    raise ScreenControlError("Fullscreen exit was not confirmed")
            button = self._wait(lambda: screen.subscription(control[1]))
            if button is None:
                outcome = "not_found"
            elif button[0] == "subscribed":
                outcome = "already"
            else:
                # Re-observe immediately before clicking; never retry a click.
                current = screen.subscription(control[1])
                if current != button:
                    raise ScreenControlError("Subscription button moved or changed")
                outcome = "unconfirmed"
                screen.click(button[1])
                target = button[1]

                def confirmed():
                    result = screen.subscription(control[1])
                    if result is None or result[0] != "subscribed":
                        return None
                    box = result[1]
                    # The new state must occupy the original author row.
                    if (abs(box.center[1] - target.center[1]) <= max(box.height, target.height) // 2
                            and target.left - 16 <= box.left <= target.left + target.width):
                        return result
                    return None
                if self._wait(confirmed):
                    outcome = "after"
        except Exception as exc:
            aborted = type(exc).__name__ == "FailSafeException"
            logger.warning("SubscribeChannelCommand: %s", exc, exc_info=not isinstance(exc, ScreenControlError))
        finally:
            if screen is not None and not aborted:
                restoration_aborted = False
                try:
                    screen.check_target()
                    if exited:
                        screen.move_over_player()
                        control = self._wait(screen.player_control)
                        if control is not None and control[0] == "enter":
                            screen.click(control[1])
                            time.sleep(0.4)
                            screen.refresh_geometry()
                            screen.move_over_player()
                            restored = self._wait(screen.player_control)
                            if restored is None or restored[0] != "exit":
                                logger.warning("SubscribeChannelCommand: fullscreen restore not confirmed")
                        elif control is None:
                            logger.warning("SubscribeChannelCommand: fullscreen restore control missing")
                except Exception as exc:
                    restoration_aborted = type(exc).__name__ == "FailSafeException"
                    logger.warning("SubscribeChannelCommand: restoration skipped or failed", exc_info=True)
                finally:
                    if not restoration_aborted:
                        try:
                            screen.check_target()
                            screen.restore_cursor()
                        except Exception:
                            logger.warning("SubscribeChannelCommand: cursor restore skipped or failed", exc_info=True)
            _SCREEN_LOCK.release()
        self._reply(ctx, outcome)
        return True  # Failures are handled here, never sent to the LLM.

    @staticmethod
    def _wait(observe):
        for attempt in range(_RETRIES):
            result = observe()
            if result is not None:
                return result
            if attempt + 1 < _RETRIES:
                time.sleep(0.5)
        return None

    @staticmethod
    def _reply(ctx: CommandContext, outcome: str) -> None:
        phrases = {
            "after": "Подписалась на канал",
            "already": "Вы уже подписаны на этот канал",
            "not_found": "Не нашла кнопку подписки. Откройте её под видео",
            "unconfirmed": "Не удалось подтвердить подписку",
            "fail": "Не получилось подписаться на канал",
        }
        print(phrases[outcome])
        play_ack = getattr(ctx.pipeline, "_play_ack", None)
        if play_ack is not None:
            play_ack(f"subscribe_channel_{outcome}.wav")
