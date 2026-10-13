"""Reusable presentation components; no pipeline dependencies."""

from math import ceil, cos, pi, sin
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QIcon, QImage, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from .theme import COLORS, ICON_PATH, ICON_PNG_PATH


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


def app_icon() -> QIcon:
    """Window and taskbar icon; an empty icon keeps Qt's default if assets are missing."""
    for path in (ICON_PATH, ICON_PNG_PATH):
        if path.is_file():
            icon = QIcon(str(path))
            if icon.availableSizes():
                return icon
    return QIcon()


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


class PixelLogo(QWidget):
    """Pixel-art portrait in a rounded frame; the frame glows while Shura listens.

    While listening, a bright light runs clockwise around the frame and the inner
    glow breathes. With animation disabled the frame simply glows steadily.

    The sprite is stored at its native grid size. It is enlarged by an integer
    factor without smoothing and only then fitted to the frame, so pixels stay
    square and crisp at any frame width and Windows display scale. When the
    sidebar is short the frame gets lower and the portrait is cropped from the
    bottom, keeping the face and the hand at the ear.
    """

    BORDER = 2
    RADIUS = 14
    FACE_ROWS = 50      # sprite rows kept in the most compact form: face and hand
    MIN_VISIBLE = 64    # below this height the logo is hidden entirely

    def __init__(self, path, width: int) -> None:
        super().__init__()
        self._sprite = QImage(str(path))
        self._hint_width = width
        self._cache: tuple | None = None
        self._listening = False
        self._animated = True
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        # Never taller than the full portrait; free to shrink when the sidebar is short.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.setToolTip("Шурочка подслушивает…")
        self.setAccessibleName("Логотип Шурочки")
        if self._sprite.isNull():
            self.hide()

    @property
    def is_listening(self) -> bool:
        return self._listening

    def _full_height(self, width: int) -> int:
        if self._sprite.isNull() or self._sprite.width() == 0:
            return 0
        return round((width - 2 * self.BORDER) * self._sprite.height() / self._sprite.width()) + 2 * self.BORDER

    def sizeHint(self) -> QSize:
        return QSize(self._hint_width, self._full_height(self._hint_width))

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

    def set_listening(self, listening: bool) -> None:
        if listening == self._listening:
            return
        self._listening = listening
        self._phase = 0.0
        self._sync_timer()

    def set_animated(self, enabled: bool) -> None:
        self._animated = enabled
        self._sync_timer()

    def _sync_timer(self) -> None:
        if self.isVisible() and self._listening and self._animated:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _tick(self) -> None:
        self._phase += 0.12
        self.update()

    @property
    def is_animating(self) -> bool:
        return self._timer.isActive()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _portrait(self, inner: QRectF, ratio: float) -> QImage:
        """Sprite scaled to the frame width, cropped to the frame height, in device pixels."""
        key = (inner.width(), inner.height(), ratio)
        if self._cache and self._cache[0] == key:
            return self._cache[1]
        width = max(1, round(inner.width() * ratio))
        height = max(1, round(inner.height() * ratio))
        scale = width / self._sprite.width()
        # Integer nearest-neighbour step first, then one smooth step: square pixels, soft-free.
        step = max(1, ceil(scale))
        big = self._sprite.scaled(self._sprite.width() * step, self._sprite.height() * step,
                                  Qt.IgnoreAspectRatio, Qt.FastTransformation)
        full_height = round(self._sprite.height() * scale)
        scaled = big.scaled(width, full_height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        # Crop from the bottom first; once only the face is left, trim the hair on top too.
        face_height = round(self.FACE_ROWS * scale)
        top = max(0, min(face_height - height, round(6 * scale))) if height < face_height else 0
        portrait = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        portrait.fill(Qt.transparent)
        painter = QPainter(portrait)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.white)
        radius = (self.RADIUS - self.BORDER) * ratio
        painter.drawRoundedRect(QRectF(0, 0, width, height), radius, radius)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.drawImage(0, 0, scaled, 0, top, width, height)
        painter.end()
        portrait.setDevicePixelRatio(ratio)
        self._cache = (key, portrait)
        return portrait

    # Running light around the frame: (position along the lap, brightness).
    SWEEP = ((0.0, 1.0), (0.10, 0.85), (0.30, 0.35), (0.55, 0.18), (0.88, 0.18), (1.0, 1.0))

    def _light_brush(self, frame: QRectF, alpha: float) -> QBrush:
        accent = QColor(COLORS["accent"])
        if not self._animated:
            accent.setAlpha(int(alpha * 0.8))
            return QBrush(accent)
        # Qt angles grow counter-clockwise: a decreasing start angle moves the head clockwise
        # and the gradient stops trail behind it as a fading tail.
        sweep = QConicalGradient(frame.center(), -self._phase * 50)
        for stop, level in self.SWEEP:
            color = QColor(accent)
            color.setAlpha(int(alpha * level))
            sweep.setColorAt(stop, color)
        return QBrush(sweep)

    def paintEvent(self, event) -> None:
        if self._sprite.isNull() or self.height() < self.MIN_VISIBLE:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        frame = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        b = self.BORDER
        inner = QRectF(self.rect()).adjusted(b, b, -b, -b)
        portrait = self._portrait(inner, self.devicePixelRatioF())

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(COLORS["surface"]))
        painter.drawRoundedRect(frame, self.RADIUS, self.RADIUS)
        painter.drawImage(inner.topLeft(), portrait)

        accent = QColor(COLORS["accent"])
        painter.setBrush(Qt.NoBrush)
        if self._listening:
            breath = 0.75 + 0.25 * sin(self._phase * 1.3) if self._animated else 1.0
            # Inner glow: thin strokes fading away from the edge. While animated they
            # share the running light, so a bright patch sweeps around the portrait.
            steps = 12
            for index in range(steps):
                fade = (1 - index / steps) ** 2
                inset = b + 0.6 + index * 1.1
                painter.setPen(QPen(self._light_brush(frame, 150 * fade * breath), 1.3))
                painter.drawRoundedRect(frame.adjusted(inset, inset, -inset, -inset),
                                        max(2.0, self.RADIUS - inset * 0.7), max(2.0, self.RADIUS - inset * 0.7))
            painter.setPen(QPen(self._light_brush(frame, 255), b + 1.5))
        else:
            accent.setAlpha(95)
            painter.setPen(QPen(accent, 1.2))
        painter.drawRoundedRect(frame.adjusted(b / 2, b / 2, -b / 2, -b / 2), self.RADIUS, self.RADIUS)


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
