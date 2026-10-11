"""Independent speech jobs, sharing ownership and exclusion with the assistant."""

from __future__ import annotations

import logging
from pathlib import Path
import threading

from PySide6.QtCore import QObject, Signal

from core.speech_runtime import SpeechRuntime, atomic_export, check_cancel
from utils.errors import CancelledError

logger = logging.getLogger(__name__)


class SpeechToolsBackend(QObject):
    busy_changed = Signal(bool)
    status = Signal(str, str)
    text_ready = Signal(int, str, bool)
    progress = Signal(int, int)
    error = Signal(str, str)

    def __init__(self, owner, *, runtime_factory=SpeechRuntime) -> None:
        super().__init__(owner)
        self.owner = owner
        self._runtime_factory = runtime_factory
        self._runtime = None
        self._thread = None
        self._cancel = threading.Event()
        self._stop_capture = threading.Event()
        self._busy = False
        self._closing = False
        self.kind = ""
        self.job_id = 0
        self._cancelled_jobs: set[int] = set()
        self.resume_standby = False
        self._cached_text = None
        self._cached_wav = None

    @property
    def runtime(self):
        if self._runtime is None:
            self._runtime = self._runtime_factory()
        return self._runtime

    @property
    def busy(self):
        return self._busy

    def accepts_result(self, job_id: int) -> bool:
        return job_id <= self.job_id and job_id not in self._cancelled_jobs and not self._closing

    def transcribe_file(self, path: str) -> bool:
        if Path(path).suffix.lower() not in {".wav", ".flac"}:
            self.error.emit("stt", "Выберите аудиофайл WAV или FLAC")
            return False
        return self._submit("stt", "file", path)

    def start_dictation(self, external: bool = False) -> bool:
        return self._submit("stt", "dictation", external)

    def refresh_audio_devices(self) -> bool:
        return self._submit("stt", "audio_snapshot", None)

    def select_audio_device(self, direction: str, endpoint_id: str) -> bool:
        return self._submit("stt", "audio_device", (direction, endpoint_id))

    def _audio_service(self):
        if self.owner._audio_service is None:
            from system.audio_devices import WindowsAudioDevices
            self.owner._audio_service = WindowsAudioDevices()
        return self.owner._audio_service

    def _emit_audio_snapshot(self, snapshot):
        from system.audio_devices import default_endpoints

        active = default_endpoints(snapshot)
        for direction, preferred in self.owner._audio_preferences.items():
            active[direction] = next((device for device in snapshot[direction]["devices"]
                                      if device["id"] == preferred), active[direction])
        stream = self._runtime._stream if self._runtime is not None else None
        self.owner.audio_devices_update.emit({**snapshot, "active": active,
                                             "stream_running": bool(stream and stream.is_running),
                                             "standalone": True})

    def stop_dictation(self) -> None:
        self._stop_capture.set()
        if self.busy and self.kind == "stt":
            self.status.emit("stt", "Завершаю запись и распознавание…")

    def synthesize(self, text: str, *, play: bool = False, destination: str | None = None) -> bool:
        if not text.strip():
            self.error.emit("tts", "Введите текст для озвучки")
            return False
        return self._submit("tts", "tts", (text, play, destination))

    def save_text(self, text: str, destination: str) -> bool:
        return self._submit("stt", "save_text", (text, destination))

    def cancel(self) -> None:
        self._cancelled_jobs.add(self.job_id)
        self._cancel.set()
        self._stop_capture.set()

    def _submit(self, kind, operation, argument) -> bool:
        owner = self.owner
        with owner._submission_lock:
            if (self._busy or self._closing or owner._closing.is_set()
                    or owner._operation_pending.is_set() or owner._startup_started_at is not None):
                self.error.emit(kind, "Дождитесь завершения текущей операции")
                return False
            self._busy = True
            self.kind = kind
            self.job_id += 1
            self._cancel = threading.Event()
            self._stop_capture = threading.Event()
            owner._operation_pending.set()
            listener = owner._listener
            self.resume_standby = bool(listener and listener.is_enabled)
            if listener:
                listener.disable()
            self.busy_changed.emit(True)
            self.status.emit(kind, "Подготавливаю инструмент…")
            if kind == "tts":
                self.progress.emit(0, 1)
            self._thread = threading.Thread(target=self._run, args=(operation, argument, self.job_id),
                                            name="speech-tools", daemon=True)
            self._thread.start()
            return True

    def _configure_device(self, direction):
        # A running assistant already owns the selected endpoints. Standalone
        # tools resolve just the direction they need, so TTS needs no microphone.
        if self.owner._pipeline is not None:
            return
        from system.audio_devices import default_endpoints, resolve_wasapi_devices

        service = self._audio_service()
        snapshot = service.snapshot()
        self._emit_audio_snapshot(snapshot)
        endpoint = default_endpoints(snapshot).get(direction)
        preferred = self.owner._audio_preferences.get(direction)
        if preferred:
            endpoint = next((device for device in snapshot[direction]["devices"]
                             if device["id"] == preferred), endpoint)
        if endpoint is None:
            raise RuntimeError("Нет активного микрофона" if direction == "input" else "Нет устройства воспроизведения")
        indices = resolve_wasapi_devices({direction: endpoint}, refresh=True)
        device = self.runtime.stream if direction == "input" else self.runtime.player
        device.set_device(indices[direction])

    def _run(self, operation, argument, job_id):
        owner = self.owner
        stage = lambda message: self.status.emit(self.kind, message)
        try:
            if operation == "audio_snapshot":
                self._emit_audio_snapshot(self._audio_service().snapshot())
                stage("Список аудиоустройств обновлён")
                return
            # A wake turn / IPC operation may already own the runtime; do not
            # clear its cancellation or touch its resources while waiting.
            runtime = self.runtime
            with runtime.operation(self._cancel):
                check_cancel(self._cancel)
                if operation == "audio_device":
                    from system.audio_devices import default_endpoints, resolve_wasapi_devices

                    direction, endpoint_id = argument
                    def bind(snapshot):
                        endpoint = default_endpoints(snapshot)[direction]
                        indices = resolve_wasapi_devices({direction: endpoint}, refresh=True)
                        device = runtime.stream if direction == "input" else runtime.player
                        device.set_device(indices[direction])

                    snapshot = self._audio_service().switch(direction, endpoint_id, bind)
                    owner._audio_preferences[direction] = endpoint_id
                    owner.audio_device_selected.emit(direction, endpoint_id)
                    self._emit_audio_snapshot(snapshot)
                elif operation == "file":
                    text = runtime.transcribe(argument, self._cancel, stage)
                    if text:
                        self.text_ready.emit(job_id, text, False)
                    else:
                        stage("Речь не обнаружена")
                        return
                elif operation == "dictation":
                    from core.dictation import dictate
                    self._configure_device("input")
                    try:
                        dictate(runtime, self._stop_capture, self._cancel,
                                lambda text: self.text_ready.emit(job_id, text, argument), stage)
                    finally:
                        if owner._pipeline is None and runtime._stream is not None:
                            runtime._stream.stop()
                elif operation == "tts":
                    text, play, destination = argument
                    if text != self._cached_text or not self._cached_wav or not Path(self._cached_wav).exists():
                        wav = runtime.synthesize(text, self._cancel, stage, self.progress.emit)
                        if self._cached_wav:
                            Path(self._cached_wav).unlink(missing_ok=True)
                        self._cached_text, self._cached_wav = text, wav
                    check_cancel(self._cancel)
                    if destination:
                        stage("Сохраняю аудио…")
                        atomic_export(self._cached_wav, destination, self._cancel)
                    if play:
                        self._configure_device("output")
                        check_cancel(self._cancel)
                        stage("Озвучиваю…")
                        runtime.player.play_file(self._cached_wav, cancel_event=self._cancel)
                elif operation == "save_text":
                    text, destination = argument
                    temporary = runtime.workspace / "export.txt"
                    try:
                        temporary.write_text(text, encoding="utf-8")
                        atomic_export(temporary, destination, self._cancel)
                    finally:
                        temporary.unlink(missing_ok=True)
                check_cancel(self._cancel)
                stage("Сохранено" if operation == "save_text" or (operation == "tts" and argument[2]) else "Готово")
        except CancelledError:
            stage("Отменено")
        except Exception as exc:
            logger.exception("Speech tool failed: %s", operation)
            self.error.emit(self.kind, str(exc))
        finally:
            with owner._submission_lock:
                listener = owner._listener
                if (listener and self.resume_standby and owner._standby_requested
                        and not owner._closing.is_set() and not self._closing):
                    listener.enable()
                owner._operation_pending.clear()
                self._busy = False
                self.busy_changed.emit(False)
            if owner._pipeline is not None and not owner._closing.is_set():
                owner._idle()

    def begin_shutdown(self):
        self._closing = True
        self.cancel()

    def finish_shutdown(self):
        """Worker-only join; never blocks the GUI event loop."""
        self.begin_shutdown()
        if self._thread is not None:
            self._thread.join()
        if self._runtime is not None:
            self._runtime.close()

    def reopen_after_assistant_failure(self):
        """The assistant failed, but the independent tools remain usable."""
        self._cached_text = self._cached_wav = None
        self._thread = None
        self._closing = False
