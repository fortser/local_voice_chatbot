"""Console + IPC orchestrator wiring AudioStream → VAD → STT → LLM → TTS.

Stages 5–6 of DEVELOPMENT_PLAN.md:

* ``--mode console`` — interactive REPL: press Enter, speak, hear the reply.
  Additionally spins up the IPC server on a background thread so other
  processes can talk to the same pipeline (see ``ipc/``).

* ``--mode ipc`` — headless: initialise the pipeline and serve IPC until
  Ctrl+C. No REPL, no initial prompt for a user to be quiet during calibration
  (ambient calibration runs anyway; clients can re-run ``recalibrate`` later).

Design notes:

* **GPU-swap is conditional.** Whisper lives on CUDA; Silero (default TTS) runs
  on CPU, so both models coexist and we keep TTS loaded for the whole session.
  Only XTTS-on-CUDA triggers the unload-STT → load-TTS → synth → unload-TTS →
  reload-STT cycle. The decision is taken from ``config`` at startup and
  cached on :class:`VoicePipeline` so every turn takes the same branch.

* **One pipeline lock serialises console turns and IPC calls.** The console
  REPL and every IPC handler acquire ``pipeline.lock`` before touching the
  mic or models — two callers can't overlap, and whichever arrives second
  just waits. Good enough for a local assistant; no priority inversion to
  worry about.

* **Fallbacks are spoken back to the user in console mode only.** An empty
  STT / empty LLM / failed LLM in ``process_voice_input`` produces a short
  spoken message and the REPL survives. IPC ops don't speak fallbacks —
  they return a structured result (or an error response) so the caller can
  decide what to do.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable

from bootstrap import bootstrap
from commands import (
    CommandContext,
    CommandRouter,
    build_default_registry,
)
from config import (
    ACK_DIR,
    CALIBRATION_DURATION,
    COMMAND_VERBOSE_ACK,
    DICTATE_BEEP_AMPLITUDE,
    DICTATE_BEEP_DURATION_MS,
    DICTATE_BEEP_FREQ,
    DICTATE_INITIAL_TIMEOUT,
    DICTATE_MAX_DURATION,
    DICTATE_PAUSE_THRESHOLD,
    UNRECOGNIZED_BEEP_AMPLITUDE,
    UNRECOGNIZED_BEEP_DURATION_MS,
    UNRECOGNIZED_BEEP_FREQ,
    IPC_HOST,
    IPC_PORT,
    SESSION_BASE_DIR,
    SILERO_DEVICE,
    TTS_DEVICE,
    TTS_PROVIDER,
    WAKE_WORD,
    WAKE_WORD_ALIASES,
    WAKE_WORD_BEEP_SAMPLE_RATE,
)
from core import create_llm_provider, create_stt_provider, create_tts_provider
from core.audio_beep import generate_beep
from logging_config import UNRECOGNIZED_LOGGER_NAME
from core.audio_output import AudioPlayer
from core.audio_stream import AudioStream
from core.prompt_manager import detect_thinking_markers
from core.vad import VoiceActivityDetector
from system.audio_session_mute import MuteController
from system.session_manager import SessionManager
from utils.errors import (
    AudioError,
    LLMError,
    STTError,
    TTSError,
    VoiceAIError,
)

logger = logging.getLogger(__name__)
unrecognized_logger = logging.getLogger(UNRECOGNIZED_LOGGER_NAME)

FALLBACK_NO_SPEECH = "Я не расслышал, повторите пожалуйста."
FALLBACK_EMPTY_LLM = "Модель не ответила. Попробуйте ещё раз."
FALLBACK_LLM_ERROR = "Возникла ошибка с языковой моделью."


def _tts_requires_gpu_swap() -> bool:
    """True iff the selected TTS runs on CUDA — then it fights Whisper for VRAM."""
    provider = (TTS_PROVIDER or "").lower()
    if provider == "xtts":
        return (TTS_DEVICE or "").lower() == "cuda"
    if provider == "silero":
        return (SILERO_DEVICE or "").lower() == "cuda"
    return False


@dataclass
class TurnResult:
    user_text: str
    llm_text: str
    wav_in: str | None
    wav_out: str | None
    total_s: float
    error: str | None = None
    # Per-stage wall-clock timings in milliseconds. ``None`` when the stage
    # was skipped (e.g. empty STT short-circuits LLM, empty LLM short-circuits
    # the primary TTS — though the fallback phrase still gets synthesised).
    stt_ms: float | None = None
    llm_ms: float | None = None
    tts_ms: float | None = None
    # Token accounting straight from the LLM backend (``eval_count`` /
    # ``completion_tokens`` for output, ``prompt_eval_count`` /
    # ``prompt_tokens`` for input). ``None`` if the backend didn't report.
    llm_prompt_tokens: int | None = None
    llm_completion_tokens: int | None = None


class VoicePipeline:
    """One AudioStream + VAD + STT + LLM + TTS, orchestrated per-turn."""

    def __init__(self) -> None:
        self._stream = AudioStream()
        self._vad: VoiceActivityDetector | None = None
        self._stt = create_stt_provider()
        self._llm = create_llm_provider()
        self._tts = create_tts_provider()
        self._player = AudioPlayer()
        self._gpu_swap = _tts_requires_gpu_swap()
        # Reentrant: a turn that's already holding the lock can call
        # ``dictate()`` (which also wants the lock) without deadlocking. IPC
        # / wake-word / console mutual exclusion still works because all entry
        # points acquire it from a thread that doesn't already hold it.
        self._lock = threading.RLock()
        # Lazy session — created on first save_note / save_screenshot.
        self._session = SessionManager(SESSION_BASE_DIR)
        # Per-session mute (M4): заглушает чужие плееры, не Шурочку.
        self._audio_mute = MuteController()
        # Pre-rendered dictation beep (in-memory, no I/O at runtime).
        self._dictate_beep = generate_beep(
            DICTATE_BEEP_FREQ,
            DICTATE_BEEP_DURATION_MS,
            sample_rate=WAKE_WORD_BEEP_SAMPLE_RATE,
            amplitude=DICTATE_BEEP_AMPLITUDE,
        )
        # Бип «не поняла команду» — играет вместо неявного LLM-фоллбэка.
        self._unrecognized_beep = generate_beep(
            UNRECOGNIZED_BEEP_FREQ,
            UNRECOGNIZED_BEEP_DURATION_MS,
            sample_rate=WAKE_WORD_BEEP_SAMPLE_RATE,
            amplitude=UNRECOGNIZED_BEEP_AMPLITUDE,
        )
        # Command router (M1). All commands are stubs in this stage; integration
        # path: STT result is offered to the router *before* falling through to
        # the LLM. Wake-word strip-out lives in the router itself so the same
        # logic works in console-typed input and serial-mode (M10).
        self._registry = build_default_registry()
        self._router = CommandRouter(
            self._registry,
            wake_words=(WAKE_WORD, *WAKE_WORD_ALIASES),
        )

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    @property
    def session(self) -> SessionManager:
        return self._session

    @property
    def audio_mute(self) -> MuteController:
        return self._audio_mute

    @property
    def stream(self) -> AudioStream:
        return self._stream

    @property
    def vad(self) -> VoiceActivityDetector | None:
        return self._vad

    @property
    def stt(self):
        return self._stt

    @property
    def player(self) -> AudioPlayer:
        return self._player

    @property
    def router(self) -> CommandRouter:
        return self._router

    # ---- lifecycle ----

    def start(self, on_stage: Callable[[str, object], None] | None = None) -> None:
        """Initialise and warm up all subsystems.

        ``on_stage(name, payload)`` is called at the start of each slow step
        so callers (UI) can show progress without polling:

        * ``("calibrating", duration_s)`` — VAD calibration starting
        * ``("loading_stt", None)``         — Whisper model loading
        * ``("loading_tts", None)``         — TTS model loading
        """
        def _stage(name: str, payload: object = None) -> None:
            if on_stage is not None:
                try:
                    on_stage(name, payload)
                except Exception:
                    logger.debug("on_stage callback raised", exc_info=True)

        logger.info(
            "Pipeline start: stt=%s llm=%s tts=%s gpu_swap=%s",
            type(self._stt).__name__,
            type(self._llm).__name__,
            type(self._tts).__name__,
            self._gpu_swap,
        )
        self._stream.start()
        try:
            self._vad = VoiceActivityDetector(self._stream)

            print("Калибровка шума (молчите ~2 сек)…")
            t0 = time.monotonic()
            _stage("calibrating", CALIBRATION_DURATION)
            noise, threshold = self._vad.calibrate()
            print(
                f"  шум={noise:.0f} RMS, порог={threshold:.0f} "
                f"(за {time.monotonic() - t0:.1f}с)"
            )

            print("Загружаю Whisper…")
            t0 = time.monotonic()
            _stage("loading_stt")
            self._stt.load_model()
            print(f"  готов за {time.monotonic() - t0:.1f}с")

            if self._llm.is_healthy():
                print(f"LLM доступен: {getattr(self._llm, 'model', '?')}")
            else:
                print(
                    "⚠ LLM не отвечает на health-check — "
                    "запустите Ollama / LM Studio, иначе оборот упадёт с fallback'ом."
                )

            if not self._gpu_swap:
                print("Загружаю TTS…")
                t0 = time.monotonic()
                _stage("loading_tts")
                self._tts.load_model()
                print(f"  готов за {time.monotonic() - t0:.1f}с")
            else:
                print(
                    "TTS будет загружаться на каждом обороте "
                    "(GPU-swap со Whisper — TTS_DEVICE=cuda)."
                )
        except Exception:
            # Any init failure → tear down what we already started.
            self.stop()
            raise

    def stop(self) -> None:
        logger.info("Pipeline stop")
        # Снять mute со всех чужих сессий, что мы заглушили — иначе
        # пользователь останется без звука и будет лезть в системный микшер.
        try:
            self._audio_mute.restore_all()
        except Exception:
            logger.exception("audio_mute.restore_all failed")
        # Best-effort unload in reverse dependency order.
        for name, action in (
            ("tts.unload", self._tts.unload_model),
            ("stt.unload", self._stt.unload_model),
            ("stream.stop", self._stream.stop),
        ):
            try:
                action()
            except Exception:
                logger.exception("Error during %s", name)

    # ---- one turn ----

    def process_voice_input(
        self,
        on_stage: Callable[[str], None] | None = None,
    ) -> TurnResult:
        assert self._vad is not None, "start() must be called first"
        # Acquire the shared lock for the whole turn — blocks IPC handlers
        # from touching the mic/models until we're done. Console callers
        # accept this blocking; they're interactive anyway.
        with self._lock:
            return self._process_voice_input_locked(on_stage)

    def process_voice_input_from_wav(
        self,
        wav_in: str,
        on_stage: Callable[[str], None] | None = None,
    ) -> TurnResult:
        """Run STT→LLM→TTS+playback on a pre-recorded WAV.

        Used by the wake-word listener: it records the user's question
        itself (directly via VAD, so it can apply its own timeout) and then
        hands the WAV to the pipeline to finish the turn.
        """
        with self._lock:
            return self._process_voice_input_locked(on_stage, wav_in=wav_in)

    def _process_voice_input_locked(
        self,
        on_stage: Callable[[str], None] | None = None,
        wav_in: str | None = None,
    ) -> TurnResult:
        assert self._vad is not None
        t_total = time.monotonic()

        def _emit(stage: str) -> None:
            if on_stage is not None:
                try:
                    on_stage(stage)
                except Exception:
                    logger.exception("on_stage callback raised")

        # 1. Record (skipped if caller supplied a WAV already)
        if wav_in is None:
            _emit("listening")
            print("🎤 Слушаю… (автостоп через ~1 сек тишины)")
            try:
                wav_in = self._vad.record_until_silence()
            except AudioError as exc:
                logger.warning("Recording failed: %s", exc)
                return TurnResult(
                    "", "", None, None,
                    time.monotonic() - t_total,
                    f"recording: {exc}",
                )

        # 2. STT
        _emit("processing")
        print("📝 Распознаю…")
        t_stt = time.monotonic()
        try:
            user_text = self._stt.transcribe(wav_in).strip()
        except STTError as exc:
            logger.exception("STT failed")
            return TurnResult(
                "", "", wav_in, None,
                time.monotonic() - t_total,
                f"stt: {exc}",
                stt_ms=(time.monotonic() - t_stt) * 1000,
            )
        stt_ms = (time.monotonic() - t_stt) * 1000

        if not user_text:
            wav_out, tts_ms = self._speak_safely(FALLBACK_NO_SPEECH)
            return TurnResult(
                "", FALLBACK_NO_SPEECH, wav_in, wav_out,
                time.monotonic() - t_total,
                stt_ms=stt_ms, tts_ms=tts_ms,
            )

        print(f"   «{user_text}»")

        # 3. Command router (M1+M2.5).
        # Единственный путь обработки: либо команда из реестра, либо ничего.
        # LLM теперь вызывается только через явную QuestionCommand
        # («ответь на вопрос …», «подскажи …»), а не как неявный фоллбэк.
        # См. feedback memory `feedback_two_word_commands` и
        # `feedback_explicit_llm_only`.
        cmd_ctx = CommandContext(
            pipeline=self,
            full_text=user_text,
            session_manager=self._session,
        )
        cmd = self._router.dispatch(user_text, cmd_ctx)
        if cmd is not None:
            logger.info("Turn handled by command router: %s", cmd.name)
            print(f"   ⚡ выполнено как команда: {cmd.name}")
            # ack_after — для INSTANT/GLOBAL играется после действия. Для
            # CONTENT-команд (note, question) ack_after обычно None: они
            # озвучивают результат сами (сохранённая заметка / ответ LLM).
            self._play_ack(cmd.ack_after)
            return TurnResult(
                user_text, "", wav_in, None,
                time.monotonic() - t_total,
                stt_ms=stt_ms,
            )

        # 4. Нераспознано — короткий бип, без LLM.
        logger.info("No command matched; LLM skipped (explicit-only mode)")
        # Параллельно пишем в отдельный журнал нераспознанных фраз
        # (logs/unrecognized.log) для последующего анализа: какие
        # формулировки пользователь произносит, чего не хватает в синонимах.
        unrecognized_logger.info(user_text)
        print("   🔇 не поняла команду")
        try:
            self._player.play_array(
                self._unrecognized_beep,
                WAKE_WORD_BEEP_SAMPLE_RATE,
                blocking=True,
            )
        except AudioError:
            logger.exception("Unrecognized beep failed")
        return TurnResult(
            user_text, "", wav_in, None,
            time.monotonic() - t_total,
            error="no_command_match",
            stt_ms=stt_ms,
        )

    # ---- IPC-oriented operations ----
    #
    # These mirror ``process_voice_input`` but:
    #   * never voice a fallback (IPC caller decides what to do with empty text)
    #   * raise errors (IPC server maps them to structured error responses)
    #   * accept a pre-recorded WAV instead of using the mic (except recalibrate)
    # All of them grab ``self._lock`` so they can't overlap with a console turn.

    def transcribe_file(
        self, audio_path: str, *, speak: bool = True
    ) -> dict[str, object]:
        """STT → LLM → TTS on a pre-recorded WAV. Raises on subsystem failure."""
        from pathlib import Path

        if not Path(audio_path).is_file():
            raise FileNotFoundError(audio_path)

        with self._lock:
            t0 = time.monotonic()
            user_text = self._stt.transcribe(audio_path).strip()
            llm_text = ""
            wav_out: str | None = None
            if user_text:
                llm_text = self._llm.generate(user_text).strip()
                if llm_text and speak:
                    wav_out, _synth_ms = self._speak(llm_text, play=False)
            return {
                "input_text": user_text,
                "output_text": llm_text,
                "audio_file": wav_out,
                "processing_time": time.monotonic() - t0,
            }

    def generate_text(
        self, text: str, *, speak: bool = True
    ) -> dict[str, object]:
        """LLM → TTS on a supplied prompt. Skips STT entirely."""
        with self._lock:
            t0 = time.monotonic()
            llm_text = self._llm.generate(text).strip()
            wav_out: str | None = None
            if llm_text and speak:
                wav_out, _synth_ms = self._speak(llm_text, play=False)
            return {
                "input_text": text,
                "output_text": llm_text,
                "audio_file": wav_out,
                "processing_time": time.monotonic() - t0,
            }

    def recalibrate(self, duration: float | None = None) -> dict[str, float]:
        """Re-run VAD calibration. Caller is expected to keep the room quiet."""
        assert self._vad is not None, "start() must be called first"
        dur = float(duration) if duration is not None else CALIBRATION_DURATION
        with self._lock:
            noise, threshold = self._vad.calibrate(dur)
            return {
                "noise_rms": float(noise),
                "threshold": float(threshold),
                "duration": dur,
            }

    def list_llm_models(self) -> list[str]:
        """Ask the LLM backend for its available models. Empty list on failure.

        Held outside the pipeline lock — this is a quick HTTP query against
        the backend and we don't want it to queue behind an in-flight turn.
        """
        lister = getattr(self._llm, "list_models", None)
        if lister is None:
            return []
        try:
            return list(lister())
        except Exception:
            logger.exception("list_llm_models failed")
            return []

    def set_llm_model(self, name: str) -> None:
        """Swap the active LLM model. Takes the lock so a turn can't race."""
        setter = getattr(self._llm, "set_model", None)
        if setter is None:
            raise RuntimeError(
                f"{type(self._llm).__name__} does not support runtime model switching"
            )
        with self._lock:
            setter(name)

    def warmup_llm(self, *, timeout: float = 600.0) -> dict[str, object]:
        """Fire a real generate so the backend loads the model and we can
        sniff its output format.

        LM Studio and Ollama both do just-in-time model loading: the model
        hits VRAM/RAM only when a request targets it. Calling this after
        ``set_llm_model`` moves the (sometimes multi-minute) load time into
        an explicit moment the user is waiting on.

        We also reuse the warmup to **autodetect thinking models** — we send
        a concrete question with ``max_tokens=64``, enough to see the
        reasoning preamble (``<|channel|>analysis``, ``Thinking Process:``,
        ``<think>``…). If any appears, the provider gets the model flagged
        so subsequent voice turns run with the ×N token/timeout budget
        instead of getting cut off mid-thought.

        Returns ``{"elapsed_s", "thinking_detected"}``. Raises the usual LLM
        errors on network/config failure.
        """
        with self._lock:
            client = getattr(self._llm, "client", None)
            model = getattr(self._llm, "model", None)
            if client is None or not model or model == "(auto)":
                return {"elapsed_s": 0.0, "thinking_detected": False}
            # Question that reliably elicits reasoning in thinking models
            # (the user's own test case); for non-thinking models it's a
            # cheap one-sentence answer.
            result = client.generate(
                "Когда родился Пушкин?",
                model=model,
                max_tokens=64,
                timeout=float(timeout),
                system_prompt=getattr(self._llm, "_system_prompt", None),
            )
            raw_text = getattr(result, "text", "") or ""
            thinking = detect_thinking_markers(raw_text)
            if thinking:
                marker = getattr(self._llm, "mark_thinking", None)
                if callable(marker):
                    marker(model)
            return {
                "elapsed_s": float(getattr(result, "elapsed_s", 0.0) or 0.0),
                "thinking_detected": bool(thinking),
            }

    def health_check(self) -> dict[str, object]:
        """Snapshot of subsystem status. Never raises — reports errors inline.

        Doesn't grab the lock: health should be queryable while a turn is
        underway. Values may be stale by a few ms, which is fine — this is a
        coarse diagnostic, not a synchronisation primitive.
        """
        # LLM health check hits the remote HTTP service; guard against network
        # hiccups turning an informational query into an exception.
        try:
            llm_ok = bool(self._llm.is_healthy())
            llm_error: str | None = None
        except Exception as exc:  # noqa: BLE001 — defensive, we report everything
            llm_ok = False
            llm_error = str(exc)

        return {
            "stt": {
                "provider": type(self._stt).__name__,
                "loaded": bool(getattr(self._stt, "is_loaded", False)),
            },
            "llm": {
                "provider": type(self._llm).__name__,
                "model": getattr(self._llm, "model", None),
                "healthy": llm_ok,
                "error": llm_error,
            },
            "tts": {
                "provider": type(self._tts).__name__,
                "loaded": bool(getattr(self._tts, "is_loaded", False)),
                "gpu_swap": self._gpu_swap,
            },
            "audio": {
                "stream_running": bool(self._stream.is_running),
                "noise_rms": float(self._vad.noise_rms) if self._vad else None,
                "threshold": float(self._vad.threshold) if self._vad else None,
            },
        }

    # ---- ack-фразы (M2.6) ----

    def _play_ack(self, filename: str | None) -> bool:
        """Проиграть pre-rendered ack-WAV. Возвращает True, если сыграли.

        Молча возвращает False если:
        - фича выключена (`COMMAND_VERBOSE_ACK = False`);
        - ``filename`` не задан (команда не озвучивает эту фазу);
        - файла нет на диске (например, забыли запустить
          `python -m utils.generate_ack_phrases`).

        Воспроизведение — blocking, чтобы ack-фраза не накладывалась на
        следующий шаг (бип-стартер диктовки или TTS-ответ).
        """
        if not COMMAND_VERBOSE_ACK or not filename:
            return False
        path = ACK_DIR / filename
        if not path.is_file():
            logger.warning(
                "Ack-WAV не найден: %s — запустите "
                "`python -m utils.generate_ack_phrases`", path,
            )
            return False
        try:
            self._player.play_file(str(path))
            return True
        except AudioError:
            logger.exception("Ack playback failed: %s", path)
            return False

    # ---- dictation (M2) ----

    def dictate(
        self,
        *,
        ack_filename: str | None = None,
        pause_threshold: float = DICTATE_PAUSE_THRESHOLD,
        max_duration: float = DICTATE_MAX_DURATION,
        initial_silence_timeout: float = DICTATE_INITIAL_TIMEOUT,
    ) -> str:
        """Записать надиктовку, прогнать через STT, вернуть строку.

        Используется командами CONTENT-типа (NoteCommand и далее
        ScreenshotNoteCommand). Не делает TTS — только звуковой бип-стартер
        и распознавание; озвучивает результат вызывающая команда.

        Lock реентрантный: метод можно вызывать как изнутри уже идущего хода
        (router → command), так и снаружи (например, из теста). Возвращает
        ``""``, если человек промолчал дольше ``initial_silence_timeout``.
        """
        assert self._vad is not None, "start() must be called first"
        with self._lock:
            logger.info(
                "Dictate: pause=%.1fs, max=%.1fs, initial_timeout=%.1fs",
                pause_threshold, max_duration, initial_silence_timeout,
            )
            print("🎤 Диктуйте…")
            # Если ack-фраза есть — играем её (она уже несёт смысл «диктуйте»);
            # иначе старый беп-стартер 1200 Гц.
            if not self._play_ack(ack_filename):
                try:
                    self._player.play_array(
                        self._dictate_beep,
                        WAKE_WORD_BEEP_SAMPLE_RATE,
                        blocking=True,
                    )
                except AudioError:
                    logger.exception("Dictate beep failed; продолжаем без сигнала")

            # Свежий порог после возможного дрейфа за время сканирующих
            # итераций wake-word или предыдущих ходов.
            self._vad.reset_threshold()

            try:
                wav = self._vad.record_until_silence(
                    pause_threshold=pause_threshold,
                    max_duration=max_duration,
                    initial_silence_timeout=initial_silence_timeout,
                )
            except AudioError as exc:
                logger.info("Dictate: тишина (%s)", exc)
                return ""

            try:
                text = self._stt.transcribe(wav).strip()
            except STTError as exc:
                logger.exception("Dictate: STT упал")
                raise STTError(f"dictate: {exc}") from exc

            logger.info("Dictate transcript: %r", text[:120])
            return text

    # ---- Q&A для QuestionCommand (M2.5) ----

    def answer_question(self, question: str) -> str:
        """Прогнать вопрос через LLM и озвучить ответ.

        Используется :class:`QuestionCommand`. Возвращает текст ответа.
        Не входит в обычный поток ``_process_voice_input_locked`` — там
        теперь нет неявного фоллбэка в LLM, обращение к модели возможно
        только через явную команду.

        Lock реентрантный — вызов из-под турного lock'а (router) безопасен.
        """
        question = (question or "").strip()
        if not question:
            return ""
        with self._lock:
            print("🧠 Думаю…")
            try:
                answer = self._llm.generate(question).strip()
            except (LLMError, VoiceAIError) as exc:
                logger.exception("answer_question: LLM упал")
                self._speak_safely(FALLBACK_LLM_ERROR)
                raise LLMError(f"answer_question: {exc}") from exc

            if not answer:
                logger.info("answer_question: LLM вернул пустую строку")
                self._speak_safely(FALLBACK_EMPTY_LLM)
                return ""

            print(f"   «{answer}»")
            self._speak_safely(answer)
            return answer

    # ---- TTS helpers ----

    def _speak(self, text: str, *, play: bool = True) -> tuple[str, float]:
        """Synthesize. Optionally play. GPU-swap when required. Raises on failure.

        Returns ``(wav_path, synth_ms)`` — ``synth_ms`` covers model I/O
        (including the GPU-swap shuffle when it kicks in) but **not** playback,
        since playback time is a property of the clip's duration, not of TTS
        performance.

        ``play=False`` is the IPC path: the caller just wants a WAV on disk
        to fetch or serve; playing it locally would be surprising.
        """
        t_synth = time.monotonic()
        if self._gpu_swap:
            logger.info("GPU swap: unload STT → load TTS → synth → unload TTS → reload STT")
            self._stt.unload_model()
            try:
                self._tts.load_model()
                wav = self._tts.synthesize(text)
            finally:
                try:
                    self._tts.unload_model()
                finally:
                    # Always try to bring STT back, even if TTS unload blew up.
                    self._stt.load_model()
        else:
            wav = self._tts.synthesize(text)
        synth_ms = (time.monotonic() - t_synth) * 1000

        if play:
            print("🔊 Воспроизвожу…")
            self._player.play_file(wav)
        return wav, synth_ms

    def _speak_safely(self, text: str) -> tuple[str | None, float | None]:
        """Like :meth:`_speak` but swallows TTS/playback errors into a warning.

        Returns ``(wav_path | None, synth_ms | None)``. ``None, None`` means
        synthesis itself failed; ``wav, synth_ms`` means the WAV exists even
        if playback later blew up (we still measured the synth correctly).
        """
        try:
            return self._speak(text)
        except TTSError as exc:
            logger.exception("TTS failed")
            print(f"⚠ TTS ошибка: {exc}")
        except AudioError as exc:
            logger.exception("Playback failed")
            print(f"⚠ воспроизведение не удалось: {exc}")
        return None, None


