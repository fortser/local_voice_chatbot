"""Translucent dictation orb; clicks and dragging never activate the window."""

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QApplication, QVBoxLayout, QWidget

from .components import VoiceOrb, label
from .theme import stylesheet


class OrbButton(QAbstractButton):
    position_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedSize(164, 164)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._press = None
        self._dragging = False
        self.orb = VoiceOrb()
        self.orb.setMinimumSize(0, 0)
        self.orb.setFixedSize(164, 164)
        self.orb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.orb)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha = 90 if self.isDown() else 55 if self.underMouse() else 25
        painter.setBrush(QColor(109, 214, 178, alpha))
        painter.setPen(QPen(QColor(168, 235, 206, 85), 1))
        painter.drawEllipse(QRectF(self.rect()).adjusted(17, 17, -17, -17))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._origin = self.window().pos()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._press
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self._dragging = True
            if self._dragging:
                self.setDown(False)
                self.window().move(self._origin + delta)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = None
            if self._dragging:
                self._dragging = False
                self.setDown(False)
                self.position_changed.emit()
                event.accept()
                return
        super().mouseReleaseEvent(event)


class DictationControl(QWidget):
    def __init__(self, page):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.page = page
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Диктовка")
        self.setStyleSheet(stylesheet())
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._drag = None
        self.setFixedSize(204, 260)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 16)
        layout.setSpacing(2)
        self.toggle = OrbButton()
        self.toggle.clicked.connect(page.toggle_external)
        self.toggle.position_changed.connect(self.save_position)
        self.toggle.orb.set_animated(page.context.settings.value("animation", True, type=bool))
        layout.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignHCenter)
        self.caption = label("Начать диктовку", "eyebrow")
        self.state = label("Нажмите на эмблему", "muted")
        self.state.setFixedHeight(32)
        self.state.setStyleSheet("font-size: 11px;")
        hint = label("Ctrl+Alt+D · потяните для переноса", "muted", wrap=False)
        hint.setStyleSheet("font-size: 9px;")
        for widget in (self.caption, self.state, hint):
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(widget)
        position = page.context.settings.value("speech/floating_position", QPoint(60, 120))
        if not isinstance(position, QPoint):
            position = QPoint(60, 120)
        screen = next((screen for screen in QApplication.screens()
                       if screen.availableGeometry().contains(position)), QApplication.primaryScreen())
        if screen is not None:
            area = screen.availableGeometry()
            position.setX(max(area.left(), min(position.x(), area.right() - self.width() + 1)))
            position.setY(max(area.top(), min(position.y(), area.bottom() - self.height() + 1)))
        self.move(position)
        self.set_recording(False, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        glass = QLinearGradient(rect.topLeft(), rect.bottomRight())
        glass.setColorAt(0, QColor(38, 58, 56, 210))
        glass.setColorAt(1, QColor(16, 25, 29, 175))
        painter.setBrush(glass)
        painter.setPen(QPen(QColor(168, 235, 206, 75), 1))
        painter.drawRoundedRect(rect, 30, 30)

    def set_recording(self, recording, available):
        text = "Остановить запись" if recording else "Начать диктовку"
        self.caption.setText(text)
        self.toggle.setAccessibleName(text)
        self.toggle.setToolTip(text + " в активное приложение. Перетащите для перемещения.")
        self.toggle.setEnabled(available or recording)
        self.toggle.orb.set_active(recording)
        if not recording:
            self.toggle.orb.set_level(0, 0)

    def set_level(self, rms, percent):
        if self.page._recording:
            self.toggle.orb.set_level(rms, percent)

    def save_position(self):
        if not self.page.context.preview:
            self.page.context.settings.setValue("speech/floating_position", self.pos())
            self.page.context.settings.sync()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = None
            self.save_position()
            event.accept()

    def closeEvent(self, event):
        self.save_position()
        super().closeEvent(event)
