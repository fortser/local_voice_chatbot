"""StatusIndicator — иконка + текст статуса pipeline.

Один источник правды для статусов — :data:`STATE_LABELS`. Имена состояний
совпадают с теми, что эмитит ``VoicePipeline`` через ``on_stage`` /
``WakeWordListener.on_state``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from config import WAKE_WORD


STATE_LABELS: dict[str, tuple[str, str]] = {
    "starting":         ("⚙", "Инициализация…"),
    "idle":             ("🟢", "Готов"),
    "calibrating":      ("🔵", "Калибровка"),
    "listening":        ("🔴", "Запись"),
    "processing":       ("🧠", "Обработка"),
    "speaking":         ("🔊", "Воспроизведение"),
    "warming":          ("⏳", "Прогрев LLM"),
    "error":            ("❌", "Ошибка"),
    "stopping":         ("⚫", "Завершение…"),
    "stopped":          ("⚫", "Остановлен"),
    "standby_idle":     ("🛌", "Дежурный: жду «{wake}»"),
    "wake_heard":       ("👂", "Услышал — подождите"),
    "wake_active":      ("🎙", "Слушаю вопрос"),
    "wake_processing":  ("🧠", "Обработка (дежурный)"),
}


class StatusIndicator(QWidget):
    """Иконка + жирный текст состояния."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._icon = QLabel("⚙")
        f_icon = QFont()
        f_icon.setPointSize(16)
        self._icon.setFont(f_icon)
        layout.addWidget(self._icon)

        self._text = QLabel("Инициализация…")
        f_text = QFont()
        f_text.setPointSize(11)
        f_text.setBold(True)
        self._text.setFont(f_text)
        self._text.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        layout.addWidget(self._text, stretch=1)

        self._state_name = "starting"

    @Slot(str, object)
    def set_state(self, name: str, detail: object = None) -> None:
        icon, label = STATE_LABELS.get(name, ("?", name))
        if "{wake}" in label:
            label = label.replace("{wake}", WAKE_WORD)
        self._icon.setText(icon)
        text = label if not detail else f"{label}: {detail}"
        self._text.setText(text)
        self._state_name = name

    @property
    def state_name(self) -> str:
        return self._state_name
