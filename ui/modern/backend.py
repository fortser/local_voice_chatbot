"""Qt boundary for VoicePipeline. Heavy work and cleanup never run on the UI thread."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from utils.startup_timing import StartupTimings
from .speech_backend import SpeechToolsBackend

logger = logging.getLogger(__name__)


class AssistantBackend(QObject):
    state_changed = Signal(str, object)
    turn_result = Signal(object)
    health_update = Signal(dict)
    model_update = Signal(dict)
    audio_devices_update = Signal(dict)
    audio_device_selected = Signal(str, str)
    gpu_update = Signal(dict)
    level_update = Signal(float, int)
    models_list = Signal(object, object)
    commands_list = Signal(object)
    standby_changed = Signal(bool)
    standby_available = Signal(bool)
    ipc_changed = Signal(str)
    screenshot_taken = Signal(object)
    ready = Signal()
    startup_started = Signal(float)
    fatal = Signal(str)
    error_message = Signal(str)
    stopped = Signal()
    _health_done = Signal()

    def __init__(self, *, with_ipc: bool = True, ipc_host: str = "127.0.0.1", ipc_port: int = 9999,
                 pipeline_factory=None, audio_service=None, gpu_monitor_factory=None,
                 startup_timings: StartupTimings | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._options = (with_ipc, ipc_host, ipc_port)
        self._pipeline_factory = pipeline_factory
        self._startup_timings = startup_timings
        self._startup_started_at: float | None = None
        self._audio_service = audio_service
        self._gpu_monitor_factory = gpu_monitor_factory
        self._audio_preferences: dict[str, str] = {}
        self._monitors: list[threading.Thread] = []
        self._audio_poll = threading.Event()
        self._audio_sync_pending = threading.Event()
        self._failed_audio_target = None
        self._pipeline: Any = None
        self._listener: Any = None
        self._standby_requested = True
        self._server: Any = None
        self._jobs: queue.Queue = queue.Queue()
        self._closing = threading.Event()
        self._shutdown_requested = threading.Event()
        self._operation_pending = threading.Event()
        self._submission_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._health_pending = False
        self._level_timer = QTimer(self)
        self._level_timer.setInterval(75)
        self._level_timer.timeout.connect(self._poll_level)
        self._health_timer = QTimer(self)
        self._health_timer.setInterval(5000)
        self._health_timer.timeout.connect(self._request_health)
        self.ready.connect(self._start_timers)
        self._health_done.connect(self._clear_health_pending)
        self.speech = SpeechToolsBackend(self)
        self.speech.busy_changed.connect(self._speech_level_timer)

    def start_pipeline(self) -> None:
        with self._submission_lock:
            if self._thread is not None or self._closing.is_set() or self.speech.busy:
                return
            estimate = self._timings().estimate_seconds()
            self._startup_started_at = time.perf_counter()
            self.startup_started.emit(estimate)
            self._thread = threading.Thread(target=self._run, name="modern-ui-pipeline", daemon=True)
            self._thread.start()

    def _timings(self) -> StartupTimings:
        if self._startup_timings is None:
            from config import LOGS_DIR
            self._startup_timings = StartupTimings(LOGS_DIR / "model_startup.jsonl")
        return self._startup_timings

    def _finish_startup(self, status: str) -> None:
        if self._startup_started_at is not None:
            duration = time.perf_counter() - self._startup_started_at
            self._startup_started_at = None
            self._timings().record(duration, status)

    @Slot()
    def _start_timers(self) -> None:
        if not self._closing.is_set():
            self._level_timer.start()
            self._health_timer.start()
            self._request_health()

    def _submit(self, name: str, argument=None) -> bool:
        with self._submission_lock:
            if self._pipeline is None or self._closing.is_set():
                return False
            if name in {"turn", "recalibrate", "model", "audio_device"}:
                if self._operation_pending.is_set():
                    return False
                self._operation_pending.set()
            self._jobs.put((name, argument))
            return True

    def request_turn(self) -> None:
        self._submit("turn")

    def request_recalibrate(self) -> None:
        self._submit("recalibrate")

    def request_list_models(self) -> None:
        self._submit("models")

    def request_set_model(self, name: str) -> None:
        if name.strip():
            self._submit("model", name)

    @property
    def note_journal_enabled(self) -> bool:
        from config import settings

        return settings.notes.html_with_screenshot

    def set_note_journal_enabled(self, enabled: bool) -> bool:
        """Persist a small setting even before the pipeline is initialized.

        Commands snapshot the runtime flag at entry, so an in-flight note
        keeps its original mode. Disk changes become live only on success.
        """
        from config import settings
        from config_model import load_settings, save_settings

        with self._submission_lock:
            if self._closing.is_set():
                return False
            try:
                updated = load_settings()
                updated.notes.html_with_screenshot = bool(enabled)
                save_settings(updated)
            except Exception:
                logger.exception("Не удалось сохранить настройку журнала заметок")
                self.error_message.emit("Не удалось сохранить настройку журнала заметок.")
                return False
            settings.notes.html_with_screenshot = bool(enabled)
            return True

    def request_toggle_standby(self, enabled: bool) -> None:
        if self._listener is None or self._closing.is_set():
            return
        # Listener controls only set Events; pausing must not wait behind a
        # voice turn, health check or model operation in the worker queue.
        self._standby_requested = bool(enabled)
        if self.speech.busy:
            self.speech.resume_standby = bool(enabled)
            return
        if enabled:
            self._listener.enable()
        else:
            self._listener.disable()
        self.standby_changed.emit(self._listener.is_enabled)

    def configure_audio_preferences(self, preferences: dict[str, str]) -> None:
        """Copy QSettings values on the GUI thread before starting workers."""
        self._audio_preferences = dict(preferences)

    def request_audio_devices(self) -> None:
        self._failed_audio_target = None
        if self._pipeline is None:
            self.speech.refresh_audio_devices()
            return
        self._audio_poll.set()

    def request_set_audio_device(self, direction: str, endpoint_id: str) -> bool:
        if (self._closing.is_set() or self._startup_started_at is not None
                or self._operation_pending.is_set() or direction not in {"input", "output"}):
            return False
        if self._pipeline is None:
            return self.speech.select_audio_device(direction, endpoint_id)
        if self._audio_service is None:
            return False
        return self._submit("audio_device", (direction, endpoint_id))

    def request_cancel(self) -> None:
        if self.speech.busy:
            self.speech.cancel()
            return
        if self._pipeline is not None:
            self._pipeline.request_cancel()

    def shutdown(self) -> None:
        self._shutdown_requested.set()
        if self._closing.is_set():
            return
        self._closing.set()
        self.speech.begin_shutdown()
        self._audio_poll.set()
        self._level_timer.stop()
        self._health_timer.stop()
        self.request_cancel()
        if self._pipeline is not None:
            self._pipeline.request_cancel()
        self._jobs.put(("stop", None))
        if self._thread is None:
            if self.speech._runtime is None and not self.speech.busy:
                self.stopped.emit()
            else:
                def finish():
                    self.speech.finish_shutdown()
                    self.stopped.emit()
                threading.Thread(target=finish, name="speech-shutdown", daemon=True).start()

    def _run(self) -> None:
        failed = False
        try:
            if self._pipeline_factory is None:
                with self.speech.runtime.lock:
                    self._initialize()
            else:
                self._initialize()
            if self._closing.is_set():
                return
            self._finish_startup("ready")
            self.ready.emit()
            self._idle()
            while not self._closing.is_set():
                name, argument = self._jobs.get()
                if name == "stop" or self._closing.is_set():
                    break
                try:
                    self._execute(name, argument)
                except Exception as exc:
                    logger.exception("Modern UI operation failed: %s", name)
                    self.error_message.emit(str(exc))
                finally:
                    if name == "health":
                        self._health_done.emit()
                    if name == "audio_sync":
                        self._audio_sync_pending.clear()
                    if name in {"turn", "recalibrate", "model", "audio_device"}:
                        self._operation_pending.clear()
                        self._idle()
        except Exception as exc:
            failed = True
            self._closing.set()
            self._finish_startup("error")
            logger.exception("Modern UI initialization failed")
            self.fatal.emit(str(exc))
        finally:
            self._finish_startup("cancelled")
            self._closing.set()
            self._audio_poll.set()
            for monitor in self._monitors:
                monitor.join()
            self.speech.begin_shutdown()
            if self.speech._thread is not None:
                self.speech._thread.join()
            for resource in (self._listener, self._server, self._pipeline):
                if resource is not None:
                    try:
                        resource.stop()
                    except Exception:
                        logger.exception("Modern UI cleanup failed")
            self.speech.finish_shutdown()
            if failed and not self._shutdown_requested.is_set():
                self._pipeline = self._listener = self._server = None
                self._monitors.clear()
                self._thread = None
                self._operation_pending.clear()
                self.speech.reopen_after_assistant_failure()
                self._closing.clear()
            self.stopped.emit()

    def _initialize(self) -> None:
        factory = self._pipeline_factory
        if factory is None:
            from bootstrap import bootstrap
            from main import VoicePipeline
            bootstrap()
            factory = lambda: VoicePipeline(speech_runtime=self.speech.runtime)
        self._pipeline = factory()
        if self._pipeline_factory is None:
            if self._audio_service is None:
                from system.audio_devices import WindowsAudioDevices
                self._audio_service = WindowsAudioDevices()
            if self._gpu_monitor_factory is None:
                from utils.gpu_monitor import GPUMonitor
                self._gpu_monitor_factory = GPUMonitor
        if self._gpu_monitor_factory is not None:
            self._start_monitor(self._monitor_gpu, "modern-ui-gpu")
        if self._audio_service is not None:
            self._restore_audio_devices()
        if self._closing.is_set():
            return
        self._pipeline.start(on_stage=lambda name, detail: self.state_changed.emit(name, detail))
        if self._closing.is_set():
            return
        if self._audio_service is not None:
            self._start_monitor(self._monitor_audio, "modern-ui-audio")
        self._pipeline.set_ui_callback(self._ui_event)
        registry = getattr(self._pipeline, "_registry", ())
        self.commands_list.emit([
            {"name": cmd.name, "synonyms": list(cmd.synonyms),
             "description": getattr(cmd, "description", "")}
            for cmd in registry
        ])
        with_ipc, host, port = self._options
        self.ipc_changed.emit("IPC выключен")
        if with_ipc:
            try:
                from ipc.server import VoiceAIServer
                self._server = VoiceAIServer(self._pipeline, host=host, port=port)
                self._server.start()
                self.ipc_changed.emit(f"IPC · {host}:{port}")
            except Exception as exc:
                self.ipc_changed.emit("IPC недоступен")
                self.error_message.emit(f"Не удалось запустить IPC: {exc}")
        try:
            from core.wake_word import WakeWordListener
            self._listener = WakeWordListener(self._pipeline, on_state=self._wake_event)
            self._listener.start()
            self._pipeline.set_wake_listener(self._listener)
            # In this UI the user explicitly starts work with the button.
            if self._standby_requested:
                self._listener.enable()
            self.standby_available.emit(True)
            self.standby_changed.emit(self._listener.is_enabled)
        except Exception as exc:
            self.standby_available.emit(False)
            self.error_message.emit(f"Голосовая активация недоступна: {exc}")
        try:
            self._list_models()
        except Exception as exc:
            self.error_message.emit(f"Не удалось получить модели: {exc}")

    def _idle(self) -> None:
        enabled = bool(self._listener and self._listener.is_enabled)
        self.standby_changed.emit(enabled)
        self.state_changed.emit("standby_idle" if enabled else "idle", None)

    def _execute(self, name: str, argument) -> None:
        pipeline = self._pipeline
        if name == "turn":
            self.turn_result.emit(pipeline.process_voice_input(
                on_stage=lambda stage: self.state_changed.emit(stage, None)))
        elif name == "recalibrate":
            self.state_changed.emit("calibrating", None)
            pipeline.recalibrate()
        elif name == "models":
            self._list_models()
        elif name == "model":
            self.state_changed.emit("warming", argument)
            pipeline.set_llm_model(argument)
            pipeline.warmup_llm()
            self._list_models()
        elif name == "health":
            self.health_update.emit(pipeline.health_check())
        elif name in {"audio_device", "audio_sync"}:
            self._change_audio_device(argument if name == "audio_device" else None)

    def _list_models(self) -> None:
        current = getattr(getattr(self._pipeline, "_llm", None), "model", None)
        self.models_list.emit(self._pipeline.list_llm_models(), current)

    def _start_monitor(self, target, name: str) -> None:
        thread = threading.Thread(target=target, name=name, daemon=True)
        self._monitors.append(thread)
        thread.start()

    def _restore_audio_devices(self) -> None:
        from system.audio_devices import default_endpoints

        for direction, endpoint_id in self._audio_preferences.items():
            if not endpoint_id:
                continue
            try:
                self._audio_service.switch(direction, endpoint_id,
                                           lambda snapshot: self._pipeline.configure_audio_devices(default_endpoints(snapshot)))
            except Exception as exc:
                self.error_message.emit(f"Не удалось восстановить аудиоустройство: {exc}. Использую defaults Windows.")
        self._pipeline.configure_audio_devices(default_endpoints(self._audio_service.snapshot()))

    def _emit_audio_snapshot(self, snapshot: dict) -> None:
        self.audio_devices_update.emit({**snapshot, "active": self._pipeline.audio_devices,
                                        "stream_running": self._pipeline.stream.is_running})

    def _monitor_audio(self) -> None:
        from system.audio_devices import default_endpoints

        last_error = None
        while not self._closing.is_set():
            try:
                snapshot = self._audio_service.snapshot()
                self._emit_audio_snapshot(snapshot)
                target = default_endpoints(snapshot)
                if (target != self._pipeline.audio_devices or not self._pipeline.stream.is_running):
                    if (target != self._failed_audio_target and not self._audio_sync_pending.is_set()
                            and not self._closing.is_set()):
                        self._audio_sync_pending.set()
                        self._jobs.put(("audio_sync", None))
                last_error = None
            except Exception as exc:
                if str(exc) != last_error:
                    self.error_message.emit(f"Не удалось обновить аудиоустройства: {exc}")
                    last_error = str(exc)
            self._audio_poll.wait(2.0)
            self._audio_poll.clear()

    def _monitor_gpu(self) -> None:
        monitor = self._gpu_monitor_factory()
        try:
            while not self._closing.is_set():
                try:
                    self.gpu_update.emit(monitor.snapshot())
                except Exception:
                    self.gpu_update.emit({"devices": [], "error": "Мониторинг недоступен"})
                try:
                    self.model_update.emit(self._pipeline.model_status())
                except Exception:
                    logger.debug("Transient model metadata error", exc_info=True)
                self._closing.wait(1.0)
        finally:
            try:
                monitor.close()
            except Exception:
                logger.exception("GPU monitor cleanup failed")

    def _change_audio_device(self, selection) -> None:
        from system.audio_devices import default_endpoints

        pipeline = self._pipeline
        with self._submission_lock:
            if selection is None and self._operation_pending.is_set():
                return  # A foreground job is queued; retry after it completes.
            self._operation_pending.set()
        listener = self._listener
        enabled = bool(listener and listener.is_enabled)
        self.state_changed.emit("switching_audio", None)
        try:
            if listener:
                listener.disable()
            with pipeline.lock:
                def bind(snapshot):
                    pipeline.configure_audio_devices(default_endpoints(snapshot))

                if selection is not None:
                    direction, endpoint_id = selection
                    snapshot = self._audio_service.switch(direction, endpoint_id, bind)
                    self._audio_preferences[direction] = endpoint_id
                    self.audio_device_selected.emit(direction, endpoint_id)
                else:
                    snapshot = self._audio_service.snapshot()
                    target = default_endpoints(snapshot)
                    try:
                        bind(snapshot)
                    except Exception:
                        self._failed_audio_target = target
                        raise
                self._failed_audio_target = None
                self._emit_audio_snapshot(snapshot)
        finally:
            try:
                if (enabled and self._standby_requested and listener
                        and pipeline.stream.is_running and not self._closing.is_set()):
                    listener.enable()
            finally:
                self._audio_poll.set()
                if selection is None:
                    self._operation_pending.clear()
                    self._idle()

    def _wake_event(self, name: str, payload) -> None:
        if name == "standby_idle" and not (self._listener and self._listener.is_enabled):
            name = "idle"
        if name == "turn_result":
            self.turn_result.emit(payload)
        else:
            # A wake scan finishing while a manual job is queued must not
            # re-enable buttons or replace the manual job's progress status.
            if not self._operation_pending.is_set():
                self.state_changed.emit("idle" if name == "wake_disabled" else name, payload)
            if name in {"idle", "wake_disabled", "standby_idle"}:
                self.standby_changed.emit(name == "standby_idle")

    def _ui_event(self, name: str, payload) -> None:
        if name == "screenshot_taken" and isinstance(payload, dict):
            self.screenshot_taken.emit(payload.get("png"))
        elif name == "note_warning" and isinstance(payload, dict):
            self.error_message.emit(str(payload.get("message", "Ошибка сохранения заметки.")))

    @Slot()
    def _request_health(self) -> None:
        if not self._health_pending and not self._closing.is_set():
            self._health_pending = True
            self._submit("health")

    @Slot()
    def _clear_health_pending(self) -> None:
        self._health_pending = False

    @Slot(bool)
    def _speech_level_timer(self, busy: bool) -> None:
        if self._closing.is_set():
            return
        # Queued completion may arrive after the next speech job has started.
        if self.speech.busy:
            self._level_timer.start()
        elif self._pipeline is None:
            self._level_timer.stop()
            self.level_update.emit(0.0, 0)

    @Slot()
    def _poll_level(self) -> None:
        stream = getattr(self._pipeline, "stream", None)
        if stream is None and self.speech._runtime is not None:
            stream = self.speech._runtime._stream
        if stream is None or not stream.is_running:
            return
        latest = None
        try:
            for _ in range(256):
                latest = stream.level_queue.get_nowait()
        except queue.Empty:
            pass
        if latest is not None:
            self.level_update.emit(float(latest[0]), int(latest[1]))
