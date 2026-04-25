"""Мост между ``main.VoicePipeline`` и Qt-UI.

Контракт:

* UI зовёт **слоты** ``PipelineBridge.start_pipeline()``,
  ``request_turn()``, ``request_recalibrate()``, ``request_list_models()``,
  ``request_set_model(name)``, ``request_toggle_standby()``,
  ``request_cancel()``, ``shutdown()``.
* Бридж эмитит **сигналы** ``state_changed``, ``turn_result``,
  ``level_update``, ``health_update``, ``models_list``, ``model_applied``,
  ``model_error``, ``ipc_changed``, ``ready``, ``fatal``.

Тяжёлая работа (создание pipeline, turn-операции, recalibrate, прогрев LLM)
выполняется в выделенном :class:`QThread`, чтобы UI-поток оставался
отзывчивым. Сигналы Qt автоматически маршалятся в UI-поток.

Уровень микрофона и health опрашиваются на :class:`QTimer` в UI-потоке —
``stream.level_queue`` это ``queue.Queue``, потокобезопасна. Health-вызов
выносится в worker, чтобы сетевой timeout не блокировал UI.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from config import IPC_HOST, IPC_PORT, WAKE_WORD_ENABLED_AT_STARTUP

logger = logging.getLogger(__name__)


class _Worker(QThread):
    """Поток-владелец :class:`VoicePipeline`. Выполняет init/turn/recalibrate/...

    Все сигналы наружу — через :class:`PipelineBridge`, чтобы UI подписывался
    на стабильный QObject (worker пересоздаётся при рестарте).
    """

    def __init__(self, bridge: "PipelineBridge") -> None:
        super().__init__()
        self._bridge = bridge
        self._job_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._stop = False

    def submit(self, job: str, payload: Any = None) -> None:
        self._job_queue.put((job, payload))

    def run(self) -> None:  # noqa: C901 — несколько простых веток
        # Ленивый импорт — Qt-окно успевает отрисоваться раньше, чем Whisper/TTS
        # подтянут зависимости при создании VoicePipeline.
        from main import VoicePipeline

        bridge = self._bridge
        while not self._stop:
            try:
                job, arg = self._job_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                if job == "init":
                    self._do_init(VoicePipeline)
                elif job == "turn":
                    self._do_turn()
                elif job == "recalibrate":
                    self._do_recalibrate()
                elif job == "list_models":
                    self._do_list_models()
                elif job == "set_model":
                    self._do_set_model(str(arg))
                elif job == "health":
                    self._do_health()
                elif job == "stop":
                    self._do_stop()
                    return
                else:
                    logger.warning("PipelineBridge worker: unknown job %r", job)
            except Exception as exc:
                logger.exception("PipelineBridge worker: job %r failed", job)
                bridge._error_str.emit(f"{job}: {exc}")

    # ---- jobs -------------------------------------------------------------

    def _do_init(self, pipeline_cls: type) -> None:
        bridge = self._bridge
        bridge._state_emit.emit("starting", "создаю компоненты")
        try:
            pipeline = pipeline_cls()

            def _on_init_stage(name: str, payload: object) -> None:
                if name == "calibrating":
                    bridge._state_emit.emit("calibrating", f"молчите {payload:.0f}с…")
                elif name == "loading_stt":
                    bridge._state_emit.emit("starting", "загружаю Whisper…")
                elif name == "loading_tts":
                    bridge._state_emit.emit("starting", "загружаю TTS…")

            pipeline.start(on_stage=_on_init_stage)
        except Exception as exc:
            logger.exception("Pipeline init failed")
            bridge.fatal.emit(f"init: {exc}")
            return

        bridge._set_pipeline(pipeline)

        # UI-callback для команд: pipeline дёргает его из worker-потока,
        # bridge переадресовывает в Qt-сигнал (auto-marshal в UI-поток).
        pipeline.set_ui_callback(bridge._on_ui_event)

        # IPC server (как в Tkinter — best-effort, не валит UI).
        if bridge._with_ipc:
            try:
                from ipc.server import VoiceAIServer
                server = VoiceAIServer(
                    pipeline, host=bridge._ipc_host, port=bridge._ipc_port
                )
                server.start()
                bridge._ipc_server = server
                bridge.ipc_changed.emit(True)
            except Exception as exc:
                logger.warning("IPC server failed to start: %s", exc)
                bridge.ipc_changed.emit(False)
        else:
            bridge.ipc_changed.emit(None)

        # Wake-word listener.
        try:
            from core.wake_word import WakeWordListener

            def _on_wake_event(state: str, payload: object) -> None:
                if state == "turn_result":
                    bridge.turn_result.emit(payload)
                else:
                    detail = payload if isinstance(payload, str) and payload else None
                    bridge._state_emit.emit(state, detail)

            listener = WakeWordListener(pipeline, on_state=_on_wake_event)
            listener.start()
            if WAKE_WORD_ENABLED_AT_STARTUP:
                listener.enable()
            bridge._wake_listener = listener
            pipeline.set_wake_listener(listener)
        except Exception as exc:
            logger.exception("WakeWordListener init failed")
            bridge._error_str.emit(f"wake-word: {exc}")

        # Стартовый список моделей — комбобокс пользователя должен сразу что-то
        # показывать.
        try:
            current = getattr(pipeline._llm, "model", None)  # noqa: SLF001
        except Exception:
            current = None
        try:
            bridge.models_list.emit(pipeline.list_llm_models(), current)
        except Exception:
            logger.exception("list_llm_models on init failed")

        bridge._state_emit.emit("idle", None)
        bridge.ready.emit()

    def _do_turn(self) -> None:
        bridge = self._bridge
        pipeline = bridge._pipeline
        if pipeline is None:
            return

        def on_stage(stage: str) -> None:
            bridge._state_emit.emit(stage, None)

        result = pipeline.process_voice_input(on_stage=on_stage)
        bridge.turn_result.emit(result)
        bridge._state_emit.emit("idle", None)

    def _do_recalibrate(self) -> None:
        bridge = self._bridge
        pipeline = bridge._pipeline
        if pipeline is None:
            return
        bridge._state_emit.emit("calibrating", None)
        try:
            pipeline.recalibrate()
        finally:
            bridge._state_emit.emit("idle", None)

    def _do_list_models(self) -> None:
        bridge = self._bridge
        pipeline = bridge._pipeline
        if pipeline is None:
            return
        models = pipeline.list_llm_models()
        try:
            current = getattr(pipeline._llm, "model", None)  # noqa: SLF001
        except Exception:
            current = None
        bridge.models_list.emit(models, current)

    def _do_set_model(self, name: str) -> None:
        bridge = self._bridge
        pipeline = bridge._pipeline
        if pipeline is None or not name:
            return
        try:
            pipeline.set_llm_model(name)
        except Exception as exc:
            bridge.model_error.emit(f"{name}: {exc}")
            return

        bridge._state_emit.emit("warming", name)
        try:
            info = pipeline.warmup_llm()
        except Exception as exc:
            bridge._state_emit.emit("idle", None)
            bridge.model_error.emit(f"{name}: прогрев не удался — {exc}")
            return
        bridge._state_emit.emit("idle", None)
        bridge.model_applied.emit(
            name,
            float(info.get("elapsed_s", 0.0) or 0.0),
            bool(info.get("thinking_detected", False)),
        )

    def _do_health(self) -> None:
        bridge = self._bridge
        pipeline = bridge._pipeline
        if pipeline is None:
            return
        try:
            snap = pipeline.health_check()
        except Exception:
            logger.exception("health_check raised")
            return
        bridge.health_update.emit(snap)

    def _do_stop(self) -> None:
        bridge = self._bridge
        try:
            if bridge._wake_listener is not None:
                bridge._wake_listener.stop()
        except Exception:
            logger.exception("wake listener stop failed")
        try:
            if bridge._ipc_server is not None:
                bridge._ipc_server.stop()
        except Exception:
            logger.exception("IPC server stop failed")
        try:
            if bridge._pipeline is not None:
                bridge._pipeline.stop()
        except Exception:
            logger.exception("pipeline.stop() raised")
        self._stop = True
        bridge.stopped.emit()


class PipelineBridge(QObject):
    """Qt-фасад над :class:`VoicePipeline`. Создаётся в UI-потоке."""

    # core signals
    state_changed = Signal(str, object)
    turn_result = Signal(object)
    health_update = Signal(dict)
    level_update = Signal(float, int)

    # auxiliary signals
    models_list = Signal(object, object)        # (list[str], current_or_None)
    model_applied = Signal(str, float, bool)    # (name, elapsed_s, thinking)
    model_error = Signal(str)
    ipc_changed = Signal(object)                # bool|None
    screenshot_taken = Signal(object)           # PNG-байты (Signal(object) для безопасной кросс-потоковой доставки)
    ready = Signal()
    fatal = Signal(str)
    stopped = Signal()
    error_message = Signal(str)

    # Private signals — emitted from worker thread, re-emitted on UI thread
    # to keep state_changed/error single-source-of-truth and decouple worker
    # from the public Signal contract.
    _state_emit = Signal(str, object)
    _error_str = Signal(str)

    LEVEL_POLL_MS = 75
    HEALTH_POLL_MS = 5000

    def __init__(
        self,
        *,
        with_ipc: bool = True,
        ipc_host: str = IPC_HOST,
        ipc_port: int = IPC_PORT,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._with_ipc = with_ipc
        self._ipc_host = ipc_host
        self._ipc_port = ipc_port

        self._pipeline: Any | None = None
        self._ipc_server: Any | None = None
        self._wake_listener: Any | None = None
        self._pipeline_lock = threading.Lock()

        self._worker = _Worker(self)
        self._worker.start()

        # Пробрасываем приватные сигналы на публичные (одно место маршалинга).
        self._state_emit.connect(self.state_changed)
        self._error_str.connect(self.error_message)

        self._level_timer = QTimer(self)
        self._level_timer.setInterval(self.LEVEL_POLL_MS)
        self._level_timer.timeout.connect(self._poll_level)

        self._health_timer = QTimer(self)
        self._health_timer.setInterval(self.HEALTH_POLL_MS)
        self._health_timer.timeout.connect(lambda: self._worker.submit("health"))

    # ---- public API for the UI -------------------------------------------

    @property
    def pipeline(self) -> Any | None:
        return self._pipeline

    @property
    def wake_listener(self) -> Any | None:
        return self._wake_listener

    @Slot()
    def start_pipeline(self) -> None:
        """Старт фоновой инициализации pipeline."""
        self._worker.submit("init")

    @Slot()
    def request_turn(self) -> None:
        if self._pipeline is None:
            return
        self._worker.submit("turn")

    @Slot()
    def request_recalibrate(self) -> None:
        if self._pipeline is None:
            return
        self._worker.submit("recalibrate")

    @Slot()
    def request_list_models(self) -> None:
        if self._pipeline is None:
            return
        self._worker.submit("list_models")

    @Slot(str)
    def request_set_model(self, name: str) -> None:
        if self._pipeline is None or not name:
            return
        self._worker.submit("set_model", name)

    @Slot()
    def request_cancel(self) -> None:
        if self._pipeline is None:
            return
        try:
            self._pipeline.request_cancel()
        except Exception:
            logger.exception("request_cancel failed")

    @Slot(bool)
    def request_toggle_standby(self, enable: bool) -> None:
        listener = self._wake_listener
        if listener is None:
            return
        if enable and not listener.is_enabled:
            listener.enable()
        elif not enable and listener.is_enabled:
            listener.disable()

    @Slot()
    def shutdown(self) -> None:
        """Аккуратно остановить таймеры, worker и pipeline."""
        try:
            self._level_timer.stop()
            self._health_timer.stop()
        except Exception:
            pass
        self._worker.submit("stop")
        # Worker сам выйдет из run(); ждём до 5с — pipeline.stop() на GPU
        # бывает медленным.
        if not self._worker.wait(5000):
            logger.warning("PipelineBridge worker did not exit in 5s")

    # ---- internals --------------------------------------------------------

    def _set_pipeline(self, pipeline: Any) -> None:
        with self._pipeline_lock:
            self._pipeline = pipeline
        # Таймеры стартуют как только есть pipeline — VAD/level уже работают.
        self._level_timer.start()
        self._health_timer.start()

    def _on_ui_event(self, kind: str, payload: object) -> None:
        """Принимает события от команд (вызывается из worker-потока).
        Маршрутизирует в Qt-сигналы — Qt сам переключит на UI-поток."""
        logger.info("PipelineBridge._on_ui_event: kind=%r", kind)
        try:
            if kind == "screenshot_taken":
                png = payload.get("png") if isinstance(payload, dict) else None
                if isinstance(png, (bytes, bytearray)):
                    logger.info(
                        "PipelineBridge: emitting screenshot_taken (%d bytes)",
                        len(png),
                    )
                    self.screenshot_taken.emit(bytes(png))
                else:
                    logger.warning(
                        "PipelineBridge: screenshot_taken without png bytes (%r)",
                        type(png).__name__,
                    )
        except Exception:
            logger.exception("PipelineBridge._on_ui_event(%r) failed", kind)

    def _poll_level(self) -> None:
        pipeline = self._pipeline
        if pipeline is None:
            return
        stream = getattr(pipeline, "stream", None)
        if stream is None or not getattr(stream, "is_running", False):
            return
        last: tuple[float, int] | None = None
        try:
            while True:
                last = stream.level_queue.get_nowait()
        except queue.Empty:
            pass
        if last is None:
            return
        rms, percent = last
        self.level_update.emit(float(rms), int(percent))

    # ---- attach/detach (не используется на этапе 4, заглушка для совместимости)

    def attach(self, pipeline: Any) -> None:
        """Внешнее подключение уже созданного pipeline (используется в тестах)."""
        self._set_pipeline(pipeline)
