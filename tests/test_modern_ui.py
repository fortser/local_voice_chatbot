"""Offscreen interaction and worker lifecycle tests; no microphone or models."""

import os
import json
import queue
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QWidget

from ui.modern.backend import AssistantBackend
from ui.modern.window import ModernWindow, PageSpec
from utils.startup_timing import StartupTimings


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolate_startup_log(monkeypatch, tmp_path):
    # Mock startups must never train the real user's loading estimate.
    monkeypatch.setattr("config.LOGS_DIR", tmp_path / "logs")


@pytest.fixture
def window(app, tmp_path):
    backend = AssistantBackend(with_ipc=False)
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat)
    instance = ModernWindow(backend, settings=settings)
    instance.show()
    app.processEvents()
    yield instance
    instance.close()
    app.processEvents()


def test_navigation_and_extension(app, tmp_path):
    extra = PageSpec("notes", "Заметки", "Новый модуль", lambda context: QWidget())
    window = ModernWindow(AssistantBackend(), extra_pages=(extra,), preview=True,
                          settings=QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat))
    window.navigate("notes")
    assert window.title.text() == "Заметки"
    assert window.stack.currentIndex() == 4
    window.navigate("missing")
    assert window.stack.currentIndex() == 0
    window.close()


@pytest.fixture
def journal_settings(monkeypatch, tmp_path):
    import config
    import config_model

    path = tmp_path / "settings.toml"
    path.write_text("[llm]\ntimeout = 173\n", encoding="utf-8")
    monkeypatch.setattr(config_model, "SETTINGS_TOML_PATH", path)
    monkeypatch.setattr(config.settings.notes, "html_with_screenshot", False)
    return path


def test_note_journal_toggle_before_start_and_after_ready(journal_settings, window):
    from config_model import load_settings

    assert window.backend._pipeline is None
    window.preferences.note_journal.setChecked(True)
    assert window.backend.note_journal_enabled
    assert load_settings(journal_settings).notes.html_with_screenshot
    assert load_settings(journal_settings).llm.timeout == 173
    # Reload the newest file, preserving edits made outside the running UI.
    journal_settings.write_text("[llm]\ntimeout = 181\n[notes]\nhtml_with_screenshot = true\n", encoding="utf-8")
    window.backend.ready.emit()
    window.preferences.note_journal.setChecked(False)
    assert not window.backend.note_journal_enabled
    assert not load_settings(journal_settings).notes.html_with_screenshot
    assert load_settings(journal_settings).llm.timeout == 181


def test_note_journal_preference_reloads(app, journal_settings, window, monkeypatch, tmp_path):
    import config
    from config_model import load_settings

    window.preferences.note_journal.setChecked(True)
    reloaded = load_settings(journal_settings)
    monkeypatch.setattr(config.settings, "notes", reloaded.notes)
    reopened = ModernWindow(AssistantBackend(with_ipc=False),
                            settings=QSettings(str(tmp_path / "reopened.ini"), QSettings.IniFormat))
    try:
        assert reopened.preferences.note_journal.isChecked()
    finally:
        reopened.close()
        app.processEvents()


def test_note_journal_setting_failure_rolls_back(journal_settings, window, monkeypatch):
    from pathlib import Path

    previous = journal_settings.read_bytes()

    def fail_replace(path, target):
        raise PermissionError("settings locked")

    monkeypatch.setattr(Path, "replace", fail_replace)
    window.preferences.note_journal.setChecked(True)
    assert not window.preferences.note_journal.isChecked()
    assert not window.backend.note_journal_enabled
    assert journal_settings.read_bytes() == previous
    assert "Не удалось сохранить настройку" in window.notice.text()
    assert not list(journal_settings.parent.glob("*.tmp"))


