"""Independent speech UI and lifecycle tests, using only fake providers."""

import os
from pathlib import Path
import queue
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.speech_runtime import SpeechRuntime
from tests.test_audio_device_switch import service
from tests.test_speech_runtime import FakeSTT, FakeTTS
from ui.modern.backend import AssistantBackend
from ui.modern.window import ModernWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_for(app, predicate):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    assert predicate()


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setattr("core.create_llm_provider", Mock(side_effect=AssertionError("no LLM")))
    monkeypatch.setattr("config.LOGS_DIR", tmp_path / "logs")
    runtime = SpeechRuntime(stt_factory=FakeSTT, tts_factory=lambda: FakeTTS(tmp_path), gpu_swap=False)
    owner = AssistantBackend(with_ipc=False)
    owner.speech._runtime_factory = lambda: runtime
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat)
    window = ModernWindow(owner, settings=settings)
    window.show()
    app.processEvents()
    yield window
    window.close()
    wait_for(app, lambda: window._stopped)


def test_pages_work_before_assistant_start(window, app):
    stt = window.pages["stt"]
    tts = window.pages["tts"]
    assert stt.start.isEnabled() and stt.open_file.isEnabled()
    assert not tts.play.isEnabled()
    tts.editor.setPlainText("Текст")
    assert tts.play.isEnabled() and tts.save.isEnabled()
    window.backend.speech.transcribe_file("audio.wav")
    wait_for(app, lambda: stt.editor.toPlainText() == "Спасибо")
    assert window.backend._pipeline is None
    assert window.backend._listener is None and window.backend._server is None
    runtime = window.backend.speech.runtime
    assert runtime._stream is runtime._tts is None


def test_tts_cache_survives_export_failure_and_invalidates_on_edit(window, app, tmp_path):
    speech = window.backend.speech
    target = tmp_path / "result.wav"
    assert speech.synthesize("Первый текст", destination=str(target))
    wait_for(app, lambda: not speech.busy)
    tts = speech.runtime.tts
    assert target.exists() and len(tts.parts) == 1
    assert speech.synthesize("Первый текст", destination=str(tmp_path / "missing" / "fail.wav"))
    wait_for(app, lambda: not speech.busy)
    assert Path(speech._cached_wav).exists()
    assert len(tts.parts) == 1
    assert speech.synthesize("Первый текст", destination=str(target))
    wait_for(app, lambda: not speech.busy)
    assert len(tts.parts) == 1
    assert speech.synthesize("Другой текст", destination=str(target))
    wait_for(app, lambda: not speech.busy)
    assert len(tts.parts) == 2
    assert speech.runtime._stream is speech.runtime._player is None


def test_cancellation_discards_late_transcript_and_external_insertion(window, app, monkeypatch):
    speech = window.backend.speech
    entered, release = threading.Event(), threading.Event()
    stt = speech.runtime.stt
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return "поздний результат"
    stt.transcribe = blocked
    inject = Mock()
    monkeypatch.setattr("system.text_injector.inject_text", inject)
    assert speech.transcribe_file("audio.wav")
    wait_for(app, entered.is_set)
    assert not window.pages["tts"].save.isEnabled()
    assert not window.overview.start.isEnabled()
    assert not speech.synthesize("конкурирующая операция")
    speech.cancel()
    speech.text_ready.emit(speech.job_id, "устаревший результат", True)
    release.set()
    wait_for(app, lambda: not speech.busy)
    assert not window.pages["stt"].editor.toPlainText()
    inject.assert_not_called()


def test_external_insertion_follows_each_delivery_and_keeps_local_copy(window, monkeypatch):
    page = window.pages["stt"]
    inject = Mock(return_value=True)
    monkeypatch.setattr("system.text_injector.inject_text", inject)
    page.receive_text(0, "Первое", True)
    page.receive_text(0, "Второе", True)
    assert [call.args[0] for call in inject.call_args_list] == ["Первое ", "Второе "]
    inject.side_effect = RuntimeError("Вставка заблокирована")
    page.receive_text(0, "Третье", True)
    assert page.editor.toPlainText() == "Первое Второе Третье"
    assert "заблокирована" in window.notice.text()


def test_standby_latest_user_preference_wins(window, app):
    speech = window.backend.speech
    listener = Mock(is_enabled=True)
    window.backend._listener = listener
    entered, release = threading.Event(), threading.Event()
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return "Текст"
    speech.runtime.stt.transcribe = blocked
    speech.transcribe_file("audio.wav")
    wait_for(app, entered.is_set)
    window.backend.request_toggle_standby(False)
    release.set()
    wait_for(app, lambda: not speech.busy)
    listener.disable.assert_called()
    listener.enable.assert_not_called()


