"""Удержание дисплея активным во время диалога с Шурочкой (anti-screensaver).

Решает проблему «заставка включилась посреди разговора, потом голосовая
команда якобы выполнилась, но плеер не возобновил воспроизведение». Снять
уже активный сторонний 3D-screensaver (3Planesoft и т.п.) синтетическим
вводом невозможно: Windows запускает screensaver на отдельном desktop'е,
а `SendInput` ограничен desktop'ом процесса. Поэтому идём по предотвращению,
а не по dismissal'у.

Используем штатный Win32-механизм:

* `SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED)` — пока флаг
  стоит, Windows не запускает screensaver и не гасит экран. Ровно то, что
  делают VLC, MPC-HC, Chromium при fullscreen-видео.
* `SetThreadExecutionState(ES_CONTINUOUS)` — снять флаг.
* Дополнительно при acquire дёргаем mouse-event (нулевое смещение,
  NOCOALESCE), чтобы обновить `LASTINPUTINFO` — страховка для случая,
  когда idle-таймер уже почти досчитал до запуска screensaver'а в момент
  установки флага.

Жизненный цикл: `acquire()` ставит флаг и (пере)запускает таймер релиза
на ``hold_after_turn_s`` секунд. Каждый новый `acquire()` (новый wake-word
или конец очередного turn'а) сбрасывает таймер заново. По истечении —
`release()`. На крах процесса флаг снимается ОС автоматически, persistent
state в системе не остаётся.
"""

from __future__ import annotations

import ctypes
import logging
import threading

from system.media_keys import _send_mouse_event, MOUSEEVENTF_MOVE, MOUSEEVENTF_MOVE_NOCOALESCE

logger = logging.getLogger(__name__)

# SetThreadExecutionState flags (winbase.h)
ES_CONTINUOUS = 0x80000000
ES_DISPLAY_REQUIRED = 0x00000002

_lock = threading.Lock()
_acquired = False
_release_timer: threading.Timer | None = None


def _set_state(flags: int) -> bool:
    rc = ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))
    if rc == 0:
        err = ctypes.windll.kernel32.GetLastError()
        logger.warning("SetThreadExecutionState(0x%08x) failed (err=%d)", flags, err)
        return False
    return True


def _nudge_last_input() -> None:
    """Обновить LASTINPUTINFO синтетическим mouse-event'ом без визуального движения."""
    _send_mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_MOVE_NOCOALESCE, 0, 0)


def acquire(hold_seconds: float, *, reason: str = "") -> None:
    """Поставить ES_DISPLAY_REQUIRED и (пере)запустить таймер релиза.

    Идемпотентно: повторный вызов в окне удержания просто продлевает таймер.
    """
    global _acquired, _release_timer
    with _lock:
        if not _acquired:
            if _set_state(ES_CONTINUOUS | ES_DISPLAY_REQUIRED):
                _acquired = True
                logger.info("keep-awake acquired (reason=%s, hold=%.0fs)", reason or "-", hold_seconds)
            _nudge_last_input()
        else:
            logger.debug("keep-awake refresh (reason=%s, hold=%.0fs)", reason or "-", hold_seconds)

        if _release_timer is not None:
            _release_timer.cancel()
        timer = threading.Timer(hold_seconds, _timed_release)
        timer.daemon = True
        timer.start()
        _release_timer = timer


def _timed_release() -> None:
    logger.info("keep-awake hold expired — releasing")
    release()


def release() -> None:
    """Снять флаг сейчас, отменить отложенный релиз. Идемпотентно."""
    global _acquired, _release_timer
    with _lock:
        if _release_timer is not None:
            _release_timer.cancel()
            _release_timer = None
        if _acquired:
            _set_state(ES_CONTINUOUS)
            _acquired = False
            logger.info("keep-awake released")


def is_active() -> bool:
    return _acquired
