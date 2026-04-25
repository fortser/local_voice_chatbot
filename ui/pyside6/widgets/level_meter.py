"""LevelMeter — RMS-индикатор уровня микрофона на QPainter.

Показывает текущий уровень (зелёный/жёлтый/красный градиент по порогам),
сплошную синюю риску шумового фона и пунктирную красную — порога VAD.
Подписывается на ``PipelineBridge.level_update`` и обновляется по событиям.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Slot
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

_INT16_PER_PERCENT = 327.67  # mirrors core.audio_stream._INT16_PER_PERCENT


class LevelMeter(QWidget):
    """Горизонтальный bar с маркерами шума и порога."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rms = 0.0
        self._percent = 0
        self._noise_rms = 0.0
        self._threshold = 0.0
        self.setMinimumHeight(28)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802 — Qt API
        return QSize(360, 28)

    # ---- public API -------------------------------------------------------

    @Slot(float, int)
    def set_level(self, rms: float, percent: int) -> None:
        self._rms = float(rms)
        self._percent = int(max(0, min(100, percent)))
        self.update()

    def set_vad(self, noise_rms: float, threshold: float) -> None:
        self._noise_rms = float(noise_rms)
        self._threshold = float(threshold)
        self.update()

    @property
    def percent(self) -> int:
        return self._percent

    @property
    def rms(self) -> float:
        return self._rms

    @property
    def noise_rms(self) -> float:
        return self._noise_rms

    @property
    def threshold(self) -> float:
        return self._threshold

    # ---- painting ---------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802 — Qt API
        p = QPainter(self)
        try:
            w = self.width()
            h = self.height()

            p.fillRect(0, 0, w, h, QColor("#1b1b1b"))

            pct = self._percent
            fill_w = int(w * pct / 100)
            if pct < 60:
                color = QColor("#3bb143")
            elif pct < 85:
                color = QColor("#e1c340")
            else:
                color = QColor("#c93f3f")
            if fill_w > 0:
                p.fillRect(0, 0, fill_w, h, color)

            noise_pct = max(0.0, min(100.0, self._noise_rms / _INT16_PER_PERCENT))
            nx = int(w * noise_pct / 100)
            if 0 <= nx < w:
                pen = QPen(QColor("#4a8fe7"))
                pen.setWidth(2)
                p.setPen(pen)
                p.drawLine(nx, 2, nx, h - 2)

            thr_pct = max(0.0, min(100.0, self._threshold / _INT16_PER_PERCENT))
            tx = int(w * thr_pct / 100)
            if 0 <= tx < w:
                pen = QPen(QColor("#ff4b4b"))
                pen.setWidth(2)
                pen.setStyle(Qt.DashLine)
                p.setPen(pen)
                p.drawLine(tx, 0, tx, h)
        finally:
            p.end()