def test_close_during_speech_loading_is_asynchronous(window, app):
    speech = window.backend.speech
    entered, release = threading.Event(), threading.Event()
    original = speech.runtime.stt.load_model
    def load():
        entered.set()
        assert release.wait(3)
        original()
    speech.runtime.stt.load_model = load
    speech.transcribe_file("audio.wav")
    wait_for(app, entered.is_set)
    before = time.monotonic()
    window.close()
    assert time.monotonic() - before < 0.5
    assert window.isVisible()
    release.set()
    wait_for(app, lambda: window._stopped)
    assert not window.isVisible()
    assert not speech.runtime.stt.is_loaded


def test_runtime_lock_serializes_tools_with_assistant(window, app):
    speech = window.backend.speech
    runtime = speech.runtime
    calls = []
    runtime.stt.transcribe = lambda *args, **kwargs: calls.append(True) or "Текст"
    with runtime.lock:
        assert speech.transcribe_file("audio.wav")
        app.processEvents()
        assert calls == []
    wait_for(app, lambda: not speech.busy)
    assert calls == [True]


def test_cancel_while_waiting_does_not_wait_for_assistant_lock(window, app):
    speech = window.backend.speech
    runtime = speech.runtime
    with runtime.lock:
        assert speech.transcribe_file("audio.wav")
        speech.cancel()
        wait_for(app, lambda: not speech.busy)
    assert runtime._stt is None


def test_stt_failure_does_not_block_tts(window, app, tmp_path):
    speech = window.backend.speech
    speech.runtime.stt.transcribe = Mock(side_effect=RuntimeError("STT failed"))
    speech.transcribe_file("audio.wav")
    wait_for(app, lambda: not speech.busy)
    target = tmp_path / "still-working.wav"
    assert speech.synthesize("Текст", destination=str(target))
    wait_for(app, lambda: not speech.busy)
    assert target.exists()


def test_preview_never_starts_tools(app, tmp_path):
    owner = AssistantBackend()
    window = ModernWindow(owner, preview=True,
                          settings=QSettings(str(tmp_path / "preview.ini"), QSettings.IniFormat))
    window.pages["tts"].editor.setPlainText("Текст")
    window.pages["stt"].start_recording()
    window.pages["tts"].play_text()
    assert owner.speech._runtime is None
    assert not window.pages["stt"].overlay.isEnabled()
    assert not window.pages["stt"].audio_input.isEnabled()
    assert not window.pages["stt"].audio_refresh.isEnabled()
    assert not window.pages["tts"].play.isEnabled()
    window.close()


def test_speech_preferences_survive_close_and_restore_without_recording(window, app, service, monkeypatch):
    hotkey = Mock()
    monkeypatch.setattr("ui.hotkey.HotkeyListener", Mock(return_value=hotkey))
    page = window.pages["stt"]
    page.destination.setCurrentIndex(1)
    page.overlay.setChecked(True)
    page.floating.move(80, 90)
    window.backend.audio_device_selected.emit("input", "input-new")
    path = window.settings.fileName()
    window.close()
    wait_for(app, lambda: window._stopped)
    hotkey.stop.assert_called_once()
    assert page.floating is None

    owner = AssistantBackend(with_ipc=False)
    owner._audio_service = service[0]
    restored = ModernWindow(owner, settings=QSettings(path, QSettings.Format.IniFormat))
    try:
        page = restored.pages["stt"]
        assert page.destination.currentData() == "external"
        assert page.overlay.isChecked() and page.floating.isVisible()
        assert page.floating.pos() == QPoint(80, 90)
        assert not page._recording
        assert owner.speech._runtime is None and owner._pipeline is None
        assert owner._audio_preferences["input"] == "input-new"
        restored.show()
        restored.navigate("stt")
        wait_for(app, lambda: page.audio_input.currentData() == "input-new")
        page.destination.setCurrentIndex(0)
        page.overlay.setChecked(False)
        # Changes are durable even before closing the window.
        saved = QSettings(path, QSettings.Format.IniFormat)
        assert saved.value("speech/destination") == "local"
        assert not saved.value("speech/overlay_enabled", type=bool)
        assert saved.value("audio/input") == "input-new"
    finally:
        restored.close()
        wait_for(app, lambda: restored._stopped)