def test_note_journal_preview_never_saves(app, journal_settings, tmp_path):
    backend = AssistantBackend(with_ipc=False)
    backend.set_note_journal_enabled = Mock()
    preview = ModernWindow(backend, preview=True,
                           settings=QSettings(str(tmp_path / "journal-preview.ini"), QSettings.IniFormat))
    previous = journal_settings.read_bytes()
    try:
        preview.preferences.note_journal.setChecked(True)
        backend.set_note_journal_enabled.assert_not_called()
        assert journal_settings.read_bytes() == previous
    finally:
        preview.close()
        app.processEvents()


def test_note_journal_open_missing_and_existing_file(journal_settings, window, monkeypatch, tmp_path):
    import config
    from datetime import datetime
    from pathlib import Path

    base = tmp_path / "notes"
    monkeypatch.setattr(config, "SESSION_BASE_DIR", str(base))
    opener = Mock(return_value=True)
    monkeypatch.setattr("ui.modern.pages.QDesktopServices.openUrl", opener)
    window.preferences._open_note_journal()
    assert not base.exists()
    opener.assert_not_called()
    assert "Журнал появится" in window.notice.text()
    path = base / datetime.now().strftime("%Y-%m") / "notes.html"
    path.parent.mkdir(parents=True)
    path.write_text("journal", encoding="utf-8")
    window.preferences._open_note_journal()
    assert Path(opener.call_args.args[0].toLocalFile()).resolve() == path.resolve()


def test_note_warning_event_is_visible(window):
    window.backend._ui_event("note_warning", {"message": "Заметка сохранена, но скриншот недоступен."})
    assert "скриншот недоступен" in window.notice.text()


def test_record_disabled_until_ready_and_busy(window):
    window.backend.request_turn = Mock()
    window.record()
    window.backend.request_turn.assert_not_called()
    window.backend.ready.emit()
    window.record()
    window.record()
    window.backend.request_turn.assert_called_once()
    assert not window.can_act
    window.backend.state_changed.emit("idle", None)
    assert window.can_act


def test_app_opens_without_starting_backend(app, tmp_path, monkeypatch):
    from ui.modern import app as app_module

    factory = Mock()
    backend = AssistantBackend(with_ipc=False, pipeline_factory=factory)
    instances = []

    def make_window(backend, **kwargs):
        instance = ModernWindow(backend, settings=QSettings(str(tmp_path / "startup.ini"), QSettings.IniFormat), **kwargs)
        instances.append(instance)
        return instance

    monkeypatch.setattr(app_module, "AssistantBackend", lambda **kwargs: backend)
    monkeypatch.setattr(app_module, "ModernWindow", make_window)
    monkeypatch.setattr(QApplication, "exec", lambda self: self.processEvents() or 0)
    assert app_module.run_ui_modern(with_ipc=False) == 0
    try:
        factory.assert_not_called()
        assert backend._thread is None and backend._pipeline is None
        assert not backend._level_timer.isActive()
        assert not backend._health_timer.isActive()
        assert instances[0].overview.start.isEnabled()
    finally:
        instances[0].close()
        app.processEvents()


def test_start_button_initializes_once_and_does_not_record(window):
    window.backend.start_pipeline = Mock()
    window.backend.request_turn = Mock()
    assert window.overview.start.text() == "Начать работу"
    assert window.overview.start.isEnabled()
    assert not window.overview.pause.isEnabled()
    window.overview.start.click()
    window.overview.start.click()
    window.start_work()
    window.backend.start_pipeline.assert_called_once()
    window.backend.request_turn.assert_not_called()
    assert not window.overview.start.isEnabled()
    window.backend.ready.emit()
    assert not window.overview.start.isEnabled()


