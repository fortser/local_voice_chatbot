"""Глобальная hotkey для возврата wake-word режима (M8).

Закрывает Q3 миграции: `StopCommand` голосом выключает
`WakeWordListener`, после чего микрофон не слушается — голосом режим
не вернуть. Hotkey (по умолчанию `Ctrl+Alt+S`, см. `config.WAKE_HOTKEY`)
включает listener обратно. Альтернатива — трей-меню «Включить ассистента».

Используем `pynput`: на Windows не требует админа (в отличие от
`keyboard`), работает как user-level hook.

Колбэк вызывается из потока pynput'а — безопасно трогать только
thread-safe объекты (`threading.Event`, методы `WakeWordListener.enable`
которые сами дергают Event).
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)


class HotkeyListener:
    """Один hotkey → один колбэк. Ничего больше не слушаем."""

    def __init__(self, hotkey: str, callback: Callable[[], None]) -> None:
        self._hotkey = hotkey
        self._callback = callback
        self._listener = None
        self._thread: threading.Thread | None = None
        self._stopped = False

    def start(self) -> None:
        try:
            from pynput import keyboard
        except ImportError:
            logger.warning("pynput не установлен — hotkey %s отключена", self._hotkey)
            return

        def _on_fire() -> None:
            try:
                self._callback()
            except Exception:
                logger.exception("hotkey callback failed")

        try:
            self._listener = keyboard.GlobalHotKeys({self._hotkey: _on_fire})
        except Exception:
            logger.exception(
                "не удалось зарегистрировать hotkey %r (неверный формат?)",
                self._hotkey,
            )
            return

        # GlobalHotKeys — это threading.Thread; .start() не блокирует.
        self._listener.start()
        logger.info("HotkeyListener: hotkey %s активна", self._hotkey)

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        listener = self._listener
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                logger.exception("HotkeyListener.stop() failed")


__all__ = ["HotkeyListener"]
