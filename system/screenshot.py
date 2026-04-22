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

Потокобезопасность: каждый вызов открывает свой контекст ``mss.mss()`` —
это дёшево и безопасно для конкурентных вызовов из разных потоков.
"""

from __future__ import annotations

import logging

import mss
import mss.tools

logger = logging.getLogger(__name__)


def take_screenshot(monitor: int | None = None) -> bytes:
    """Снять скриншот, вернуть PNG-байты.

    На моноэкране всегда захватывается единственный экран. На multi-monitor
    по умолчанию — основной (``monitors[1]``). Поднимать другой —
    передать индекс из ``mss().monitors``.
    """
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