def test_loading_progress_clock_survives_stage_changes_and_hidden_page(window):
    clock = [100.0]
    orb = window.overview.orb
    orb._clock = lambda: clock[0]
    window.backend.startup_started.emit(25.0)
    assert orb.loading_progress == 0
    assert orb._timer.isActive()
    assert window.overview.loading_status.isVisible()
    assert "около 25 с" in window.overview.loading_status.text()
    clock[0] = 112.5
    window.backend.state_changed.emit("loading_stt", None)
    orb._tick()
    assert orb.loading_progress == 0.5
    assert "12 с" in window.overview.loading_status.text()
    window.navigate("settings")
    assert not orb._timer.isActive()
    clock[0] = 120
    window.navigate("overview")
    assert orb.loading_progress == 0.8
    assert orb._timer.isActive()
    assert "20 с" in window.overview.loading_status.text()
    window.backend.ready.emit()
    assert orb.loading_progress == 1
    assert not window.overview.loading_status.isVisible()
    assert not orb._timer.isActive()


def test_loading_exceeding_estimate_keeps_waiting_even_with_animation_disabled(window):
    clock = [0.0]
    orb = window.overview.orb
    orb._clock = lambda: clock[0]
    window.preferences.animation.setChecked(False)
    window.backend.startup_started.emit(25.0)
    assert orb._timer.isActive()
    clock[0] = 35
    orb._tick()
    assert 0.97 < orb.loading_progress < 1
    assert "дольше обычного" in window.overview.loading_status.text()
    assert not window.overview.start.isEnabled()
    window.backend.fatal.emit("test failure")
    assert orb.loading_progress is None
    assert not orb._timer.isActive()
    assert not window.overview.loading_status.isVisible()
    assert "test failure" in window.notice.text()


def test_close_during_loading_stops_progress(window):
    window.backend.startup_started.emit(25.0)
    window.backend.shutdown = Mock()
    window.close()
    assert window.overview.orb.loading_progress is None
    assert not window.overview.loading_status.isVisible()
    window.backend.stopped.emit()


def test_pause_and_resume_keep_models_and_do_not_cancel_active_turn(window):
    from core.wake_word import WakeWordListener

    backend = window.backend
    pipeline = Mock()
    backend._pipeline = pipeline
    backend._listener = WakeWordListener(pipeline, on_state=backend._wake_event)
    backend.standby_available.emit(True)
    backend.ready.emit()
    backend._listener.enable()
    assert window.overview.pause.text() == "Остановить"
    assert window.overview.standby.isChecked()
    backend._operation_pending.set()
    window.set_state("processing")
    window.overview.pause.click()
    assert not backend._listener.is_enabled
    assert window.overview.pause.text() == "Возобновить"
    assert not window.overview.standby.isChecked()
    assert not window.overview.pause.isEnabled()
    assert backend._jobs.qsize() == 1  # Only the health job from ready.
    pipeline.request_cancel.assert_not_called()
    pipeline.stop.assert_not_called()
    pipeline.start.assert_not_called()
    backend._wake_event("standby_idle", None)  # Late callback must not undo pause.
    assert not window.overview.standby.isChecked()
    backend._operation_pending.clear()
    backend._idle()
    assert "приостановлено" in window.overview.status.text()
    assert window.overview.pause.isEnabled()
    window.overview.pause.click()
    assert backend._listener.is_enabled
    assert window.overview.pause.text() == "Остановить"
    assert window.overview.standby.isChecked()
    assert window.overview.status.text() == "Слушаю кодовое слово"
    pipeline.start.assert_not_called()


def test_unavailable_wake_listener_disables_pause(window):
    window.backend.ready.emit()
    window.backend.standby_available.emit(False)
    assert not window.overview.pause.isEnabled()


@pytest.mark.parametrize("opened", [True, False])
def test_all_history_opens_configured_materials_folder_before_start(window, tmp_path, monkeypatch, opened):
    import config
    from ui.modern import window as window_module

    materials = tmp_path / "Заметки и снимки"
    materials.mkdir()
    monkeypatch.setattr(config, "SESSION_BASE_DIR", str(materials))
    opener = Mock(return_value=opened)
    monkeypatch.setattr(window_module.QDesktopServices, "openUrl", opener)
    window.overview.history.click()
    assert opener.call_args.args[0].toLocalFile() == str(materials.resolve()).replace("\\", "/")
    assert window.stack.currentIndex() == 0
    assert window.backend._thread is None
    if not opened:
        assert "Не удалось открыть" in window.notice.text()


