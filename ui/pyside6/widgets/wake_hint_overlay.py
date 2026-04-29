"""WakeHintOverlay — полноэкранный полупрозрачный список команд при пробуждении.

При срабатывании wake-word'а появляется поверх всех окон со списком доступных
команд крупным текстом, удерживается ``hold_ms`` и плавно растворяется. Окно
frameless / on-top / прозрачно для мыши и не претендует на фокус — пользователь
продолжает работать с тем, что под оверлеем, ничего не блокируется.

Источник списка — :mod:`commands.hint_provider`. Виджет не знает про команды,
он принимает готовый ``list[str]`` и параметры отображения.

Один экземпляр виджета переиспользуется на каждый wake — пересоздавать
QWidget каждый раз дорого и приводит к мерцанию из-за оконного менеджера
Windows. ``show_lines()`` обновляет текст и запускает анимацию заново;
``hide_now()`` досрочно скрывает (например, при переходе в processing).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    QTimer,
    Qt,
)
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QWidget

logger = logging.getLogger(__name__)


def _pick_screen_geometry(monitor_pref: str) -> QRect:
    """Геометрия монитора по политике ``monitor_pref``: cursor / primary / active_window."""
    screens = QGuiApplication.screens()
    if not screens:
        return QRect(0, 0, 1920, 1080)
    if monitor_pref == "cursor":
        scr = QGuiApplication.screenAt(QCursor.pos())
        if scr is not None:
            return scr.geometry()
    # ``active_window`` свести к primary без зависимости от Win32 — Qt не даёт
    # переносимый foreground-window API. Можно расширить позже через ctypes.
    primary = QGuiApplication.primaryScreen()
    return primary.geometry() if primary else screens[0].geometry()


class WakeHintOverlay(QWidget):
    """Полноэкранный полупрозрачный список команд."""

    def __init__(
        self,
        *,
        hold_ms: int = 1500,
        fade_in_ms: int = 150,
        fade_out_ms: int = 250,
        opacity: float = 0.55,
        font_pt: int = 32,
        monitor: str = "cursor",
        vertical_align: str = "center",
        text_color: str = "#1a1a1a",
        shadow_enabled: bool = True,
        shadow_color: str = "#ffffff",
        shadow_blur: int = 16,
        backdrop_enabled: bool = True,
        backdrop_color: str = "#fdf6e3",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.Tool,
        )
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        # WA_TranslucentBackground: фон окна — без подложки, остаётся только
        # отрисованный лейбл с тенью. Без него Qt заливает окно системным цветом.
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._hold_ms = max(0, int(hold_ms))
        self._fade_in_ms = max(0, int(fade_in_ms))
        self._fade_out_ms = max(0, int(fade_out_ms))
        self._target_opacity = max(0.0, min(1.0, float(opacity)))
        self._monitor_pref = monitor
        self._vertical_align = vertical_align if vertical_align in {
            "center", "top", "bottom"
        } else "center"
        self._text_color = text_color
        self._font_pt = int(font_pt)

        self._label = QLabel(self)
        self._label.setWordWrap(False)
        self._label.setTextFormat(Qt.RichText)
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        font = QFont()
        font.setPointSize(self._font_pt)
        font.setBold(True)
        self._label.setFont(font)
        # Глобальный QSS приложения может выставлять `QWidget { font-size: 10pt; }`,
        # что переопределяет setFont() и ломает крупные шрифты. Локальный
        # stylesheet виджета имеет более высокий приоритет, чем application-level
        # QSS — и заодно поддерживает inline font-size в rich-text spans
        # (см. _format_html). Фон-подложка тоже задаётся здесь, иначе глобальная
        # тема (`solarized.qss`) красит QLabel в свой `QWidget` background.
        bg_rule = (
            f"background-color: {backdrop_color};"
            if backdrop_enabled else "background: transparent;"
        )
        self._label.setStyleSheet(
            f"QLabel {{ font-size: {self._font_pt}pt; font-weight: bold; {bg_rule} }}"
        )
        self._label.setAlignment(self._qt_alignment())

        # Halo вокруг букв через DropShadowEffect с offset=(0,0) — буквы любого
        # цвета остаются читаемыми на любом фоне (тёмные на светлом видны
        # сами, светлый halo "проявляет" их же на тёмном фоне). Эффект
        # вешается на QLabel; opacity всего окна анимируется через
        # setWindowOpacity, чтобы не конфликтовать с graphics effect.
        if shadow_enabled:
            shadow = QGraphicsDropShadowEffect(self._label)
            shadow.setBlurRadius(int(shadow_blur))
            shadow.setOffset(0, 0)
            shadow.setColor(QColor(shadow_color))
            self._label.setGraphicsEffect(shadow)

        self.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._start_fade_out)

    # ---- public API -------------------------------------------------------

    def show_lines(self, lines: list[str]) -> None:
        """Показать список команд: fade-in → hold → fade-out."""
        if not lines:
            return
        self._label.setText(self._format_html(lines))
        self._reposition()
        self._fade_anim.stop()
        self._hide_timer.stop()

        self.show()
        self.raise_()

        self._fade_anim.setDuration(self._fade_in_ms)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(self._target_opacity)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Отвязываем предыдущие коннекты, чтобы старый fade-out не переходил
        # в hide посреди нового fade-in.
        try:
            self._fade_anim.finished.disconnect()
        except RuntimeError:
            pass
        self._fade_anim.finished.connect(
            lambda: self._hide_timer.start(self._hold_ms)
        )
        self._fade_anim.start()

    def hide_now(self) -> None:
        """Досрочно скрыть оверлей плавным fade-out."""
        if not self.isVisible():
            return
        self._hide_timer.stop()
        self._start_fade_out()

    # ---- internals --------------------------------------------------------

    def _qt_alignment(self) -> Qt.Alignment:
        h = Qt.AlignHCenter
        v = {
            "center": Qt.AlignVCenter,
            "top":    Qt.AlignTop,
            "bottom": Qt.AlignBottom,
        }[self._vertical_align]
        return h | v

    def _reposition(self) -> None:
        geom = _pick_screen_geometry(self._monitor_pref)
        self.setGeometry(geom)
        self._label.setGeometry(0, 0, geom.width(), geom.height())

    def _format_html(self, lines: list[str]) -> str:
        """Готовит rich-text: каждая строка цветом ``self._text_color``.

        font-size дублируется в inline-стиле span'а (поверх QLabel.styleSheet
        и setFont) — это страховка от любых application-level QSS-правил,
        которые могут перебить размер на уровне виджета.
        """
        color = html_escape(self._text_color)
        size = self._font_pt
        rows = "<br>".join(
            f"<span style='color:{color}; font-size:{size}pt; font-weight:bold;'>"
            f"{html_escape(s)}</span>"
            for s in lines
        )
        return (
            "<div style='line-height:140%;'>"
            f"{rows}"
            "</div>"
        )

    def _start_fade_out(self) -> None:
        self._fade_anim.stop()
        self._fade_anim.setDuration(self._fade_out_ms)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.InCubic)
        try:
            self._fade_anim.finished.disconnect()
        except RuntimeError:
            pass
        self._fade_anim.finished.connect(self.hide)
        self._fade_anim.start()


def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )


__all__ = ["WakeHintOverlay"]
