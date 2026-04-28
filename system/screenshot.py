"""Захват экрана через ``mss`` (M3).

Один публичный вызов ``take_screenshot()`` — возвращает PNG-байты.
Сохранение в файл — задача :class:`SessionManager.save_screenshot`,
чтобы пути и нумерация лежали в одном месте.

Многомониторная конфигурация:

* ``monitor=None`` (по умолчанию) — захватывается **основной** монитор
  (``mss().monitors[1]``; индекс 0 в API mss — это «все мониторы вместе»).
* ``monitor=N`` — конкретный экран по индексу из ``mss().monitors``
  (1-based для физических). Список можно посмотреть так::

      with mss.mss() as s:
          for i, m in enumerate(s.monitors):
              print(i, m)

Mouse-nudge перед захватом:
    Видеоплееры (YouTube, VLC, MPC, MPV) автоматически прячут панель
    управления и временную шкалу через несколько секунд бездействия.
    Чтобы шкала попала в скриншот, перед ``sct.grab()`` курсор быстро
    проходит через несколько точек поверх foreground-окна. Точки взяты
    в долях от размеров окна (50/30, 50/50, 35/40) — у YouTube в
    дефолтной раскладке плеер в верхне-центральной части, у локальных
    плееров видео заполняет окно почти целиком. После захвата курсор
    возвращается на исходную позицию. Поведение управляется секцией
    ``[mouse_nudge]`` в ``settings.toml``.

Потокобезопасность: каждый вызов открывает свой контекст ``mss.mss()`` —
это дёшево и безопасно для конкурентных вызовов из разных потоков.
"""

from __future__ import annotations

import logging
import sys
import time

import mss
import mss.tools

from config import settings

logger = logging.getLogger(__name__)


# Доли (x, y) от width/height foreground-окна. Подобраны так, чтобы
# хотя бы одна точка попала на область видеоплеера в типовых раскладках.
_SWEEP_POINTS: tuple[tuple[float, float], ...] = (
    (0.50, 0.30),
    (0.50, 0.50),
    (0.35, 0.40),
)


def _nudge_mouse_over_foreground() -> None:
    """Win32-only: проводит курсор через ``_SWEEP_POINTS`` поверх foreground-окна
    и возвращает на исходную позицию. Любая ошибка ctypes/Win32 — тихий no-op,
    скриншот всё равно должен сделаться."""
    if sys.platform != "win32":
        return
    cfg = settings.mouse_nudge
    if not cfg.enabled:
        return

    try:
        import ctypes

        class _POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class _RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return
        rect = _RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w < cfg.min_window_size or h < cfg.min_window_size:
            return

        saved = _POINT()
        have_saved = bool(user32.GetCursorPos(ctypes.byref(saved)))

        step = max(0.0, cfg.step_ms / 1000.0)
        settle = max(0.0, cfg.settle_ms / 1000.0)
        try:
            for fx, fy in _SWEEP_POINTS:
                x = rect.left + int(w * fx)
                y = rect.top + int(h * fy)
                user32.SetCursorPos(x, y)
                if step:
                    time.sleep(step)
            if settle:
                time.sleep(settle)
        finally:
            # Курсор возвращаем ПОСЛЕ возврата управления — захват уже
            # будет сделан вызывающей функцией. Здесь рано возвращать
            # нельзя: контролы плеера погаснут до grab(). Поэтому
            # восстановление лежит на ``take_screenshot``.
            pass

        # Сохранённую позицию вернёт вызывающая функция через _restore_cursor.
        _nudge_mouse_over_foreground._saved = (saved.x, saved.y) if have_saved else None  # type: ignore[attr-defined]
    except Exception:
        logger.debug("mouse-nudge skipped due to exception", exc_info=True)
        _nudge_mouse_over_foreground._saved = None  # type: ignore[attr-defined]


def _restore_cursor() -> None:
    saved = getattr(_nudge_mouse_over_foreground, "_saved", None)
    if saved is None or sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.user32.SetCursorPos(saved[0], saved[1])
    except Exception:
        logger.debug("cursor restore skipped due to exception", exc_info=True)
    finally:
        _nudge_mouse_over_foreground._saved = None  # type: ignore[attr-defined]


def take_screenshot(monitor: int | None = None) -> bytes:
    """Снять скриншот, вернуть PNG-байты.

    На моноэкране всегда захватывается единственный экран. На multi-monitor
    по умолчанию — основной (``monitors[1]``). Поднимать другой —
    передать индекс из ``mss().monitors``.
    """
    _nudge_mouse_over_foreground()
    try:
        with mss.mss() as sct:
            if monitor is None:
                # ``monitors[0]`` — bbox объединения всех экранов (часто гигантский
                # PNG); пользователь почти всегда хочет именно основной экран.
                target = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            else:
                if monitor < 0 or monitor >= len(sct.monitors):
                    raise ValueError(
                        f"monitor={monitor} вне диапазона 0..{len(sct.monitors) - 1}"
                    )
                target = sct.monitors[monitor]
            raw = sct.grab(target)
            png_bytes = mss.tools.to_png(raw.rgb, raw.size)
            logger.info(
                "Screenshot taken: %dx%d, %d KB",
                raw.size[0], raw.size[1], len(png_bytes) // 1024,
            )
            return png_bytes
    finally:
        _restore_cursor()