def test_all_history_reports_missing_folder(window, tmp_path, monkeypatch):
    import config
    from ui.modern import window as window_module

    materials = tmp_path / "missing"
    monkeypatch.setattr(config, "SESSION_BASE_DIR", str(materials))
    opener = Mock()
    monkeypatch.setattr(window_module.QDesktopServices, "openUrl", opener)
    window.overview.history.click()
    opener.assert_not_called()
    assert "Папка ещё не создана" in window.notice.text()
    assert not materials.exists()


def test_standby_tracks_backend_including_voice_disable(window):
    window.backend.standby_available.emit(True)
    window.backend.ready.emit()
    window.backend.standby_changed.emit(True)
    assert window.overview.standby.isChecked()
    window.backend.standby_changed.emit(False)
    assert not window.overview.standby.isChecked()


def test_history_escapes_model_markup_filters_and_bounds(window):
    history = window.pages["history"]
    result = SimpleNamespace(user_text="<img src='file:///secret'>", llm_text="<b>Ответ</b>", total_s=1.2)
    window.backend.turn_result.emit(result)
    assert "<b>Ответ</b>" in history.browser.toPlainText()
    assert "<img src=" in history.browser.toPlainText()
    history.search.setText("несуществующий текст")
    assert "Пока ничего нет" in history.browser.toPlainText()
    history.LIMIT = 2
    history._add(result)
    history._add(result)
    assert len(history.entries) == 2


def test_command_search_uses_configured_synonyms(window):
    commands = window.pages["commands"]
    window.backend.commands_list.emit([
        {"name": "note", "synonyms": ["моя новая фраза"], "description": ""},
        {"name": "pause", "synonyms": ["поставь паузу"], "description": ""},
    ])
    commands.search.setText("НОВАЯ")
    assert commands.list.count() == 1
    commands.list.setCurrentRow(0)
    commands._copy()
    assert QApplication.clipboard().text() == "моя новая фраза"


def test_preview_disables_real_actions(app, tmp_path):
    backend = AssistantBackend()
    backend.request_turn = Mock()
    backend.start_pipeline = Mock()
    window = ModernWindow(backend, preview=True,
                          settings=QSettings(str(tmp_path / "preview.ini"), QSettings.IniFormat))
    backend.ready.emit()
    window.record()
    window.start_work()
    backend.request_turn.assert_not_called()
    backend.start_pipeline.assert_not_called()
    assert not window.overview.start.isEnabled()
    assert not window.preferences.calibrate.isEnabled()
    window.close()


def test_model_selection_and_fatal_state(window):
    window.backend.ready.emit()
    window.backend.models_list.emit(["alpha", "beta"], "beta")
    assert window.preferences.models.currentText() == "beta"
    assert window.preferences.apply.isEnabled()
    window.backend.fatal.emit("Микрофон недоступен")
    assert not window.can_act
    assert "Микрофон недоступен" in window.notice.text()