def _start_ipc_server(pipeline: VoicePipeline, host: str, port: int):
    """Lazy import to avoid pulling pydantic into non-IPC test scripts."""
    from ipc.server import VoiceAIServer

    server = VoiceAIServer(pipeline, host=host, port=port)
    server.start()
    print(f"🛰 IPC сервер на tcp://{host}:{port}")
    return server


def run_console_mode(
    *,
    with_ipc: bool = True,
    ipc_host: str = IPC_HOST,
    ipc_port: int = IPC_PORT,
) -> int:
    bootstrap()
    pipeline = VoicePipeline()
    pipeline.start()

    ipc_server = None
    if with_ipc:
        try:
            ipc_server = _start_ipc_server(pipeline, ipc_host, ipc_port)
        except RuntimeError as exc:
            # Don't kill the REPL if the port is busy — report and keep going.
            print(f"⚠ IPC не поднялся: {exc}")

    print()
    print("=" * 60)
    print("Консольный режим. Enter — начать запись. 'q' / Ctrl+C — выход.")
    print("=" * 60)

    try:
        while True:
            try:
                cmd = input("\n> (Enter для записи) ")
            except EOFError:
                break
            if cmd.strip().lower() in ("q", "quit", "exit"):
                break

            result = pipeline.process_voice_input()
            if result.error:
                print(f"❌ {result.error}")
            print(f"⏱ оборот: {result.total_s:.1f}с")

    except KeyboardInterrupt:
        print("\nCtrl+C — выходим…")
    finally:
        if ipc_server is not None:
            ipc_server.stop()
        pipeline.stop()

    return 0