def test_preview_does_not_restore_hotkey_or_write_speech_preferences(app, tmp_path, monkeypatch):
    factory = Mock()
    monkeypatch.setattr("ui.hotkey.HotkeyListener", factory)
    settings = QSettings(str(tmp_path / "preview-speech.ini"), QSettings.Format.IniFormat)
    settings.setValue("speech/destination", "external")
    settings.setValue("speech/overlay_enabled", True)
    settings.sync()
    window = ModernWindow(AssistantBackend(with_ipc=False), preview=True, settings=settings)
    try:
        page = window.pages["stt"]
        assert page.destination.currentData() == "external"
        assert page.overlay.isChecked()
        assert page.floating is None
        page.destination.setCurrentIndex(0)
        page.overlay.setChecked(False)
    finally:
        window.close()
        wait_for(app, lambda: window._stopped)
    factory.assert_not_called()
    assert settings.value("speech/destination") == "external"
    assert settings.value("speech/overlay_enabled", type=bool)


def test_floating_orb_click_drag_transparency_and_recording(window, app, monkeypatch):
    hotkey = Mock()
    factory = Mock(return_value=hotkey)
    monkeypatch.setattr("ui.hotkey.HotkeyListener", factory)
    page = window.pages["stt"]
    callback = Mock()
    monkeypatch.setattr(page, "toggle_external", callback)
    page.overlay.setChecked(True)
    control = page.floating
    page.toggle_overlay(True)
    factory.assert_called_once()
    hotkey.start.assert_called_once()
    app.processEvents()
    assert control.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert control.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert control.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert control.toggle.focusPolicy() == Qt.FocusPolicy.NoFocus
    image = control.grab().toImage()
    assert image.pixelColor(0, 0).alpha() == 0
    assert 0 < image.pixelColor(10, control.height() // 2).alpha() < 255
    QTest.mouseClick(control.toggle, Qt.MouseButton.LeftButton)
    callback.assert_called_once()
    callback.reset_mock()

    origin = control.pos()
    local = QPointF(control.toggle.rect().center())
    start = QPointF(control.toggle.mapToGlobal(local.toPoint()))
    delta = QPointF(40, 30)
    for kind, position, buttons in (
        (QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton),
        (QEvent.Type.MouseMove, start + delta, Qt.MouseButton.LeftButton),
        (QEvent.Type.MouseButtonRelease, start + delta, Qt.MouseButton.NoButton),
    ):
        event = QMouseEvent(kind, local, position,
                            Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton,
                            buttons, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(control.toggle, event)
    assert control.pos() == origin + delta.toPoint()
    assert window.settings.value("speech/floating_position") == control.pos()
    callback.assert_not_called()

    page._recording = True
    window.backend.speech._busy = True
    try:
        page.refresh()
        window.backend.level_update.emit(1000, 65)
        assert control.toggle.orb._active
        assert control.toggle.orb._level == 0.65
        assert control.toggle.isEnabled()
        assert control.toggle.accessibleName() == "Остановить запись"
        window.preferences.animation.setChecked(False)
        assert not control.toggle.orb._timer.isActive()
    finally:
        window.backend.speech._busy = False
        page.refresh()
    assert not control.toggle.orb._active
    assert control.toggle.orb._level == 0
    assert control.toggle.accessibleName() == "Начать диктовку"
    page.overlay.setChecked(False)
    assert not control.isVisible()
    assert not control.toggle.orb._timer.isActive()


def test_successful_queued_results_survive_next_submission(window):
    speech = window.backend.speech
    speech.job_id = 2
    assert speech.accepts_result(1)
    speech.cancel()
    speech.job_id = 3
    assert speech.accepts_result(1)
    assert not speech.accepts_result(2)


def test_tools_still_work_after_assistant_initialization_failure(window, app, tmp_path):
    pipeline = Mock()
    pipeline.start.side_effect = RuntimeError("Микрофон недоступен")
    window.backend._pipeline_factory = lambda: pipeline
    window.start_work()
    wait_for(app, lambda: window.backend._thread is None and window.pages["stt"].start.isEnabled())
    assert window.pages["stt"].start.isEnabled()
    assert not window._stopped
    target = tmp_path / "after-assistant-failure.wav"
    assert window.backend.speech.synthesize("Текст", destination=str(target))
    wait_for(app, lambda: not window.backend.speech.busy and window.overview.start.isEnabled())
    assert target.exists()
    assert window.overview.start.isEnabled()


def test_stt_lists_saved_microphone_without_loading_runtime(window, app, service):
    audio, state = service
    owner = window.backend
    owner._audio_service = audio
    owner.configure_audio_preferences({"input": "input-new"})
    window.navigate("stt")
    page = window.pages["stt"]
    wait_for(app, lambda: page.audio_input.isEnabled())
    assert page.audio_input.currentData() == "input-new"
    assert "input new" in page.audio_label.text()
    assert window.overview.audio_combos["input"].currentData() == "input-new"
    assert owner.speech._runtime is None
    assert owner._pipeline is None
    audio._set_default.assert_not_called()

    state["input"]["devices"] = []
    page.audio_refresh.click()
    wait_for(app, lambda: not owner.speech.busy)
    assert page.audio_input.count() == 0 and not page.audio_input.isEnabled()
    assert "недоступен" in page.audio_label.text()
    assert page.open_file.isEnabled()


@pytest.mark.parametrize("fail", [False, True])
def test_stt_selects_shared_input_and_preserves_selection_on_failure(window, app, service, monkeypatch, fail):
    audio, state = service
    owner = window.backend
    owner._audio_service = audio
    stream = SimpleNamespace(is_running=False, set_device=Mock(), stop=Mock())
    owner.speech.runtime._stream = stream
    resolver = Mock(return_value={"input": 7})
    if fail:
        resolver.side_effect = RuntimeError("Устройство недоступно")
    monkeypatch.setattr("system.audio_devices.resolve_wasapi_devices", resolver)
    window.navigate("stt")
    page = window.pages["stt"]
    wait_for(app, lambda: page.audio_input.isEnabled())
    page.audio_input.activated.emit(page.audio_input.findData("input-new"))
    wait_for(app, lambda: page.audio_input.isEnabled())
    if fail:
        assert state["input"]["default_id"] == "input-old"
        assert page.audio_input.currentData() == "input-old"
        assert not window.settings.value("audio/input")
        stream.set_device.assert_not_called()
        assert "недоступно" in page.status.text()
    else:
        assert set(state["input"]["roles"].values()) == {"input-new"}
        assert state["output"]["default_id"] == "output-old"
        assert owner._audio_preferences["input"] == "input-new"
        assert window.settings.value("audio/input") == "input-new"
        assert page.audio_input.currentData() == "input-new"
        assert window.overview.audio_combos["input"].currentData() == "input-new"
        stream.set_device.assert_called_once_with(7)
        owner.speech._configure_device("input")
        assert resolver.call_args.args[0]["input"]["id"] == "input-new"
    assert owner.speech.runtime._stt is owner.speech.runtime._tts is None


def test_stt_meter_and_device_controls_during_standalone_dictation(window, app, service, monkeypatch):
    audio, _ = service
    owner = window.backend
    owner._audio_service = audio
    stream = SimpleNamespace(is_running=False, level_queue=queue.Queue(), set_device=Mock(), stop=Mock())
    stream.stop.side_effect = lambda: setattr(stream, "is_running", False)
    owner.speech.runtime._stream = stream
    monkeypatch.setattr("system.audio_devices.resolve_wasapi_devices", lambda *args, **kwargs: {"input": 3})
    entered = threading.Event()

    def dictate(runtime, stop, cancel, on_text, stage):
        stream.is_running = True
        stream.level_queue.put((3276.7, 10))
        entered.set()
        assert stop.wait(3)

    monkeypatch.setattr("core.dictation.dictate", dictate)
    window.navigate("stt")
    page = window.pages["stt"]
    wait_for(app, lambda: page.audio_input.isEnabled())
    page.start.click()
    try:
        wait_for(app, entered.is_set)
        wait_for(app, lambda: page.level.percent == 10)
        assert "10%" in page.level_text.text()
        assert window.overview.level.percent == 10
        assert not page.audio_input.isEnabled() and not page.audio_refresh.isEnabled()
        assert not owner.request_set_audio_device("input", "input-new")
    finally:
        page.stop.click()
    wait_for(app, lambda: not owner.speech.busy and page.audio_input.isEnabled())
    assert page.level.percent == 0
    assert not owner._level_timer.isActive()


def test_stt_device_selection_uses_running_assistant(window, service, monkeypatch):
    audio, _ = service
    owner = window.backend
    owner._audio_service = audio
    monkeypatch.setattr(owner, "_pipeline", Mock())
    submit = Mock(return_value=True)
    monkeypatch.setattr(owner, "_submit", submit)
    from system.audio_devices import default_endpoints
    snapshot = audio.snapshot()
    owner.audio_devices_update.emit({**snapshot, "active": default_endpoints(snapshot), "stream_running": True})
    page = window.pages["stt"]
    page.audio_input.activated.emit(page.audio_input.findData("input-new"))
    submit.assert_called_once_with("audio_device", ("input", "input-new"))
    owner.level_update.emit(500.0, 23)
    assert page.level.percent == 23
    assert owner.speech._runtime is None