def wait_until(app, predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate()


@pytest.mark.parametrize("outcome", ["ready", "error", "cancelled"])
def test_worker_journals_full_startup_once(app, tmp_path, monkeypatch, outcome):
    clock = [100.0]
    monkeypatch.setattr("ui.modern.backend.time", SimpleNamespace(perf_counter=lambda: clock[0]))
    timing = StartupTimings(tmp_path / "startup.jsonl")
    timing.record(30, "ready")
    timing.record(20, "ready")
    backend = AssistantBackend(with_ipc=False, startup_timings=timing)
    entered, release = threading.Event(), threading.Event()
    estimates, ready, stopped = [], [], []
    backend.startup_started.connect(estimates.append)
    backend.ready.connect(lambda: ready.append(True))
    backend.stopped.connect(lambda: stopped.append(True))

    def initialize():
        entered.set()
        assert release.wait(3)
        clock[0] = 140
        if outcome == "error":
            raise RuntimeError("init failed")
        backend._pipeline = Mock()

    backend._initialize = initialize
    backend.start_pipeline()
    backend.start_pipeline()
    try:
        wait_until(app, entered.is_set)
        assert estimates == [25.0]
        if outcome == "cancelled":
            backend.shutdown()
        release.set()
        wait_until(app, lambda: bool(ready or stopped))
    finally:
        release.set()
        backend.shutdown()
        wait_until(app, lambda: bool(stopped))
    rows = [json.loads(line) for line in timing.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 3
    assert rows[-1]["status"] == outcome
    assert rows[-1]["duration_s"] == 40
    assert timing.estimate_seconds() == (30 if outcome == "ready" else 25)


def test_worker_initialization_error_cleans_partial_pipeline(app):
    pipeline = Mock()
    pipeline.start.side_effect = RuntimeError("init failed")
    backend = AssistantBackend(pipeline_factory=lambda: pipeline, with_ipc=False)
    errors = []
    stopped = []
    backend.fatal.connect(errors.append)
    backend.stopped.connect(lambda: stopped.append(True))
    backend.start_pipeline()
    wait_until(app, lambda: bool(stopped))
    assert errors == ["init failed"]
    pipeline.stop.assert_called_once()
    backend.shutdown()


def test_worker_lifecycle_and_gui_timers(app, monkeypatch):
    listener = Mock(is_enabled=False)
    monkeypatch.setitem(sys.modules, "core.wake_word", SimpleNamespace(WakeWordListener=lambda *a, **k: listener))
    monkeypatch.setattr("config.WAKE_WORD_ENABLED_AT_STARTUP", False)
    pipeline = Mock()
    pipeline._registry = []
    pipeline._llm.model = "test-model"
    pipeline.list_llm_models.return_value = ["test-model"]
    pipeline.stream = SimpleNamespace(is_running=True, level_queue=queue.Queue())
    pipeline.health_check.return_value = {"llm": {"healthy": True}}
    turn_entered = threading.Event()
    pipeline.process_voice_input.side_effect = lambda **kwargs: turn_entered.set()
    worker_threads = []
    pipeline.start.side_effect = lambda **kwargs: worker_threads.append(threading.get_ident())
    backend = AssistantBackend(pipeline_factory=lambda: pipeline, with_ipc=False)
    ready, stopped, health = [], [], []
    backend.ready.connect(lambda: ready.append(True))
    backend.stopped.connect(lambda: stopped.append(True))
    backend.health_update.connect(health.append)
    backend.start_pipeline()
    try:
        wait_until(app, lambda: bool(ready) and bool(health))
        assert worker_threads[0] != threading.get_ident()
        listener.enable.assert_called_once()
        assert backend._level_timer.isActive()
        assert backend._level_timer.thread() == app.thread()
        backend.request_turn()
        wait_until(app, turn_entered.is_set)
    finally:
        backend.shutdown()
        wait_until(app, lambda: bool(stopped))
    assert not backend._level_timer.isActive()
    pipeline.stop.assert_called_once()
    listener.stop.assert_called_once()


def test_close_waits_for_backend_without_blocking(window):
    window.backend.shutdown = Mock()
    window.close()
    assert window.isVisible()
    window.backend.shutdown.assert_called_once()
    window.backend.stopped.emit()
    assert not window.isVisible()


def test_pending_manual_job_ignores_stale_wake_idle(app):
    backend = AssistantBackend()
    backend._pipeline = Mock()
    states = []
    backend.state_changed.connect(lambda name, detail: states.append(name))
    backend.request_turn()
    backend.request_turn()
    backend._wake_event("standby_idle", None)
    assert backend._jobs.qsize() == 1
    assert states == []
    backend.shutdown()


def test_voice_stop_idle_event_unchecks_standby(window):
    window.backend.standby_changed.emit(True)
    window.backend._wake_event("idle", None)
    assert not window.overview.standby.isChecked()


def test_service_models_devices_and_swap_states(window):
    window.backend.model_update.emit({
        "stt": {"provider": "WhisperSTT", "model": "large-v3-turbo", "device": "cuda:0", "loaded": True},
        "tts": {"provider": "SileroTTS", "model": "v5_ru", "device": "cpu", "loaded": True},
    })
    assert "large-v3-turbo · GPU" in window.overview.service_labels["stt"][1].text()
    assert "v5_ru · CPU" in window.overview.service_labels["tts"][1].text()
    window.backend.model_update.emit({"tts": {
        "provider": "XTSTTTS", "model": "xtts_v2", "device": "cuda", "loaded": False, "gpu_swap": True,
    }})
    assert "загрузка по запросу" in window.overview.service_labels["tts"][1].text()
    assert "large-v3-turbo" in window.overview.service_labels["stt"][1].text()
    window.backend.model_update.emit({"stt": {"loaded": False, "gpu_swap": True}})
    assert "временно выгружена" in window.overview.service_labels["stt"][1].text()


def test_gpu_zero_missing_and_multiple_cards(window):
    window.backend.gpu_update.emit({"devices": [
        {"name": "GPU A", "utilization": 0, "memory_used": 2**30, "memory_total": 8 * 2**30},
        {"name": "GPU B", "utilization": None, "memory_used": None, "memory_total": None},
    ]})
    text = window.overview.gpu_status.text()
    assert "0%" in text and "1.00 / 8.00 ГиБ" in text
    assert "GPU B" in text and "Загрузка: —" in text
    window.backend.gpu_update.emit({"devices": [], "error": "Нет драйвера"})
    assert window.overview.gpu_status.text() == "Нет драйвера"


def audio_snapshot():
    return {**{direction: {
        "devices": [{"id": "old", "name": "Длинное имя " * 12}, {"id": "new", "name": "Новое устройство"}],
        "default_id": "old",
    } for direction in ("input", "output")},
        "active": {direction: {"id": "old", "name": "Активное устройство"}
                   for direction in ("input", "output")}, "stream_running": True}


def test_audio_choice_blocks_actions_and_saves_only_success(window):
    window.backend.ready.emit()
    window.backend.audio_devices_update.emit(audio_snapshot())
    combo = window.overview.audio_combos["input"]
    assert combo.currentData() == "old"
    window.backend.request_set_audio_device = Mock(return_value=True)
    combo.activated.emit(1)
    window.backend.request_set_audio_device.assert_called_once_with("input", "new")
    assert not combo.isEnabled() and not window.can_act
    assert window.settings.value("audio/input") is None
    window.backend.audio_device_selected.emit("input", "new")
    assert window.settings.value("audio/input") == "new"
    window.backend.state_changed.emit("idle", None)
    assert combo.isEnabled()


def test_stream_failure_disables_record_but_allows_device_recovery(window):
    window.backend.ready.emit()
    snapshot = audio_snapshot()
    snapshot["stream_running"] = False
    window.backend.audio_devices_update.emit(snapshot)
    assert not window.overview.pause.isEnabled()
    assert window.overview.audio_combos["input"].isEnabled()
    window.backend.request_turn = Mock()
    window.record()
    window.backend.request_turn.assert_not_called()


def test_audio_preferences_are_loaded_on_gui_thread(app, tmp_path):
    settings = QSettings(str(tmp_path / "audio.ini"), QSettings.IniFormat)
    settings.setValue("audio/input", "stable-endpoint-id")
    backend = AssistantBackend()
    instance = ModernWindow(backend, settings=settings)
    assert backend._audio_preferences["input"] == "stable-endpoint-id"
    instance.close()


def test_gpu_monitor_updates_during_blocked_voice_turn(app):
    release = threading.Event()
    entered = threading.Event()
    pipeline = Mock()
    pipeline.health_check.return_value = {}
    pipeline.model_status.return_value = {}
    monitor = Mock()
    monitor.snapshot.return_value = {"devices": [], "error": "test"}

    def turn(**kwargs):
        entered.set()
        assert release.wait(4)

    pipeline.process_voice_input.side_effect = turn
    backend = AssistantBackend(pipeline_factory=lambda: pipeline, gpu_monitor_factory=lambda: monitor)

    def initialize():
        backend._pipeline = pipeline
        backend._start_monitor(backend._monitor_gpu, "test-gpu")

    backend._initialize = initialize
    ticks, stopped = [], []
    backend.gpu_update.connect(ticks.append)
    backend.stopped.connect(lambda: stopped.append(True))
    backend.start_pipeline()
    try:
        wait_until(app, lambda: len(ticks) > 0)
        backend.request_turn()
        wait_until(app, entered.is_set)
        before = len(ticks)
        wait_until(app, lambda: len(ticks) > before)
        assert not release.is_set()
    finally:
        release.set()
        backend.shutdown()
        wait_until(app, lambda: bool(stopped))
    monitor.close.assert_called_once()


def test_audio_backend_restore_missing_device_uses_windows(app):
    from tests.test_audio_device_switch import snapshot
    backend = AssistantBackend()
    backend._pipeline = Mock()
    backend._audio_service = Mock()
    backend._audio_service.snapshot.return_value = snapshot()
    backend._audio_service.switch.side_effect = ValueError("недоступно")
    backend.configure_audio_preferences({"input": "disconnected"})
    errors = []
    backend.error_message.connect(errors.append)
    backend._restore_audio_devices()
    assert "defaults Windows" in errors[0]
    assert backend._pipeline.configure_audio_devices.call_args.args[0]["input"]["id"] == "input-old"


def test_audio_backend_restores_standby_after_switch_failure(app):
    from tests.test_audio_device_switch import snapshot
    backend = AssistantBackend()
    backend._pipeline = Mock()
    backend._pipeline.lock = threading.RLock()
    backend._pipeline.stream.is_running = True
    backend._listener = Mock(is_enabled=True)
    backend._audio_service = Mock()
    backend._audio_service.snapshot.return_value = snapshot()
    backend._audio_service.switch.side_effect = RuntimeError("switch failed")
    saved = []
    backend.audio_device_selected.connect(lambda *args: saved.append(args))
    with pytest.raises(RuntimeError, match="switch failed"):
        backend._change_audio_device(("input", "input-new"))
    backend._listener.disable.assert_called_once()
    backend._listener.enable.assert_called_once()
    assert saved == []


def test_pause_during_audio_switch_is_not_undone(app):
    from tests.test_audio_device_switch import snapshot
    from core.wake_word import WakeWordListener

    backend = AssistantBackend()
    backend._pipeline = Mock()
    backend._pipeline.lock = threading.RLock()
    backend._pipeline.stream.is_running = True
    backend._listener = WakeWordListener(backend._pipeline)
    backend._listener.enable()
    backend._audio_service = Mock()

    def switch(direction, endpoint_id, bind):
        backend.request_toggle_standby(False)
        return snapshot()

    backend._audio_service.switch.side_effect = switch
    backend._change_audio_device(("input", "input-new"))
    assert not backend._listener.is_enabled
    backend._pipeline.stop.assert_not_called()


def test_background_audio_sync_does_not_clear_pending_manual_job(app):
    backend = AssistantBackend()
    backend._pipeline = Mock()
    backend._operation_pending.set()
    backend._change_audio_device(None)
    assert backend._operation_pending.is_set()
    backend._pipeline.configure_audio_devices.assert_not_called()
