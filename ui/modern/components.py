"""Reusable presentation components; no pipeline dependencies."""

from math import cos, pi, sin
import time

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from .theme import COLORS


def label(text: str, role: str = "", *, wrap: bool = True) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    widget.setProperty("role", role)
    widget.setWordWrap(wrap)
    return widget


def button(text: str, callback, role: str = "") -> QPushButton:
    widget = QPushButton(text)
    widget.setProperty("role", role)
    widget.setCursor(Qt.PointingHandCursor)
    widget.clicked.connect(callback)
    return widget


class Card(QFrame):
    def __init__(self, title: str = "") -> None:
        super().__init__()
        self.setProperty("card", True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(22, 20, 22, 20)
        self.body.setSpacing(12)
        if title:
            self.body.addWidget(label(title, "section"))


class VoiceOrb(QWidget):
    """Quiet procedural artwork. Animation follows activity, bars follow RMS."""

    loading_updated = Signal(float, float)
    TICK_COUNT = 48

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(180, 180)
        self.setMaximumWidth(300)
        self.setAccessibleName("Индикатор активности ассистента")
        self._phase = 0.0
        self._level = 0.0
        self._animated = True
        self._active = False
        self._clock = time.monotonic
        self._loading_started_at: float | None = None
        self._loading_duration = 25.0
        self._loading_complete = False
        self._completion_timer = QTimer(self)
        self._completion_timer.setSingleShot(True)
        self._completion_timer.setInterval(800)
        self._completion_timer.timeout.connect(self._clear_loading)
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    @property
    def loading_progress(self) -> float | None:
        if self._loading_complete:
            return 1.0
        if self._loading_started_at is None:
            return None
        elapsed = max(0.0, self._clock() - self._loading_started_at)
        # The last notch is reserved for actual readiness, even on a slow run.
        return min(elapsed / self._loading_duration, (self.TICK_COUNT - 1) / self.TICK_COUNT)

    def start_loading(self, expected_seconds: float) -> None:
        self._completion_timer.stop()
        self._loading_complete = False
        self._loading_duration = max(0.001, expected_seconds)
        self._loading_started_at = self._clock()
        self._emit_loading_time()
        self._sync_timer()

    def finish_loading(self, success: bool) -> None:
        if self._loading_started_at is None:
            return
        self._loading_started_at = None
        self._loading_complete = success
        self.setAccessibleDescription("Загрузка завершена" if success else "Загрузка прервана")
        if success:
            self._completion_timer.start()
        self._sync_timer()

    def _clear_loading(self) -> None:
        self._loading_complete = False
        self.setAccessibleDescription("")
        self.update()

    def _emit_loading_time(self) -> None:
        if self._loading_started_at is not None:
            elapsed = max(0.0, self._clock() - self._loading_started_at)
            self.setAccessibleDescription(f"Загрузка · {int(self.loading_progress * 100)}% · прошло {int(elapsed)} с")
            self.loading_updated.emit(elapsed, self._loading_duration)

    def set_active(self, active: bool) -> None:
        self._active = active
        self._sync_timer()

    def set_animated(self, enabled: bool) -> None:
        self._animated = enabled
        self._sync_timer()

    def _sync_timer(self) -> None:
        if self.isVisible() and (self._loading_started_at is not None or (self._active and self._animated)):
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._emit_loading_time()
        self._sync_timer()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def set_level(self, rms: float, percent: int) -> None:
        self._level = max(0, min(percent, 100)) / 100
        self.update()

    def _tick(self) -> None:
        if self._animated:
            self._phase += 0.06
        self._emit_loading_time()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = min(self.width(), self.height()) * 0.40
        glow = QRadialGradient(center, radius * 1.18)
        glow.setColorAt(0, QColor(109, 214, 178, 52))
        glow.setColorAt(0.70, QColor(109, 214, 178, 16))
        glow.setColorAt(1, QColor(109, 214, 178, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, radius * 1.18, radius * 1.18)
        painter.setBrush(Qt.NoBrush)
        for ring in range(3):
            painter.setPen(QPen(QColor(168, 235, 206, 35 + ring * 24), 1.1))
            r = radius * (0.68 + ring * 0.13)
            painter.drawEllipse(center, r, r)
        progress = self.loading_progress
        completed = int(progress * self.TICK_COUNT) if progress is not None else 0
        for index in range(self.TICK_COUNT):
            angle = -pi / 2 + index * 2 * pi / self.TICK_COUNT
            length = 3 + 8 * (0.5 + 0.5 * sin(angle * 3 + self._phase))
            start = center + QPointF(cos(angle), sin(angle)) * (radius * 0.88)
            end = center + QPointF(cos(angle), sin(angle)) * (radius * 0.88 + length)
            color, width = QColor(168, 235, 206, 140), 1.8
            if progress is not None:
                color = QColor(COLORS["accent"] if index < completed else COLORS["border"])
                if index < completed:
                    width = 2.8
                elif (index == completed and index < self.TICK_COUNT - 1
                      and self._loading_started_at is not None):
                    color = QColor(COLORS["accent"])
                    color.setAlpha(int(170 + 85 * (0.5 + 0.5 * sin(self._phase * 3))))
                    width = 3.2
            painter.setPen(QPen(color, width))
            painter.drawLine(start, end)
        painter.setPen(QPen(QColor(COLORS["accent"]), 5, Qt.SolidLine, Qt.RoundCap))
        for index in range(7):
            height = 8 + (16 + self._level * 42) * (0.3 + 0.7 * abs(sin(index * 0.8 + self._phase)))
            x = center.x() + (index - 3) * 11
            painter.drawLine(QPointF(x, center.y() - height / 2), QPointF(x, center.y() + height / 2))


class LevelMeter(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(24)
        self.percent = 0
        self.setAccessibleName("Уровень микрофона")

    def set_level(self, rms: float, percent: int) -> None:
        self.percent = max(0, min(percent, 100))
        self.setAccessibleDescription(f"{self.percent}%")
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        count = 42
        step = self.width() / count
        for index in range(count):
            painter.setBrush(QColor(COLORS["accent"] if index < self.percent * count / 100 else COLORS["border"]))
            painter.drawRoundedRect(int(index * step), 4, max(2, int(step - 3)), 16, 2, 2)
