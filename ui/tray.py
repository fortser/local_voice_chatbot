"""Иконка в системном трее (M8).

`pystray` крутит собственный event loop и блокирует поток — поэтому
всё живёт в daemon-потоке и дергает колбэки из main UI. Иконка
генерируется PIL'ом, внешние файлы не нужны.

Меню:
  • Включить ассистента   — wake_listener.enable() (закрывает Q3 плана:
                             после голосового StopCommand это единственный
                             способ вернуть дежурный режим, кроме hotkey)
  • Открыть папку сессии  — открывает в Проводнике session_manager.base_dir
                             (или текущую папку сессии, если уже создана)
  • Перезагрузить конфиг  — заглушка (TODO M8.x / отдельный этап)
  • Выход                 — корректный shutdown приложения через колбэк
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


def _make_icon_image():
    """64×64 PNG — зелёный кружок с буквой «Ш». Без внешних файлов."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, 62, 62), fill=(59, 177, 67, 255), outline=(20, 20, 20, 255))
    # Буква Ш — универсальный дефолтный шрифт PIL.
    try:
        font = ImageFont.truetype("arial.ttf", 34)
    except Exception:
        font = ImageFont.load_default()
    try:
        bbox = d.textbbox((0, 0), "Ш", font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((64 - tw) / 2 - bbox[0], (64 - th) / 2 - bbox[1] - 2),
               "Ш", fill=(255, 255, 255, 255), font=font)
    except Exception:
        d.text((20, 16), "Ш", fill=(255, 255, 255, 255), font=font)
    return img


class SystemTray:
    """Фасад над `pystray.Icon`, крутится в daemon thread.

    Колбэки вызываются **из потока pystray** — если они трогают Tk или
    pipeline, обёртку с переносом на нужный поток делает вызывающий
    (например, `tkinter_ui` шлёт события в свою очередь `_ui_queue`).

    Колбэк `on_quit` обязателен — остальные опциональны; если не заданы,
    пункт меню всё равно показывается, но ничего не делает.
    """

    def __init__(
        self,
        *,
        on_enable_assistant: Callable[[], None] | None = None,
        on_open_session: Callable[[], None] | None = None,
        on_reload_config: Callable[[], None] | None = None,
        on_quit: Callable[[], None],
        title: str = "Shura v2",
    ) -> None:
        self._on_enable = on_enable_assistant
        self._on_open = on_open_session
        self._on_reload = on_reload_config
        self._on_quit = on_quit
        self._title = title
        self._icon = None
        self._thread: threading.Thread | None = None
        self._stopped = False

    def start(self) -> None:
        import pystray

        image = _make_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem("Включить ассистента", self._handle_enable),
            pystray.MenuItem("Открыть папку сессии", self._handle_open),
            pystray.MenuItem("Перезагрузить конфиг", self._handle_reload),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", self._handle_quit),
        )
        self._icon = pystray.Icon("shura_v2", image, self._title, menu)
        self._thread = threading.Thread(
            target=self._run, name="SystemTray", daemon=True
        )
        self._thread.start()
        logger.info("SystemTray started")

    def _run(self) -> None:
        try:
            self._icon.run()
        except Exception:
            logger.exception("SystemTray thread crashed")

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        icon = self._icon
        if icon is not None:
            try:
                icon.visible = False
                icon.stop()
            except Exception:
                logger.exception("SystemTray.stop() failed")

    # ---- menu handlers (вызываются из потока pystray) --------------------

    def _handle_enable(self, _icon, _item) -> None:
        if self._on_enable is None:
            return
        try:
            self._on_enable()
        except Exception:
            logger.exception("tray: on_enable failed")

    def _handle_open(self, _icon, _item) -> None:
        if self._on_open is None:
            return
        try:
            self._on_open()
        except Exception:
            logger.exception("tray: on_open failed")

    def _handle_reload(self, _icon, _item) -> None:
        if self._on_reload is None:
            logger.info("tray: перезагрузка конфига не реализована (заглушка)")
            return
        try:
            self._on_reload()
        except Exception:
            logger.exception("tray: on_reload failed")

    def _handle_quit(self, _icon, _item) -> None:
        try:
            self._on_quit()
        except Exception:
            logger.exception("tray: on_quit failed")


def open_folder(path: Path | str) -> None:
    """Открыть папку в системном Проводнике. Best-effort."""
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    try:
        os.startfile(str(p))  # type: ignore[attr-defined]  # Windows-only
    except Exception:
        logger.exception("open_folder(%s) failed", p)


__all__ = ["SystemTray", "open_folder"]