def run_ipc_mode(*, ipc_host: str = IPC_HOST, ipc_port: int = IPC_PORT) -> int:
    """Headless mode: start the pipeline + IPC server, wait for Ctrl+C."""
    bootstrap()
    pipeline = VoicePipeline()
    pipeline.start()

    ipc_server = None
    try:
        ipc_server = _start_ipc_server(pipeline, ipc_host, ipc_port)
    except RuntimeError as exc:
        print(f"❌ {exc}")
        pipeline.stop()
        return 2

    print()
    print("=" * 60)
    print("Headless IPC-режим. Ctrl+C — выход.")
    print("Методы:")
    print("  health_check, generate_only, transcribe_and_respond, recalibrate")
    print("=" * 60)

    stop_event = threading.Event()
    try:
        # A plain sleep loop keeps signals working on Windows (Event.wait
        # can swallow KeyboardInterrupt on some Python builds).
        while not stop_event.is_set():
            stop_event.wait(timeout=0.5)
    except KeyboardInterrupt:
        print("\nCtrl+C — выходим…")
    finally:
        if ipc_server is not None:
            ipc_server.stop()
        pipeline.stop()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Voice AI Assistant — console + IPC orchestrator"
    )
    parser.add_argument(
        "--mode",
        choices=["ui", "console", "ipc"],
        default="ui",
        help=(
            "ui = Tkinter GUI with diagnostics (default); "
            "console = interactive REPL + IPC server on background thread; "
            "ipc = headless, IPC server only."
        ),
    )
    parser.add_argument(
        "--no-ipc",
        action="store_true",
        help="Console mode only: skip starting the IPC server.",
    )
    parser.add_argument("--host", default=IPC_HOST, help="IPC bind host.")
    parser.add_argument("--port", type=int, default=IPC_PORT, help="IPC bind port.")
    args = parser.parse_args()

    if args.mode == "ui":
        # Lazy import so console/IPC modes don't drag in Tkinter dependencies.
        from ui.tkinter_ui import run_ui
        return run_ui(
            with_ipc=not args.no_ipc, ipc_host=args.host, ipc_port=args.port
        )
    if args.mode == "console":
        return run_console_mode(
            with_ipc=not args.no_ipc, ipc_host=args.host, ipc_port=args.port
        )
    if args.mode == "ipc":
        return run_ipc_mode(ipc_host=args.host, ipc_port=args.port)

    return 1


if __name__ == "__main__":
    sys.exit(main())
