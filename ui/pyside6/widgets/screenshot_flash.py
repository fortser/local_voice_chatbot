"""ScreenshotFlashOverlay — визуальное подтверждение сохранённого скриншота.

После успешного захвата экрана появляется поверх всех окон копия кадра в
размер монитора, удерживается ``hold_ms`` миллисекунд статично, затем плавно
зуммируется в точку в центре экрана с одновременным fade-out за ``zoom_ms``.

Окно frameless / on-top / прозрачно для мыши и не претендует на фокус —
пользователь продолжает работать, оверлей не блокирует ввод. После завершения
анимации виджет сам удаляется (``deleteLater``).

Окно крепится к ``QGuiApplication.primaryScreen()``: ``system.screenshot``
по умолчанию снимает основной монитор, поэтому flash отображается там же.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRect,
    QTimer,
    Qt,
)
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

logger = logging.getLogger(__name__)


class ScreenshotFlashOverlay(QWidget):
    """Полноэкранный оверлей: hold → zoom-to-center с fade-out → self-destroy."""

    def __init__(
        self,
        png_bytes: bytes,
        *,
        hold_ms: int = 500,
        zoom_ms: int = 400,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.BypassWindowManagerHint,
        )
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        # Тёмный фон-фоллбэк: если pixmap не декодировался, всё равно увидим
        # факт срабатывания flash'а.
        self.setStyleSheet("background-color: #000;")

        self._hold_ms = max(0, int(hold_ms))
        self._zoom_ms = max(50, int(zoom_ms))

        screen = QGuiApplication.primaryScreen()
        self._screen_geom: QRect = screen.geometry() if screen else QRect(0, 0, 1920, 1080)

        pix = QPixmap()
        ok = pix.loadFromData(QByteArray(png_bytes), "PNG")
        logger.info(
            "ScreenshotFlashOverlay: pixmap loaded=%s, isNull=%s, screen=%dx%d at (%d,%d)",
            ok, pix.isNull(),
            self._screen_geom.width(), self._screen_geom.height(),
            self._screen_geom.x(), self._screen_geom.y(),
        )

        self._label = QLabel(self)
        self._label.setPixmap(pix)
        self._label.setScaledContents(True)
        self._label.setGeometry(0, 0, self._screen_geom.width(), self._screen_geom.height())

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        self.setGeometry(self._screen_geom)

        self._anim_group: QParallelAnimationGroup | None = None
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._start_zoom)

    def show_and_animate(self) -> None:
        logger.info("ScreenshotFlashOverlay.show_and_animate: hold=%dms zoom=%dms",
                    self._hold_ms, self._zoom_ms)
        self.show()
        self.raise_()
        self.activateWindow()
        if self._hold_ms == 0:
            self._start_zoom()
        else:
            self._hold_timer.start(self._hold_ms)

    def _start_zoom(self) -> None:
        center_x = self._screen_geom.x() + self._screen_geom.width() // 2
        center_y = self._screen_geom.y() + self._screen_geom.height() // 2
        end_rect = QRect(center_x, center_y, 1, 1)

        geom_anim = QPropertyAnimation(self, b"geometry", self)
        geom_anim.setDuration(self._zoom_ms)
        geom_anim.setStartValue(self._screen_geom)
        geom_anim.setEndValue(end_rect)
        geom_anim.setEasingCurve(QEasingCurve.InCubic)

        opacity_anim = QPropertyAnimation(self._opacity, b"opacity", self)
        opacity_anim.setDuration(self._zoom_ms)
        opacity_anim.setStartValue(1.0)
        opacity_anim.setEndValue(0.0)
        opacity_anim.setEasingCurve(QEasingCurve.InCubic)

        # Лейбл — child с setScaledContents, поэтому надо в финале
        # вручную ужать его до размеров окна (Qt сам не перепозиционирует
        # на каждом тике geometry-анимации).
        def _resize_label(value: QRect) -> None:
            self._label.setGeometry(0, 0, value.width(), value.height())

        geom_anim.valueChanged.connect(_resize_label)

        group = QParallelAnimationGroup(self)
        group.addAnimation(geom_anim)
        group.addAnimation(opacity_anim)
        group.finished.connect(self.close)
        self._anim_group = group
        group.start()
