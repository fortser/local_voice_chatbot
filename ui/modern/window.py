"""Application shell and explicit page registry. Add pages without changing layouts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QMainWindow, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .components import button, label
from .pages import CommandsPage, HistoryPage, OverviewPage, SettingsPage
from .speech_pages import STTPage, TTSPage
from .theme import stylesheet

STATES = {
    "not_started": "Нажмите «Начать работу», чтобы запустить ассистента",
    "paused": "Прослушивание кодового слова приостановлено",
    "starting": "Подготавливаю ассистента…", "loading_stt": "Загружаю распознавание речи…",
    "loading_tts": "Загружаю голос…", "idle": "Готова к вашей команде",
    "standby_idle": "Слушаю кодовое слово", "calibrating": "Измеряю шум. Пожалуйста, помолчите…",
    "listening": "Слушаю вас…", "processing": "Обрабатываю команду…",
    "speaking": "Озвучиваю ответ…", "warming": "Подготавливаю языковую модель…",
    "wake_heard": "Услышала вас…", "wake_active": "Слушаю вашу команду…",
    "wake_processing": "Обрабатываю команду…", "stopping": "Завершаю работу…",
    "error": "Не удалось запустить ассистента", "stopped": "Ассистент остановлен",
    "switching_audio": "Переключаю аудиоустройство. Во время калибровки сохраняйте тишину…",
}


@dataclass(frozen=True)
class PageSpec:
    key: str
    title: str
    subtitle: str
    factory: Callable


DEFAULT_PAGES = (
    PageSpec("overview", "Обзор", "Всё, что нужно для общения с ассистентом", OverviewPage),
    PageSpec("stt", "Распознавание речи", "Диктовка и аудиофайлы в текст", STTPage),
    PageSpec("tts", "Озвучка текста", "Текст в речь и аудиофайл", TTSPage),
    PageSpec("history", "История", "Ваши команды и ответы в одном месте", HistoryPage),
    PageSpec("commands", "Команды", "Возможности вашего голосового ассистента", CommandsPage),
    PageSpec("settings", "Настройки", "Настройте ассистента под себя", SettingsPage),
)


class ModernWindow(QMainWindow):
    def __init__(self, backend, *, preview: bool = False, settings=None, extra_pages=()) -> None:
        super().__init__()
        self.backend = backend
        self.settings = settings if settings is not None else QSettings("Shura", "ModernUI")
        self.preview = preview
        if not preview:
            backend.configure_audio_preferences({direction: str(self.settings.value(f"audio/{direction}", ""))
                                                 for direction in ("input", "output")})
        self.can_act = False
        self._started = False
        self._listening = False
        self._state = "not_started"
        self._ready = False
        self._wake_available = False
        self._audio_available = True
        self._closing = False
        self._stopped = False
        self.setWindowTitle("Шурочка · Голосовой ассистент" + (" · Предпросмотр" if preview else ""))
        self.setMinimumSize(940, 680)
        self.resize(1180, 850)
        self.setStyleSheet(stylesheet())
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(20, 30, 20, 22)
        nav.setSpacing(10)
        nav.addWidget(label("шурочка", "title"))
        nav.addWidget(label("ГОЛОСОВОЙ АССИСТЕНТ", "eyebrow"))
        nav.addSpacing(38)
        nav.addWidget(label("РАБОЧЕЕ ПРОСТРАНСТВО", "muted"))
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        outer.addWidget(sidebar)

        content = QVBoxLayout()
        content.setContentsMargins(30, 28, 30, 20)
        content.setSpacing(18)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        self.title = label("Обзор", "title")
        self.subtitle = label("", "muted")
        heading.addWidget(self.title)
        heading.addWidget(self.subtitle)
        header.addLayout(heading, 1)
        self.badge = label("ПРЕДПРОСМОТР" if preview else "○  ОЖИДАНИЕ", "eyebrow")
        header.addWidget(self.badge)
        content.addLayout(header)
        self.notice = label("", "error")
        self.notice.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.notice.hide()
        content.addWidget(self.notice)
        self.stack = QStackedWidget()
        content.addWidget(self.stack, 1)
        self.footer = label("Предпросмотр · микрофон и модели не запускаются" if preview else "Ассистент запускается по кнопке «Начать работу» · речевые инструменты работают самостоятельно", "muted")
        content.addWidget(self.footer)
        outer.addLayout(content, 1)

        self.pages = {}
        self.nav_buttons = {}
        self.specs = {}
        for spec in (*DEFAULT_PAGES, *extra_pages):
            if spec.key in self.pages:
                raise ValueError(f"Duplicate page key: {spec.key}")
            page = spec.factory(self)
            page.setObjectName("page")
            self.pages[spec.key] = page
            self.specs[spec.key] = spec
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
            nav_button = button(spec.title, lambda checked=False, key=spec.key: self.navigate(key), "nav")
            nav_button.setCheckable(True)
            self.nav_group.addButton(nav_button)
            self.nav_buttons[spec.key] = nav_button
            nav.addWidget(nav_button)
        nav.addStretch()
        nav.addWidget(label("С ВАМИ НА ОДНОЙ ВОЛНЕ", "eyebrow"))
        nav.addWidget(label("Голос, команды\nи немного магии.", "muted"))
        self.overview = self.pages["overview"]
        self.preferences = self.pages["settings"]
        self.overview.orb.set_animated(self.preferences.animation.isChecked())

        backend.state_changed.connect(self.set_state)
        backend.ready.connect(self._on_ready)
        backend.startup_started.connect(self._on_startup_started)
        self.overview.orb.loading_updated.connect(self._loading_time)
        backend.fatal.connect(self._on_fatal)
        backend.error_message.connect(self.notify)
        backend.ipc_changed.connect(self._ipc)
        backend.stopped.connect(self._on_stopped)
        backend.standby_available.connect(self._standby_available)
        backend.standby_changed.connect(self._standby_changed)
        backend.screenshot_taken.connect(lambda png: self.footer.setText("Снимок экрана сохранён в папке сессий"))
        backend.audio_device_selected.connect(self._save_audio_device)
        backend.audio_devices_update.connect(self._audio_state)
        backend.speech.busy_changed.connect(self._speech_busy)
        self._shortcuts = []
        for sequence, callback in (("Ctrl+Space", self.record), ("Escape", backend.request_cancel)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        for index, key in enumerate(self.pages, 1):
            if index > 9:
                break
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index}"), self)
            shortcut.activated.connect(lambda key=key: self.navigate(key))
            self._shortcuts.append(shortcut)
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.navigate(str(self.settings.value("page", "overview")))
        self.set_state("not_started", None)

    def navigate(self, key: str) -> None:
        if key not in self.pages:
            key = "overview"
        self.stack.setCurrentIndex(list(self.pages).index(key))
        self.nav_buttons[key].setChecked(True)
        self.title.setText(self.specs[key].title)
        self.subtitle.setText(self.specs[key].subtitle)
        if not self.preview:
            self.settings.setValue("page", key)

    def notify(self, message: str) -> None:
        self.notice.setText(message)
        self.notice.show()

    def set_state(self, name: str, detail=None) -> None:
        if self._closing and name != "stopping":
            return
        if name == "idle" and self._wake_available and not self._listening:
            name = "paused"
        self._state = name
        self.can_act = (self._ready and name in {"idle", "standby_idle", "paused"}
                        and not self.preview and not self.backend.speech.busy)
        text = STATES.get(name, name)
        if detail and isinstance(detail, str):
            text += f" · {detail}"
        self.overview.status.setText(text)
        self.overview.orb.set_active(name not in {"not_started", "idle", "standby_idle", "paused", "error", "stopped"})
        self.overview.start.setEnabled(not self._started and not self._ready and not self.preview
                                       and not self._closing and not self.backend.speech.busy)
        if self._ready:
            start_text = "Работа начата"
        elif self._started and name not in {"error", "stopped", "stopping"}:
            start_text = "Запускаю…"
        else:
            start_text = "Начать работу"
        self.overview.start.setText(start_text)
        self._update_listening_button()
        self.overview.standby.setEnabled(self.can_act and self._wake_available and self._audio_available)
        self.overview.set_audio_enabled(self.can_act)
        self.preferences.calibrate.setEnabled(self.can_act and self._audio_available)
        self.preferences.models.setEnabled(self.can_act)
        self.preferences.refresh.setEnabled(self.can_act)
        self.preferences.apply.setEnabled(self.can_act and self.preferences.models.count() > 0)
        if not self.preview:
            badge = {"error": "○  ОШИБКА", "stopped": "○  ОСТАНОВЛЕНА",
                     "not_started": "○  ОЖИДАНИЕ", "paused": "○  ПАУЗА"}
            self.badge.setText(badge.get(name, "●  ГОТОВА" if self.can_act else "○  В РАБОТЕ"))

    def start_work(self) -> None:
        if self._started or self._ready or self.preview or self._closing or self.backend.speech.busy:
            return
        self._started = True
        self.notice.hide()
        self.set_state("starting")
        self.backend.start_pipeline()

    def _on_startup_started(self, expected_seconds: float) -> None:
        if self.preview or self._closing:
            return
        self._started = True
        self.set_state("starting")
        self.overview.loading_status.show()
        self.overview.orb.start_loading(expected_seconds)

    def _loading_time(self, elapsed: float, expected: float) -> None:
        if elapsed < expected:
            text = f"Прошло {int(elapsed)} с · обычно около {expected:.0f} с. Пожалуйста, подождите…"
        else:
            text = f"Прошло {int(elapsed)} с · загрузка дольше обычного. Пожалуйста, подождите…"
        self.overview.loading_status.setText(text)

    def _finish_loading(self, success: bool = False) -> None:
        self.overview.orb.finish_loading(success)
        self.overview.loading_status.hide()

    def _update_listening_button(self) -> None:
        self.overview.pause.setText("Возобновить" if self._ready and not self._listening else "Остановить")
        self.overview.pause.setToolTip(
            "Приостановить прослушивание кодового слова, сохранив модели в памяти" if self._listening
            else "Возобновить прослушивание кодового слова без повторной загрузки моделей")
        self.overview.pause.setEnabled(
            self._ready and self._wake_available and not self.preview and not self._closing
            and (self._listening or (self.can_act and self._audio_available)))

    def toggle_listening(self) -> None:
        if self.overview.pause.isEnabled():
            self.backend.request_toggle_standby(not self._listening)

    def open_sessions(self) -> None:
        from config import SESSION_BASE_DIR

        path = Path(SESSION_BASE_DIR).expanduser().resolve()
        if not path.is_dir():
            self.notify("Папка ещё не создана. Она появится после первой заметки или снимка.")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.notify("Не удалось открыть папку с заметками и снимками.")

    def record(self) -> None:
        if self.can_act and self._audio_available:
            self.notice.hide()
            self.set_state("listening")
            self.backend.request_turn()

    def _save_audio_device(self, direction: str, endpoint_id: str) -> None:
        if not self.preview:
            self.settings.setValue(f"audio/{direction}", endpoint_id)
            self.settings.sync()

    def _audio_state(self, snapshot: dict) -> None:
        self._audio_available = bool(snapshot.get("stream_running", True))
        self._update_listening_button()
        self.overview.standby.setEnabled(self.can_act and self._wake_available and self._audio_available)
        self.preferences.calibrate.setEnabled(self.can_act and self._audio_available)

    def calibrate(self) -> None:
        if self.can_act and self._audio_available:
            self.notice.hide()
            self.set_state("calibrating")
            self.backend.request_recalibrate()

    def _on_ready(self) -> None:
        self._finish_loading(success=True)
        self._ready = True
        self._started = True
        self.set_state("standby_idle" if self._listening else "idle")

    def _speech_busy(self, busy: bool) -> None:
        self.set_state(self._state)

    def _standby_available(self, enabled: bool) -> None:
        self._wake_available = enabled
        self._update_listening_button()
        self.overview.standby.setEnabled(self.can_act and enabled and self._audio_available)

    def _standby_changed(self, enabled: bool) -> None:
        self._listening = enabled
        self._update_listening_button()
        if self._ready and self._state in {"idle", "standby_idle", "paused"}:
            self.set_state("standby_idle" if enabled else "idle")

    def _on_fatal(self, message: str) -> None:
        self._finish_loading()
        self._ready = False
        self.set_state("error")
        self.notify("Не удалось запустить ассистента. " + message)

    def _ipc(self, text: str) -> None:
        if not self.preview:
            self.footer.setText(text)

    def _on_stopped(self) -> None:
        self._finish_loading()
        self._stopped = self._closing or self.backend._shutdown_requested.is_set()
        self._ready = False
        if self._closing:
            self.close()
        elif not self.backend._closing.is_set():
            self._started = False
            self.set_state("error")
            for key in ("stt", "tts"):
                self.pages[key].refresh()
        elif not self.notice.isVisible():
            self.set_state("stopped")

    def closeEvent(self, event) -> None:
        if not self.preview:
            self.settings.setValue("geometry", self.saveGeometry())
        if self._stopped:
            self.pages["stt"].shutdown()
            event.accept()
            return
        event.ignore()
        if not self._closing:
            self._closing = True
            self.pages["stt"].shutdown()
            for key in ("stt", "tts"):
                self.pages[key].refresh()
            self._finish_loading()
            self.set_state("stopping")
            self.footer.setText("Освобождаю микрофон и модели. Окно закроется после завершения.")
            self.backend.shutdown()
