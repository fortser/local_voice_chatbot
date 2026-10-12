"""Speech tools pages and a non-activating, draggable dictation control."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
    QPlainTextEdit, QProgressBar, QVBoxLayout, QWidget,
)

from .components import Card, LevelMeter, button, label
from .dictation_control import DictationControl


def model_description(kind):
    from config import settings
    if kind == "stt":
        stt = settings.stt
        if stt.provider.lower() == "gigaam":
            return f"GigaAM-v3 · {stt.gigaam.revision} · {stt.gigaam.device}"
        return f"Whisper · {stt.whisper_model_size} · {stt.whisper_device}"
    # Existing config shim is the provider factories' source of truth.
    from config import TTS_PROVIDER, SILERO_SPEAKER, SILERO_DEVICE, TTS_DEVICE
    if TTS_PROVIDER.lower() == "silero":
        return f"Silero · {SILERO_SPEAKER} · {SILERO_DEVICE}"
    from config import TTS_SPEAKER_NAME
    return f"XTTS · {TTS_SPEAKER_NAME or 'голос из настроек'} · {TTS_DEVICE}"


class SpeechPage(QWidget):
    kind = ""

    def __init__(self, context):
        super().__init__()
        self.context = context
        self.backend = context.backend.speech
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(18)
        self.body.addWidget(label(model_description(self.kind), "muted"))
        self.body.addWidget(label("Работает независимо от запуска ассистента. Модель загрузится при первом использовании.", "muted"))
        self.card = Card()
        self.status = label("Готово к работе" if not context.preview else "Предпросмотр · операции отключены", "muted")
        self.body.addWidget(self.status)
        self.body.addWidget(self.card)
        self.body.addStretch()
        self.backend.status.connect(self._status)
        self.backend.error.connect(self._error)
        self.backend.busy_changed.connect(self.refresh)
        context.backend.state_changed.connect(self.refresh)
        context.backend.startup_started.connect(self.refresh)

    def _status(self, kind, message):
        if kind == self.kind and not self.context._closing:
            self.status.setText(message)

    def _error(self, kind, message):
        self._status(kind, message)

    def available(self):
        owner = self.context.backend
        return (not self.context.preview and not self.context._closing and not self.backend.busy
                and not owner._operation_pending.is_set() and owner._startup_started_at is None
                and not owner._closing.is_set())

    def refresh(self, *args):
        pass


class STTPage(SpeechPage):
    kind = "stt"
    external_requested = Signal()

    def __init__(self, context):
        super().__init__(context)
        self.floating = None
        self.hotkey = None
        self._recording = False
        self._audio_snapshot = {}
        microphone = Card("Аудиовход")
        self.audio_label = label("Микрофон: ожидание устройств", "muted")
        microphone.body.addWidget(self.audio_label)
        row = QHBoxLayout()
        self.audio_input = QComboBox()
        self.audio_input.setAccessibleName("Микрофон по умолчанию Windows")
        self.audio_input.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.audio_input.setMinimumContentsLength(15)
        self.audio_input.setToolTip("Общий микрофон диктовки и ассистента. Выбор меняет вход Windows, включая связь.")
        self.audio_input.activated.connect(self._select_audio)
        self.audio_refresh = button("Обновить устройства", context.backend.request_audio_devices)
        row.addWidget(self.audio_input, 1)
        row.addWidget(self.audio_refresh)
        microphone.body.addLayout(row)
        self.level = LevelMeter()
        self.level_text = label("Ожидание аудиопотока", "muted")
        microphone.body.addWidget(self.level)
        microphone.body.addWidget(self.level_text)
        self.body.insertWidget(2, microphone)
        context.backend.audio_devices_update.connect(self._audio_devices)
        context.backend.level_update.connect(self._level)
        self.destination = QComboBox()
        self.destination.addItem("В поле раздела", "local")
        self.destination.addItem("В активное приложение", "external")
        saved_destination = context.settings.value("speech/destination", "local")
        self.destination.setCurrentIndex(max(0, self.destination.findData(saved_destination)))
        self.destination.currentIndexChanged.connect(self._save_preferences)
        self.destination.setAccessibleName("Куда вставлять диктовку")
        self.card.body.addWidget(self.destination)
        row = QHBoxLayout()
        self.start = button("Начать", lambda: self.start_recording(), "primary")
        self.stop = button("Стоп", self.stop_recording)
        self.cancel = button("Отменить", self.backend.cancel)
        self.open_file = button("Открыть WAV / FLAC", self.choose_file)
        for widget in (self.start, self.stop, self.cancel, self.open_file):
            row.addWidget(widget)
        self.card.body.addLayout(row)
        self.overlay = QCheckBox("Плавающая кнопка и Ctrl+Alt+D")
        self.overlay.setToolTip("Начать или остановить диктовку в активное приложение, сохранив фокус его поля ввода")
        self.overlay.toggled.connect(self.toggle_overlay)
        self.overlay.setEnabled(not context.preview)
        self.card.body.addWidget(self.overlay)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Распознанный текст появится здесь. Его можно исправить, скопировать или сохранить.")
        self.editor.setMinimumHeight(140)
        self.editor.setAccessibleName("Распознанный текст")
        self.card.body.addWidget(self.editor)
        actions = QHBoxLayout()
        self.copy = button("Копировать", lambda: QApplication.clipboard().setText(self.editor.toPlainText()))
        self.clear = button("Очистить", self.editor.clear)
        self.save = button("Сохранить TXT", self.save_text)
        for widget in (self.copy, self.clear, self.save):
            actions.addWidget(widget)
        self.card.body.addLayout(actions)
        self.editor.textChanged.connect(self.refresh)
        self.backend.text_ready.connect(self.receive_text)
        self.external_requested.connect(self.toggle_external)
        # Restore only after all controls exist; never start recording on restore.
        self.overlay.setChecked(context.settings.value("speech/overlay_enabled", False, type=bool))
        self.refresh()

    def _save_preferences(self, *args):
        if not self.context.preview:
            settings = self.context.settings
            settings.setValue("speech/destination", self.destination.currentData())
            settings.setValue("speech/overlay_enabled", self.overlay.isChecked())
            settings.sync()

    def showEvent(self, event):
        super().showEvent(event)
        if self.available():
            self.context.backend.request_audio_devices()

    def _audio_devices(self, snapshot):
        self._audio_snapshot = snapshot
        info = snapshot.get("input", {})
        active = (snapshot.get("active") or {}).get("input")
        name = active.get("name", "—") if active else "недоступен"
        if active and not snapshot.get("standalone") and active.get("id") != info.get("default_id"):
            name += " · ожидает переключения на выбор Windows"
        self.audio_label.setText(f"Микрофон: {name}")
        self.audio_label.setToolTip(name)
        if not self.audio_input.view().isVisible():
            self.audio_input.blockSignals(True)
            self.audio_input.clear()
            for endpoint in info.get("devices", []):
                self.audio_input.addItem(endpoint["name"], endpoint["id"])
                self.audio_input.setItemData(self.audio_input.count() - 1, endpoint["name"], Qt.ToolTipRole)
            selected = active.get("id") if snapshot.get("standalone") and active else info.get("default_id")
            self.audio_input.setCurrentIndex(self.audio_input.findData(selected))
            self.audio_input.blockSignals(False)
        if not snapshot.get("stream_running", False):
            self._reset_level()
        self.refresh()

    def _select_audio(self, index):
        endpoint_id = self.audio_input.itemData(index)
        if self.available() and endpoint_id:
            self.context.backend.request_set_audio_device("input", endpoint_id)
        self._audio_devices(self._audio_snapshot)

    def _level(self, rms, percent):
        self.level.set_level(rms, percent)
        self.level_text.setText(f"Уровень входа · {max(0, min(percent, 100))}%")
        if self.floating:
            self.floating.set_level(rms, percent)

    def _reset_level(self):
        self.level.set_level(0, 0)
        self.level_text.setText("Ожидание аудиопотока")

    def refresh(self, *args):
        available = self.available()
        self.audio_input.setEnabled(available and self.audio_input.count() > 0)
        self.audio_refresh.setEnabled(available)
        if not self.backend.busy and self.context.backend._pipeline is None:
            self._reset_level()
        if not self.backend.busy:
            self._recording = False
        self.start.setEnabled(available)
        self.open_file.setEnabled(available)
        self.destination.setEnabled(available)
        self.stop.setEnabled(self._recording and self.backend.busy)
        self.cancel.setEnabled(self.backend.busy and self.backend.kind == "stt" and not self.context._closing)
        text = bool(self.editor.toPlainText())
        self.copy.setEnabled(text and not self.context.preview)
        self.clear.setEnabled(text and not self.backend.busy)
        self.save.setEnabled(text and available)
        if self.floating:
            self.floating.set_recording(self._recording, available)

    def start_recording(self, external=None):
        if not self.available():
            return
        if external is None:
            external = self.destination.currentIndex() == 1
        if self.backend.start_dictation(external):
            self._recording = True
            self.refresh()

    def stop_recording(self):
        self.backend.stop_dictation()
        self._recording = False
        self.refresh()

    def toggle_external(self):
        if self._recording:
            self.stop_recording()
        elif self.available():
            self.destination.setCurrentIndex(1)
            self.start_recording(external=True)

    def toggle_overlay(self, enabled):
        if self.context.preview:
            return
        self._save_preferences()
        if enabled:
            if self.floating is None:
                self.floating = DictationControl(self)
            self.floating.show()
            if self.hotkey is None:
                from ui.hotkey import HotkeyListener
                self.hotkey = HotkeyListener("<ctrl>+<alt>+d", self.external_requested.emit)
                self.hotkey.start()
        else:
            if self.hotkey:
                self.hotkey.stop()
                self.hotkey = None
            if self.floating:
                self.floating.hide()
        self.refresh()

    def receive_text(self, job_id, text, external):
        if not self.backend.accepts_result(job_id) or self.context._closing:
            return
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        prefix = " " if self.editor.toPlainText() and not self.editor.toPlainText()[-1].isspace() else ""
        cursor.insertText(prefix + text)
        self.editor.setTextCursor(cursor)
        if external:
            try:
                from system.text_injector import inject_text
                if not inject_text(text + " "):
                    self.status.setText("Текст сохранён здесь: активно окно Шурочки")
            except Exception as exc:
                self.status.setText(str(exc))
                self.context.notify(str(exc))

    def choose_file(self):
        if self.available():
            path, _ = QFileDialog.getOpenFileName(self, "Распознать аудио", "", "Аудиофайлы (*.wav *.flac)")
            if path:
                self.backend.transcribe_file(path)

    def save_text(self):
        if self.available():
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить текст", "Распознанный текст.txt", "Текст (*.txt)")
            if path:
                self.backend.save_text(self.editor.toPlainText(), path)

    def _status(self, kind, message):
        super()._status(kind, message)
        if kind == "stt" and self.floating:
            self.floating.state.setText(message)

    def shutdown(self):
        self._save_preferences()
        if self.hotkey:
            self.hotkey.stop()
            self.hotkey = None
        if self.floating:
            self.floating.close()
            self.floating.deleteLater()
            self.floating = None


class TTSPage(SpeechPage):
    kind = "tts"

    def __init__(self, context):
        super().__init__(context)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Введите или вставьте текст для озвучки…")
        self.editor.setAccessibleName("Текст для озвучки")
        self.editor.setMinimumHeight(200)
        self.card.body.addWidget(self.editor)
        row = QHBoxLayout()
        self.play = button("Озвучить", self.play_text, "primary")
        self.stop = button("Остановить", self.backend.cancel)
        self.save = button("Сохранить WAV", self.save_audio)
        for widget in (self.play, self.stop, self.save):
            row.addWidget(widget)
        self.card.body.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.card.body.addWidget(self.progress)
        self.backend.progress.connect(self.show_progress)
        self.editor.textChanged.connect(self.refresh)
        self.refresh()

    def refresh(self, *args):
        available = self.available() and bool(self.editor.toPlainText().strip())
        self.play.setEnabled(available)
        self.save.setEnabled(available)
        self.stop.setEnabled(self.backend.busy and self.backend.kind == "tts" and not self.context._closing)
        self.editor.setReadOnly(self.backend.busy and self.backend.kind == "tts")

    def show_progress(self, done, total):
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    def play_text(self):
        if self.available():
            self.backend.synthesize(self.editor.toPlainText(), play=True)

    def save_audio(self):
        if self.available():
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить озвучку", "Озвучка.wav", "Аудиофайл WAV (*.wav)")
            if path:
                self.backend.synthesize(self.editor.toPlainText(), destination=path)
