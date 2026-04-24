"""Полупрозрачное окно-статус в углу экрана (M8).

Отдельное `tk.Toplevel` поверх всех окон: показывает текущее состояние
ассистента (Пассивен / Слышу / Говорите / Обрабатываю / Отвечаю).
Полный UI (`tkinter_ui.VoiceAIApp`) живёт рядом в обычном окне — overlay
его не заменяет, а дополняет для ситуаций «окно свернул, хочу видеть
состояние».

Click-through на Windows: overlay не перехватывает мышь — щелчок
«проваливается» сквозь него в окно под ним. Делается через расширенный
стиль окна `WS_EX_TRANSPARENT | WS_EX_LAYERED` (ctypes). На других
платформах — no-op (Overlay будет обычным всегда-поверх окном).

Потоки: все методы публичного API безопасно вызывать из любого потока —
они перекладывают работу на UI-поток через `root.after(0, ...)`.
"""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from typing import Callable

from config import (
    OVERLAY_ALPHA,
    OVERLAY_ENABLED,
    OVERLAY_MARGIN,
    OVERLAY_POSITION,
    WAKE_WORD,
)

logger = logging.getLogger(__name__)


# ---- state mapping ---------------------------------------------------------

# Короткие лейблы специально для overlay: одна строка, одна emoji.
# Ключи — имена состояний, которые постит pipeline (см. STATE_LABELS в
# tkinter_ui.py). Если приходит неизвестное имя — overlay показывает его
# как есть, без emoji.
_OVERLAY_LABELS: dict[str, tuple[str, str]] = {
    "starting":         ("⚙",  "Инициализация"),
    "idle":             ("🟢", "Готов"),
    "calibrating":      ("🔵", "Калибровка"),
    "listening":        ("🎙", "Говорите"),
    "processing":       ("🧠", "Обрабатываю"),
    "speaking":         ("🔊", "Отвечаю"),
    "warming":          ("⏳", "Прогрев"),
    "error":            ("❌", "Ошибка"),
    "stopping":         ("⚫", "Завершение"),
    "stopped":          ("⚫", "Остановлен"),
    "standby_idle":     ("🛌", "Дежурный"),
    "wake_heard":       ("👂", "Слышу"),
    "wake_active":      ("🎙", "Говорите"),
    "wake_processing":  ("🧠", "Обрабатываю"),
}

_POSITION_CHOICES = {"top_right", "top_left", "bottom_right", "bottom_left"}


class Overlay:
    """Небольшое always-on-top окно-статус.

    Создаётся поверх существующего Tk root; `destroy()` убирает только
    overlay, root остаётся. Если `OVERLAY_ENABLED=False` — конструктор
    ничего не делает (все публичные методы превращаются в no-op).
    """

    WIDTH = 230
    HEIGHT = 48

    def __init__(
        self,
        root: tk.Tk,
        *,
        position: str = OVERLAY_POSITION,
        alpha: float = OVERLAY_ALPHA,
        margin: int = OVERLAY_MARGIN,
    ) -> None:
        self._root = root
        self._enabled = bool(OVERLAY_ENABLED)
        self._position = position if position in _POSITION_CHOICES else "top_right"
        self._alpha = float(alpha)
        self._margin = int(margin)
        self._win: tk.Toplevel | None = None
        self._label: tk.Label | None = None
        self._destroyed = False

        if not self._enabled:
            return
        self._build()

    # ---- construction -----------------------------------------------------

    def _build(self) -> None:
        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)
        try:
            win.wm_attributes("-alpha", self._alpha)
        except tk.TclError:
            logger.debug("Overlay: platform doesn't support -alpha")

        # На Windows добавляем toolwindow — чтобы overlay не мелькал в Alt-Tab.
        if sys.platform == "win32":
            try:
                win.wm_attributes("-toolwindow", True)
            except tk.TclError:
                pass

        frame = tk.Frame(win, bg="#111111", bd=0, highlightthickness=0)
        frame.pack(fill="both", expand=True)
        label = tk.Label(
            frame,
            text="⚙  Инициализация",
            bg="#111111",
            fg="#e0e0e0",
            font=("Segoe UI Emoji", 12, "bold"),
            padx=10,
            pady=6,
            anchor="w",
            justify="left",
        )
        label.pack(fill="both", expand=True)

        self._win = win
        self._label = label

        self._place()
        # После map-а применяем click-through (на неразмаппленном окне hwnd
        # ещё не готов, поэтому откладываем на первый tick).
        win.after(50, self._apply_click_through)

    def _place(self) -> None:
        assert self._win is not None
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        w, h = self.WIDTH, self.HEIGHT
        m = self._margin
        if self._position == "top_right":
            x, y = sw - w - m, m
        elif self._position == "top_left":
            x, y = m, m
        elif self._position == "bottom_right":
            x, y = sw - w - m, sh - h - m - 40  # -40: над таскбаром
        else:  # bottom_left
            x, y = m, sh - h - m - 40
        self._win.geometry(f"{w}x{h}+{x}+{y}")

    def _apply_click_through(self) -> None:
        """Делаем overlay прозрачным для мыши (Windows-only)."""
        if sys.platform != "win32" or self._win is None:
            return
        try:
            import ctypes

            # Для Toplevel с overrideredirect реальный HWND — это родитель
            # виджета, возвращаемого winfo_id (сам виджет — child window Tk).
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000

            hwnd = ctypes.windll.user32.GetParent(self._win.winfo_id())
            if not hwnd:
                hwnd = self._win.winfo_id()
            ex = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_ex = (
                ex
                | WS_EX_LAYERED
                | WS_EX_TRANSPARENT
                | WS_EX_TOOLWINDOW
                | WS_EX_NOACTIVATE
            )
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex)
        except Exception:
            logger.exception("Overlay: не удалось применить click-through")

    # ---- public API -------------------------------------------------------

    def set_state(self, name: str, detail: str | None = None) -> None:
        """Обновить отображаемое состояние. Безопасно из любого потока."""
        if not self._enabled or self._destroyed:
            return
        # Готовим строку сразу — не трогаем Tk из чужого потока.
        icon, label = _OVERLAY_LABELS.get(name, ("•", name))
        if name == "standby_idle":
            label = f"Дежурный: «{WAKE_WORD}»"
        text = f"{icon}  {label}"
        if detail:
            text = f"{text}  —  {detail[:30]}"
        self._schedule(lambda: self._apply_text(text))

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._schedule(self._do_destroy)

    # ---- internals --------------------------------------------------------

    def _apply_text(self, text: str) -> None:
        if self._label is None:
            return
        try:
            self._label.configure(text=text)
        except tk.TclError:
            # Окно уже уничтожено (например, root закрылся).
            pass

    def _do_destroy(self) -> None:
        win = self._win
        self._win = None
        self._label = None
        if win is not None:
            try:
                win.destroy()
            except tk.TclError:
                pass

    def _schedule(self, fn: Callable[[], None]) -> None:
        try:
            self._root.after(0, fn)
        except (RuntimeError, tk.TclError):
            # root уже уничтожен — ничего не делаем.
            pass


__all__ = ["Overlay"]
