"""Tkinter UI for the Voice AI Assistant (Stage 7).

Owns a :class:`main.VoicePipeline` and exposes:

  * main panel — "🎤 Слушай" / "🔄 Перекалибровать" buttons, recognized-text
    and LLM-reply text widgets, a big status bar that walks through
    Готов → Запись → Обработка → Воспроизведение
  * audio diagnostics — live RMS level bar with a blue noise-floor marker
    and a red threshold marker, plus numeric readouts (RMS / шум / порог)
  * service indicators — Whisper / LLM / TTS health pills, refreshed every
    few seconds via :meth:`VoicePipeline.health_check`
  * log viewer — last N lines captured from the root logger with an
    INFO/WARNING/ERROR filter

Threading model:

* UI runs in the main thread
* one background worker thread (``UIWorker``) owns the pipeline — does init,
  runs turns, handles recalibrate/stop
* a separate health-poll thread (``UIHealth``) calls ``pipeline.health_check``
  every ``HEALTH_INTERVAL_S`` seconds
* audio level bar pulls ``AudioStream.level_queue`` on a Tk ``after`` timer
  (never crosses threads — ``queue.Queue`` is safe either way)
* a custom ``logging.Handler`` pushes formatted records into a bounded queue
  which the UI drains on another ``after`` timer

The UI never blocks on pipeline work — buttons submit a job to the worker
queue and wait for a notification back. This keeps ``Ctrl+C`` and "move the
window" working even while Whisper is transcribing.
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk
from typing import Any

from bootstrap import bootstrap
from config import IPC_HOST, IPC_PORT, WAKE_WORD, WAKE_WORD_ENABLED_AT_STARTUP

logger = logging.getLogger(__name__)


# ---- state labels ----------------------------------------------------------

# Single source of truth for the status bar. Keep the icon column one code
# point wide so the layout doesn't jitter when the status changes.
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
    # Дежурный режим (wake-word).
    "standby_idle":     ("🛌", "Дежурный: жду «{wake}»"),
    "wake_heard":       ("👂", "Услышал — подождите"),
    "wake_active":      ("🎙", "Слушаю вопрос"),
    "wake_processing":  ("🧠", "Обработка (дежурный)"),
}

_INT16_PER_PERCENT = 327.67  # mirrors AudioStream._INT16_PER_PERCENT


# ---- log handler -----------------------------------------------------------


class _UILogHandler(logging.Handler):
    """Ship formatted records into a bounded queue for the UI log viewer."""

    _FMT = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    def __init__(self, sink: queue.Queue[tuple[int, str]]) -> None:
        super().__init__()
        self._sink = sink
        self.setFormatter(self._FMT)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
        except Exception:
            # If formatting itself fails we don't want to crash the app.
            return
        try:
            self._sink.put_nowait((record.levelno, line))
        except queue.Full:
            # Drop oldest, push newest — the viewer only cares about recency.
            try:
                self._sink.get_nowait()
                self._sink.put_nowait((record.levelno, line))
            except queue.Empty:
                pass


# ---- the app ---------------------------------------------------------------


class VoiceAIApp:
    """Tk app shell — see module docstring for threading contract."""

    POLL_UI_MS = 50           # how often to drain worker → UI messages
    POLL_LEVEL_MS = 75        # how often to refresh the RMS level bar
    POLL_LOG_MS = 200         # how often to refresh the log viewer
    HEALTH_INTERVAL_S = 5.0   # how often to poll pipeline.health_check
    MAX_LOG_LINES = 200       # cap the log viewer history

    def __init__(
        self,
        root: tk.Tk,
        *,
        with_ipc: bool = True,
        ipc_host: str = IPC_HOST,
        ipc_port: int = IPC_PORT,
    ) -> None:
        self._root = root
        self._with_ipc = with_ipc
        self._ipc_host = ipc_host
        self._ipc_port = ipc_port

        # Pipeline + IPC server are created by the worker thread during init;
        # UI code only reads them through the accessors once ready.
        self._pipeline: Any = None
        self._ipc_server: Any = None
        # Wake-word listener (Stage 8). Created after pipeline.start().
        self._wake_listener: Any = None
        self._ready = False
        self._stopped = False
        self._shutdown_started = False
        self._worker_done = False
        self._shutdown_deadline_ticks = 0

        # Worker → UI event stream. Each item is (kind, payload).
        self._ui_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=200)
        # UI → worker job stream. Each item is (job, payload).
        self._job_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        # Log handler sink.
        self._log_queue: queue.Queue[tuple[int, str]] = queue.Queue(maxsize=500)
        # Log buffer (after filtering) for redraws.
        self._log_lines: list[tuple[int, str]] = []

        # Audio diagnostics state (updated from level_queue + health/VAD).
        self._current_rms = 0.0
        self._current_percent = 0
        self._noise_rms = 0.0
        self._threshold = 0.0

        self._log_filter_var = tk.StringVar(value="ALL")
        self._model_var = tk.StringVar(value="")

        self._build_ui()
        self._attach_log_handler()

        # Worker thread: owns the pipeline, runs all heavy work.
        self._worker = threading.Thread(
            target=self._worker_loop, name="UIWorker", daemon=True
        )
        self._worker.start()

        # Health polling thread — reads pipeline state periodically.
        self._health_stop = threading.Event()
        self._health = threading.Thread(
            target=self._health_loop, name="UIHealth", daemon=True
        )
        self._health.start()

        # Kick off the init job immediately.
        self._job_queue.put(("init", None))

        # Tk polling loops.
        self._root.after(self.POLL_UI_MS, self._drain_ui_queue)
        self._root.after(self.POLL_LEVEL_MS, self._poll_levels)
        self._root.after(self.POLL_LOG_MS, self._drain_log_queue)

        self._log_filter_var.trace_add(
            "write", lambda *_: self._refresh_log_text()
        )

    # ---- UI construction --------------------------------------------------

    def _build_ui(self) -> None:
        self._root.title("Voice AI — Shura v2")
        self._root.geometry("780x720")
        self._root.minsize(640, 520)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Status bar (top).
        top = ttk.Frame(self._root, padding=(10, 8))
        top.pack(fill="x")
        self._status_icon = ttk.Label(
            top, text="⚙", font=("Segoe UI Emoji", 18)
        )
        self._status_icon.pack(side="left")
        self._status_text = ttk.Label(
            top, text="Инициализация…", font=("Segoe UI", 12, "bold")
        )
        self._status_text.pack(side="left", padx=10)

        btns = ttk.Frame(top)
        btns.pack(side="right")
        self._listen_btn = ttk.Button(
            btns, text="🎤 Слушай", command=self._on_listen, width=14
        )
        self._listen_btn.pack(side="left", padx=4)
        self._standby_btn = ttk.Button(
            btns,
            text="🛌 Дежурный: выкл",
            command=self._on_toggle_standby,
            width=20,
        )
        self._standby_btn.pack(side="left", padx=4)
        self._recal_btn = ttk.Button(
            btns, text="🔄 Перекалибровать", command=self._on_recalibrate, width=20
        )
        self._recal_btn.pack(side="left", padx=4)

        # LLM model selector.
        mdl = ttk.LabelFrame(self._root, text="LLM модель", padding=8)
        mdl.pack(fill="x", padx=10, pady=4)
        ttk.Label(mdl, text="Модель:").pack(side="left")
        self._model_combo = ttk.Combobox(
            mdl,
            textvariable=self._model_var,
            state="readonly",
            width=40,
        )
        self._model_combo.pack(side="left", padx=(6, 8), fill="x", expand=True)
        self._refresh_models_btn = ttk.Button(
            mdl, text="🔄 Обновить", command=self._on_refresh_models, width=12
        )
        self._refresh_models_btn.pack(side="left", padx=4)
        self._apply_model_btn = ttk.Button(
            mdl, text="Применить", command=self._on_apply_model, width=12
        )
        self._apply_model_btn.pack(side="left", padx=4)
        self._model_status = ttk.Label(mdl, text="(не загружено)", foreground="#777")
        self._model_status.pack(side="left", padx=(8, 0))

        # Audio diagnostics.
        diag = ttk.LabelFrame(self._root, text="Диагностика аудио", padding=8)
        diag.pack(fill="x", padx=10, pady=4)
        self._level_canvas = tk.Canvas(
            diag, height=44, bg="#1b1b1b", highlightthickness=0
        )
        self._level_canvas.pack(fill="x")
        self._level_info = ttk.Label(
            diag,
            text="RMS: —   Шум: —   Порог: —",
            font=("Consolas", 10),
        )
        self._level_info.pack(anchor="w", pady=(6, 0))

        svc = ttk.Frame(diag)
        svc.pack(anchor="w", pady=(4, 0))
        self._svc_whisper = ttk.Label(svc, text="🟡 Whisper")
        self._svc_whisper.pack(side="left", padx=(0, 12))
        self._svc_llm = ttk.Label(svc, text="🟡 LLM")
        self._svc_llm.pack(side="left", padx=(0, 12))
        self._svc_tts = ttk.Label(svc, text="🟡 TTS")
        self._svc_tts.pack(side="left", padx=(0, 12))
        self._svc_ipc = ttk.Label(svc, text="🟡 IPC")
        self._svc_ipc.pack(side="left")

        # Transcript panels.
        dlg = ttk.LabelFrame(self._root, text="Диалог", padding=8)
        dlg.pack(fill="both", expand=True, padx=10, pady=4)

        ttk.Label(dlg, text="Вы:").pack(anchor="w")
        self._user_text = scrolledtext.ScrolledText(
            dlg, height=3, wrap="word", font=("Segoe UI", 10)
        )
        self._user_text.pack(fill="x")

        ttk.Label(dlg, text="Ассистент:").pack(anchor="w", pady=(6, 0))
        self._llm_text = scrolledtext.ScrolledText(
            dlg, height=4, wrap="word", font=("Segoe UI", 10)
        )
        self._llm_text.pack(fill="x")

        # Per-stage timing readouts.
        stats = ttk.Frame(dlg)
        stats.pack(fill="x", pady=(6, 0))
        ttk.Label(stats, text="Статистика оборота:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self._stats_stt = ttk.Label(
            stats, text="🎤 Распознавание: —", font=("Consolas", 10)
        )
        self._stats_stt.pack(anchor="w")
        self._stats_llm = ttk.Label(
            stats, text="🧠 LLM: —", font=("Consolas", 10)
        )
        self._stats_llm.pack(anchor="w")
        self._stats_tts = ttk.Label(
            stats, text="🔊 Синтез: —", font=("Consolas", 10)
        )
        self._stats_tts.pack(anchor="w")
        self._stats_total = ttk.Label(
            stats, text="⏱ Итого: —", font=("Consolas", 10, "bold")
        )
        self._stats_total.pack(anchor="w")

        # Log viewer.
        logs = ttk.LabelFrame(self._root, text="Логи", padding=8)
        logs.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        filter_row = ttk.Frame(logs)
        filter_row.pack(anchor="w")
        ttk.Label(filter_row, text="Уровень: ").pack(side="left")
        for lvl in ("ALL", "INFO", "WARNING", "ERROR"):
            ttk.Radiobutton(
                filter_row,
                text=lvl,
                variable=self._log_filter_var,
                value=lvl,
            ).pack(side="left")

        self._log_text = scrolledtext.ScrolledText(
            logs,
            height=10,
            wrap="none",
            font=("Consolas", 9),
        )
        self._log_text.pack(fill="both", expand=True, pady=(6, 0))
        self._log_text.configure(state="disabled")

        self._set_controls_enabled(False)

    # ---- log handler plumbing --------------------------------------------

    def _attach_log_handler(self) -> None:
        handler = _UILogHandler(self._log_queue)
        handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)
        self._log_handler = handler

    def _detach_log_handler(self) -> None:
        handler = getattr(self, "_log_handler", None)
        if handler is not None:
            logging.getLogger().removeHandler(handler)

    # ---- button handlers --------------------------------------------------

    def _on_listen(self) -> None:
        if not self._ready:
            return
        # Drop the click if we're already mid-cycle; worker queue would
        # serialize anyway but an accidental double-click would queue a second
        # turn the user didn't ask for. "standby_idle" is allowed — manual
        # button is the documented fallback even while the listener runs.
        if self._current_state() not in ("idle", "standby_idle"):
            return
        self._job_queue.put(("turn", None))

    def _on_recalibrate(self) -> None:
        if not self._ready:
            return
        if self._current_state() not in ("idle", "standby_idle"):
            return
        self._job_queue.put(("recalibrate", None))

    def _on_toggle_standby(self) -> None:
        if not self._ready or self._wake_listener is None:
            return
        # Flip directly on the UI thread — enable()/disable() just flip a
        # threading.Event, no heavy work. The listener thread picks it up
        # on its next loop iteration.
        if self._wake_listener.is_enabled:
            self._wake_listener.disable()
            self._standby_btn.configure(text="🛌 Дежурный: выкл")
        else:
            self._wake_listener.enable()
            self._standby_btn.configure(text="🛌 Дежурный: вкл")

    def _on_refresh_models(self) -> None:
        if not self._ready:
            return
        self._model_status.configure(text="обновляю…", foreground="#777")
        self._job_queue.put(("list_models", None))

    def _on_apply_model(self) -> None:
        if not self._ready:
            return
        name = self._model_var.get().strip()
        if not name:
            self._model_status.configure(text="выберите модель", foreground="#c93f3f")
            return
        # Applying while a turn is running would wait on the lock anyway, but
        # the UX is clearer if we gate it the same way as the Listen button.
        # standby_idle допускаем — пользователь может поменять модель
        # с включённым дежурным режимом; pipeline.lock сериализует это
        # с циклом wake-word, так что подождём один scan window максимум.
        if self._current_state() not in ("idle", "standby_idle"):
            return
        self._model_status.configure(text=f"применяю «{name}»…", foreground="#777")
        self._job_queue.put(("set_model", name))

    def _on_close(self) -> None:
        # Hand teardown to the worker so the UI thread stays responsive:
        # pipeline.stop() joins the mic thread (2s) and unloads GPU models
        # (bounded, but can spike), which used to freeze the window for
        # several seconds after the close button was clicked. Now we just
        # flip to "stopping", post a stop job, and poll a deadline on the
        # UI thread — the window repaints normally in the meantime.
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._set_controls_enabled(False)
        self._set_state("stopping")
        self._health_stop.set()
        self._job_queue.put(("stop", None))
        # ~5s hard cap: if teardown hangs we destroy the window anyway and
        # let the daemon threads die with the process.
        self._shutdown_deadline_ticks = 50
        self._root.after(100, self._tick_shutdown)

    def _tick_shutdown(self) -> None:
        if self._worker_done or self._shutdown_deadline_ticks <= 0:
            self._stopped = True
            try:
                self._detach_log_handler()
            except Exception:
                pass
            try:
                self._root.destroy()
            except Exception:
                pass
            return
        self._shutdown_deadline_ticks -= 1
        self._root.after(100, self._tick_shutdown)

    # ---- worker -----------------------------------------------------------

    def _worker_loop(self) -> None:
        # Defer heavy imports to the worker so Tk starts fast and the user
        # sees the window before Whisper/Silero deps get pulled in.
        from main import VoicePipeline  # noqa: WPS433 — intentional lazy import

        while True:
            job, arg = self._job_queue.get()
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
                    self._do_set_model(arg)
                elif job == "stop":
                    self._do_stop()
                    return
                else:
                    logger.warning("UI worker: unknown job %r", job)
            except Exception as exc:
                logger.exception("UI worker: job %r failed", job)
                self._post("error", f"{job}: {exc}")

    def _do_init(self, pipeline_cls: type) -> None:
        self._post("state", ("starting", "создаю компоненты"))
        try:
            self._pipeline = pipeline_cls()

            def _on_init_stage(name: str, payload: object) -> None:
                if name == "calibrating":
                    # Kick off a countdown in the UI thread. payload = seconds.
                    self._post("cal_countdown_start", float(payload or 2.0))
                elif name == "loading_stt":
                    self._post("state", ("starting", "загружаю Whisper…"))
                elif name == "loading_tts":
                    self._post("state", ("starting", "загружаю TTS…"))

            self._pipeline.start(on_stage=_on_init_stage)
        except Exception as exc:
            logger.exception("Pipeline init failed")
            self._post("fatal", f"init: {exc}")
            return

        # Optional IPC server — same as console mode: don't kill the UI if
        # the port's busy, just report it.
        if self._with_ipc:
            try:
                from ipc.server import VoiceAIServer
                server = VoiceAIServer(
                    self._pipeline, host=self._ipc_host, port=self._ipc_port
                )
                server.start()
                self._ipc_server = server
                self._post("ipc", True)
            except Exception as exc:
                logger.warning("IPC server failed to start: %s", exc)
                self._post("ipc", False)
        else:
            self._post("ipc", None)

        self._post("vad_refresh", None)
        # Prime the model list so the combobox has something in it as soon
        # as the user looks at it — no need to click Refresh first.
        try:
            current = getattr(self._pipeline._llm, "model", None)  # noqa: SLF001 — read-only peek
        except Exception:
            current = None
        self._post("models_list", (self._pipeline.list_llm_models(), current))

        # Wake-word listener — always spun up, toggled on by user (or by
        # WAKE_WORD_ENABLED_AT_STARTUP for power users).
        try:
            from core.wake_word import WakeWordListener
            listener = WakeWordListener(
                self._pipeline, on_state=self._on_wake_event
            )
            listener.start()
            if WAKE_WORD_ENABLED_AT_STARTUP:
                listener.enable()
            self._wake_listener = listener
        except Exception as exc:
            logger.exception("WakeWordListener init failed")
            self._post("error", f"wake-word: {exc}")

        self._post("state", ("idle", None))
        self._post("ready", None)

    def _on_wake_event(self, state: str, payload: object) -> None:
        """Callback from WakeWordListener thread. Posts to the UI queue."""
        if state == "turn_result":
            self._post("turn_result", payload)
            self._post("vad_refresh", None)
        else:
            # state ∈ {standby_idle, wake_heard, wake_active, wake_processing, idle}
            detail = None
            if isinstance(payload, str) and payload:
                detail = payload[:60]
            self._post("state", (state, detail))

    def _do_turn(self) -> None:
        assert self._pipeline is not None
        # The pipeline callback lets us walk the status bar through
        # listening → processing → speaking even though the call is blocking.
        def on_stage(stage: str) -> None:
            self._post("state", (stage, None))

        result = self._pipeline.process_voice_input(on_stage=on_stage)
        self._post("turn_result", result)
        self._post("vad_refresh", None)
        # If the turn failed with a spoken fallback we still land back on
        # idle — the error string shows up as a detail in the status bar
        # via the turn_result handler.
        self._post("state", ("idle", None))

    def _do_recalibrate(self) -> None:
        assert self._pipeline is not None
        self._post("state", ("calibrating", None))
        result = self._pipeline.recalibrate()
        self._post("recal_result", result)
        self._post("state", ("idle", None))

    def _do_list_models(self) -> None:
        assert self._pipeline is not None
        models = self._pipeline.list_llm_models()
        try:
            current = getattr(self._pipeline._llm, "model", None)  # noqa: SLF001
        except Exception:
            current = None
        self._post("models_list", (models, current))

    def _do_set_model(self, name: str) -> None:
        assert self._pipeline is not None
        # Step 1 — flip the internal variable. Instant.
        try:
            self._pipeline.set_llm_model(name)
        except Exception as exc:
            self._post("model_error", f"{name}: {exc}")
            return

        # Step 2 — force the backend to actually load the model. Without
        # this the load only happens on the user's next voice turn, which
        # looks like "Apply did nothing" because LM Studio stays silent
        # until the first real request. Big models can take minutes to
        # load from disk; we gate the status bar so the user sees progress.
        self._post("state", ("warming", name))
        self._post(
            "model_warming",
            f"прогреваю «{name}» в бэкенде (может занять минуту)…",
        )
        try:
            info = self._pipeline.warmup_llm()
        except Exception as exc:
            self._post("state", ("idle", None))
            self._post("model_error", f"{name}: прогрев не удался — {exc}")
            return
        self._post("state", ("idle", None))
        self._post(
            "model_applied",
            (
                name,
                float(info.get("elapsed_s", 0.0) or 0.0),
                bool(info.get("thinking_detected", False)),
            ),
        )

    def _do_stop(self) -> None:
        # Driven by _on_close via ("stop", None). Tears down everything the
        # worker owns so the UI thread never blocks on GPU cleanup or
        # socket joins. The UI polls for the "stopped" event with a
        # deadline so a hung backend can't keep the window open forever.
        try:
            if self._wake_listener is not None:
                self._wake_listener.stop()
        except Exception:
            logger.exception("wake listener stop failed")
        try:
            if self._ipc_server is not None:
                self._ipc_server.stop()
        except Exception:
            logger.exception("IPC server stop failed")
        try:
            if self._pipeline is not None:
                self._pipeline.stop()
        except Exception:
            logger.exception("pipeline.stop() raised")
        self._post("stopped", None)

    def _post(self, kind: str, payload: Any) -> None:
        """Put a message on the worker→UI queue, dropping oldest if full."""
        try:
            self._ui_queue.put_nowait((kind, payload))
        except queue.Full:
            try:
                self._ui_queue.get_nowait()
                self._ui_queue.put_nowait((kind, payload))
            except queue.Empty:
                pass

    # ---- health polling ---------------------------------------------------

    def _health_loop(self) -> None:
        # Intentionally loose — we don't want the UI dashboard to have its
        # own opinion about availability, we just mirror what the pipeline
        # reports. Polling from a dedicated thread keeps network timeouts
        # off the UI thread.
        while not self._health_stop.is_set():
            if self._pipeline is not None:
                try:
                    snapshot = self._pipeline.health_check()
                    self._post("health", snapshot)
                except Exception:
                    logger.exception("health_check raised")
            if self._health_stop.wait(self.HEALTH_INTERVAL_S):
                break

    # ---- Tk polling timers -----------------------------------------------

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                self._handle(kind, payload)
        except queue.Empty:
            pass
        if not self._stopped:
            self._root.after(self.POLL_UI_MS, self._drain_ui_queue)

    def _poll_levels(self) -> None:
        # Drain everything that's waiting — we only care about the most
        # recent (rms, percent) pair. The queue is bounded at 10 so there's
        # a hard upper bound on work per tick.
        if self._pipeline is not None:
            stream = self._pipeline.stream
            if stream.is_running:
                last: tuple[float, int] | None = None
                try:
                    while True:
                        last = stream.level_queue.get_nowait()
                except queue.Empty:
                    pass
                if last is not None:
                    self._current_rms, self._current_percent = last
        self._redraw_level_bar()
        if not self._stopped:
            self._root.after(self.POLL_LEVEL_MS, self._poll_levels)

    def _drain_log_queue(self) -> None:
        grew = False
        try:
            while True:
                lvl, line = self._log_queue.get_nowait()
                self._log_lines.append((lvl, line))
                grew = True
        except queue.Empty:
            pass
        if len(self._log_lines) > self.MAX_LOG_LINES:
            # Trim in one shot rather than popping per-line.
            self._log_lines = self._log_lines[-self.MAX_LOG_LINES:]
        if grew:
            self._refresh_log_text()
        if not self._stopped:
            self._root.after(self.POLL_LOG_MS, self._drain_log_queue)

    # ---- event handlers ---------------------------------------------------

    def _handle(self, kind: str, payload: Any) -> None:
        if kind == "state":
            name, detail = payload if isinstance(payload, tuple) else (payload, None)
            self._set_state(name, detail)
        elif kind == "ready":
            self._ready = True
            self._set_controls_enabled(True)
            # Sync the standby-toggle button text with the listener's actual
            # state (mostly relevant when WAKE_WORD_ENABLED_AT_STARTUP=True).
            if self._wake_listener is not None and self._wake_listener.is_enabled:
                self._standby_btn.configure(text="🛌 Дежурный: вкл")
        elif kind == "fatal":
            self._ready = False
            self._set_controls_enabled(False)
            self._set_state("error", str(payload))
        elif kind == "error":
            self._set_state("error", str(payload))
        elif kind == "turn_result":
            self._apply_turn_result(payload)
        elif kind == "recal_result":
            self._noise_rms = float(payload.get("noise_rms", 0.0))
            self._threshold = float(payload.get("threshold", 0.0))
        elif kind == "vad_refresh":
            self._refresh_vad_from_pipeline()
        elif kind == "health":
            self._apply_health(payload)
        elif kind == "ipc":
            if payload is True:
                self._svc_ipc.configure(text="🟢 IPC")
            elif payload is False:
                self._svc_ipc.configure(text="🔴 IPC")
            else:
                self._svc_ipc.configure(text="⚫ IPC off")
        elif kind == "cal_countdown_start":
            self._start_cal_countdown(float(payload))
        elif kind == "models_list":
            self._apply_models_list(payload)
        elif kind == "model_warming":
            self._model_status.configure(text=str(payload), foreground="#777")
        elif kind == "model_applied":
            thinking = False
            if isinstance(payload, tuple):
                if len(payload) == 3:
                    name, elapsed, thinking = payload
                elif len(payload) == 2:
                    name, elapsed = payload
                else:
                    name, elapsed = payload[0], None
            else:
                name, elapsed = payload, None
            text = f"✓ активна: {name}"
            if elapsed:
                text += f" (прогрет за {elapsed:.1f}с)"
            if thinking:
                text += " — thinking-режим"
            self._model_status.configure(text=text, foreground="#2d8a3e")
        elif kind == "model_error":
            self._model_status.configure(
                text=f"✗ {payload}", foreground="#c93f3f"
            )
        elif kind == "stopped":
            # Worker finished teardown — _tick_shutdown will destroy the
            # window on its next tick. Don't touch the state bar; it's
            # already showing "Завершение…" and the window is about to go.
            self._worker_done = True
        else:
            logger.debug("Unknown UI event: %r", kind)

    def _apply_turn_result(self, result: Any) -> None:
        self._user_text.delete("1.0", "end")
        self._user_text.insert("end", result.user_text or "(нет речи)")
        self._llm_text.delete("1.0", "end")
        self._llm_text.insert("end", result.llm_text or "(пусто)")
        self._update_stats(result)
        if result.error:
            # Status bar detail is visible for the next call; the log also
            # contains the full traceback.
            self._status_text.configure(
                text=f"Готов (последний оборот: {result.error})"
            )

    def _update_stats(self, result: Any) -> None:
        def fmt_ms(value: float | None) -> str:
            return f"{value:,.0f} мс".replace(",", " ") if value is not None else "—"

        self._stats_stt.configure(text=f"🎤 Распознавание: {fmt_ms(result.stt_ms)}")

        llm_bits = [f"🧠 LLM: {fmt_ms(result.llm_ms)}"]
        comp = result.llm_completion_tokens
        prom = result.llm_prompt_tokens
        if comp is not None or prom is not None:
            toks = []
            if prom is not None:
                toks.append(f"prompt={prom}")
            if comp is not None:
                toks.append(f"completion={comp}")
            if prom is not None and comp is not None:
                toks.append(f"всего={prom + comp}")
            llm_bits.append("токены: " + ", ".join(toks))
        self._stats_llm.configure(text="  |  ".join(llm_bits))

        self._stats_tts.configure(text=f"🔊 Синтез: {fmt_ms(result.tts_ms)}")
        total_ms = result.total_s * 1000 if result.total_s else None
        self._stats_total.configure(text=f"⏱ Итого: {fmt_ms(total_ms)}")

    def _apply_models_list(self, payload: Any) -> None:
        models, current = payload
        values = list(models) if models else []
        self._model_combo.configure(values=values)
        if not values:
            self._model_var.set("")
            self._model_status.configure(
                text="нет моделей (проверьте, что бэкенд запущен)",
                foreground="#c93f3f",
            )
            return
        # Keep the current selection if it's still in the list; otherwise pick
        # the backend's active model, or fall back to the first option.
        selected = self._model_var.get()
        if selected not in values:
            selected = current if current in values else values[0]
        self._model_var.set(selected)
        self._model_status.configure(
            text=f"активна: {current or '—'}   ({len(values)} доступно)",
            foreground="#2d8a3e" if current in values else "#777",
        )

    def _refresh_vad_from_pipeline(self) -> None:
        p = self._pipeline
        if p is None:
            return
        vad = p.vad
        if vad is not None:
            self._noise_rms = float(vad.noise_rms)
            self._threshold = float(vad.threshold)

    def _apply_health(self, snap: dict[str, Any]) -> None:
        stt = snap.get("stt", {})
        llm = snap.get("llm", {})
        tts = snap.get("tts", {})
        audio = snap.get("audio", {})

        def _pill(ok: bool, text: str, neutral: bool = False) -> str:
            if neutral:
                return f"🟡 {text}"
            return f"{'🟢' if ok else '🔴'} {text}"

        self._svc_whisper.configure(
            text=_pill(bool(stt.get("loaded")), "Whisper", neutral=not stt.get("loaded"))
        )

        llm_name = llm.get("provider") or "LLM"
        self._svc_llm.configure(
            text=_pill(bool(llm.get("healthy")), f"LLM ({llm_name})")
        )

        # GPU-swap TTS legitimately stays unloaded between turns — call that
        # neutral rather than red so the user doesn't think it broke.
        tts_loaded = bool(tts.get("loaded"))
        tts_swap = bool(tts.get("gpu_swap"))
        tts_name = tts.get("provider") or "TTS"
        if tts_loaded:
            self._svc_tts.configure(text=f"🟢 {tts_name}")
        elif tts_swap:
            self._svc_tts.configure(text=f"🟡 {tts_name} (swap)")
        else:
            self._svc_tts.configure(text=f"🟡 {tts_name}")

        # Keep the noise/threshold fresh between recalibrations — VAD drifts
        # them during record_until_silence and we want to show that drift.
        noise = audio.get("noise_rms")
        thr = audio.get("threshold")
        if noise is not None:
            self._noise_rms = float(noise)
        if thr is not None:
            self._threshold = float(thr)

    # ---- drawing ----------------------------------------------------------

    def _redraw_level_bar(self) -> None:
        c = self._level_canvas
        c.delete("all")
        w = max(c.winfo_width(), 200)
        h = max(c.winfo_height(), 30)

        # Background track.
        c.create_rectangle(0, 0, w, h, fill="#1b1b1b", outline="")

        pct = int(min(100, max(0, self._current_percent)))
        fill_w = int(w * pct / 100)
        if pct < 60:
            color = "#3bb143"
        elif pct < 85:
            color = "#e1c340"
        else:
            color = "#c93f3f"
        c.create_rectangle(0, 0, fill_w, h, fill=color, outline="")

        # Noise floor (blue, solid).
        noise_pct = min(100.0, max(0.0, self._noise_rms / _INT16_PER_PERCENT))
        nx = int(w * noise_pct / 100)
        if 0 <= nx < w:
            c.create_line(nx, 2, nx, h - 2, fill="#4a8fe7", width=2)

        # Threshold (red, dashed).
        thr_pct = min(100.0, max(0.0, self._threshold / _INT16_PER_PERCENT))
        tx = int(w * thr_pct / 100)
        if 0 <= tx < w:
            c.create_line(tx, 0, tx, h, fill="#ff4b4b", width=2, dash=(4, 3))

        self._level_info.configure(
            text=(
                f"RMS: {self._current_rms:>6.0f} ({pct:>3}%)   "
                f"Шум: {self._noise_rms:>5.0f}   "
                f"Порог: {self._threshold:>5.0f}"
            )
        )

    def _refresh_log_text(self) -> None:
        f = self._log_filter_var.get()
        thresholds = {
            "ALL": 0,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
        }
        min_level = thresholds.get(f, 0)

        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        for lvl, line in self._log_lines:
            if lvl >= min_level:
                self._log_text.insert("end", line + "\n")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    # ---- calibration countdown -------------------------------------------

    def _start_cal_countdown(self, duration: float) -> None:
        """Show a live "Калибровка: Xс" countdown in the status bar.

        Runs entirely on the UI thread via ``root.after`` at 250ms resolution
        — fine enough that the displayed number updates visibly without any
        flicker. The countdown stops itself once the deadline passes; a stale
        "loading_stt" / "loading_tts" state from the pipeline will overwrite
        whatever's shown once the next event arrives.
        """
        import time as _time
        deadline = _time.monotonic() + duration

        def _tick() -> None:
            if self._stopped or self._ready:
                return
            remaining = deadline - _time.monotonic()
            if remaining > 0:
                self._set_state("calibrating", f"молчите {remaining:.0f}с…")
                self._root.after(250, _tick)
            else:
                # Calibration done on the pipeline side; next on_stage event
                # ("loading_stt") will replace the text, but show a momentary
                # "готово" so there's no jump straight to empty.
                self._set_state("calibrating", "готово")

        self._set_state("calibrating", f"молчите {duration:.0f}с…")
        self._root.after(250, _tick)

    # ---- small helpers ---------------------------------------------------

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self._listen_btn.configure(state=state)
        self._standby_btn.configure(state=state)
        self._recal_btn.configure(state=state)
        self._refresh_models_btn.configure(state=state)
        self._apply_model_btn.configure(state=state)

    def _set_state(self, name: str, detail: str | None = None) -> None:
        icon, label = STATE_LABELS.get(name, ("?", name))
        # ``standby_idle`` label uses {wake} placeholder so the configured
        # wake-word shows up in the status bar without hard-coding it here.
        if "{wake}" in label:
            label = label.replace("{wake}", WAKE_WORD)
        self._status_icon.configure(text=icon)
        text = label if not detail else f"{label}: {detail}"
        self._status_text.configure(text=text)
        self._state_name = name

    def _current_state(self) -> str:
        return getattr(self, "_state_name", "starting")


# ---- entry point -----------------------------------------------------------


def run_ui(
    *,
    with_ipc: bool = True,
    ipc_host: str = IPC_HOST,
    ipc_port: int = IPC_PORT,
) -> int:
    """Open the UI. Returns when the window is closed."""
    bootstrap()
    root = tk.Tk()
    try:
        VoiceAIApp(root, with_ipc=with_ipc, ipc_host=ipc_host, ipc_port=ipc_port)
        root.mainloop()
    finally:
        # Best-effort cleanup if mainloop bailed abnormally.
        try:
            root.destroy()
        except Exception:
            pass
    return 0


__all__ = ["VoiceAIApp", "run_ui"]
