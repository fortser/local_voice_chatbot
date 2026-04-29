"""Wake-word listener (Stage 8, MVP).

Dejurny mode: a background thread repeatedly records short windows from the
mic, runs Whisper on them, and watches for the configured wake-word
(``"шурочка"`` by default). On a match it plays an activation beep, records
the user's question (with a timeout), and hands it to the pipeline for a
normal STT→LLM→TTS+playback turn.

This is the MVP path — no dedicated wake-word engine, no substring
heuristics, no extra dependencies. The class is kept deliberately thin and
focused on the orchestration so it can be swapped out later for a real
wake-word detector (Porcupine / openWakeWord) without touching the UI or
the pipeline.

Concurrency:
  * One daemon thread runs :meth:`_loop`.
  * The thread acquires ``pipeline.lock`` for a single scan-or-activation
    iteration, so the manual record button still gets a turn between
    iterations.
  * ``stop()`` is idempotent; callers should invoke it before
    ``pipeline.stop()``.

Wake-word matching:
  Exact match on tokenized, lowercased, de-punctuated STT output — ``WAKE_WORD``
  or any of ``WAKE_WORD_ALIASES``. No substring matching: ``"шурочкин"``
  must not trigger on ``"шурочка"``. This is intentional (see user memory
  ``feedback_avoid_complex_auto``).
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Callable, Iterable, Sequence

from config import (
    KEEP_AWAKE_AFTER_TURN_S,
    WAKE_WORD,
    WAKE_WORD_ACTIVE_TIMEOUT,
    WAKE_WORD_ALIASES,
    WAKE_WORD_BEEP_AMPLITUDE,
    WAKE_WORD_BEEP_DURATION_MS,
    WAKE_WORD_BEEP_OFF_FREQ,
    WAKE_WORD_BEEP_ON_FREQ,
    WAKE_WORD_BEEP_SAMPLE_RATE,
    WAKE_WORD_SCAN_WINDOW,
)
from core.audio_beep import generate_beep
from system import keep_awake
from utils.errors import AudioError, STTError, VoiceAIError

logger = logging.getLogger(__name__)

# States posted to the UI callback. Keep the names in sync with
# ``ui.tkinter_ui.STATE_LABELS``.
STATE_STANDBY_IDLE = "standby_idle"        # enabled, listening for wake-word
STATE_WAKE_HEARD = "wake_heard"            # matched, about to beep + prompt
STATE_WAKE_ACTIVE = "wake_active"          # beep played, recording user question
STATE_WAKE_PROCESSING = "wake_processing"  # STT → LLM → TTS on the question
STATE_WAKE_DISABLED = "idle"               # listener switched off; UI returns to "Готов"

_WORD_BOUNDARY = re.compile(r"[^\w\s]+", flags=re.UNICODE)


def _normalize(text: str) -> list[str]:
    """Return the list of tokens for wake-word comparison.

    Lowercase, strip punctuation, split on whitespace. Pure function so it
    can be unit-tested without the rest of the subsystem.
    """
    if not text:
        return []
    cleaned = _WORD_BOUNDARY.sub(" ", text.lower())
    return [t for t in cleaned.split() if t]


def contains_wake_word(text: str, wake_word: str, aliases: Iterable[str] = ()) -> bool:
    """True iff any token in ``text`` equals ``wake_word`` or any alias."""
    tokens = set(_normalize(text))
    if not tokens:
        return False
    candidates = {wake_word.lower(), *(a.lower() for a in aliases)}
    return bool(tokens & candidates)


class WakeWordListener:
    """Background wake-word listener driving the standby / active cycle."""

    def __init__(
        self,
        pipeline,
        *,
        on_state: Callable[[str, object], None] | None = None,
        wake_word: str = WAKE_WORD,
        aliases: Sequence[str] = tuple(WAKE_WORD_ALIASES),
        scan_window: float = WAKE_WORD_SCAN_WINDOW,
        active_timeout: float = WAKE_WORD_ACTIVE_TIMEOUT,
    ) -> None:
        self._pipeline = pipeline
        self._on_state = on_state
        self._wake_word = wake_word
        self._aliases = tuple(aliases)
        self._scan_window = float(scan_window)
        self._active_timeout = float(active_timeout)

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        # ``_enabled`` gates the scan loop without killing the thread — the
        # UI toggle flips this, start()/stop() manage the thread lifetime.
        self._enabled = threading.Event()

        self._beep_on = generate_beep(
            WAKE_WORD_BEEP_ON_FREQ,
            WAKE_WORD_BEEP_DURATION_MS,
            sample_rate=WAKE_WORD_BEEP_SAMPLE_RATE,
            amplitude=WAKE_WORD_BEEP_AMPLITUDE,
        )
        self._beep_off = generate_beep(
            WAKE_WORD_BEEP_OFF_FREQ,
            WAKE_WORD_BEEP_DURATION_MS,
            sample_rate=WAKE_WORD_BEEP_SAMPLE_RATE,
            amplitude=WAKE_WORD_BEEP_AMPLITUDE,
        )

    # ---- public API ---------------------------------------------------------

    def start(self) -> None:
        """Spin up the background thread. Idempotent."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="WakeWordListener", daemon=True
        )
        self._thread.start()
        logger.info("WakeWordListener started (wake_word=%r)", self._wake_word)

    def stop(self, timeout: float | None = None) -> None:
        """Signal stop and join the thread. Safe to call multiple times."""
        self._stop_event.set()
        self._enabled.clear()
        thread = self._thread
        if thread is not None and thread.is_alive():
            # Scan window + STT latency bound; +1s cushion.
            thread.join(timeout=timeout if timeout is not None else self._scan_window + 2.0)
        self._thread = None
        logger.info("WakeWordListener stopped")

    def enable(self) -> None:
        """Turn on standby listening. Requires ``start()`` to have been called."""
        if self._enabled.is_set():
            return
        self._enabled.set()
        self._emit(STATE_STANDBY_IDLE)
        logger.info("Standby mode enabled")

    def disable(self) -> None:
        """Pause standby listening without stopping the thread."""
        if not self._enabled.is_set():
            return
        self._enabled.clear()
        self._emit(STATE_WAKE_DISABLED)
        logger.info("Standby mode disabled")

    @property
    def is_enabled(self) -> bool:
        return self._enabled.is_set()

    # ---- loop ---------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            # Wait for enable() without spinning.
            if not self._enabled.wait(timeout=0.2):
                continue
            if self._stop_event.is_set():
                break
            try:
                self._iterate()
            except Exception:
                logger.exception("WakeWordListener iteration failed")
                # Don't melt the CPU if something's broken — brief pause.
                self._stop_event.wait(timeout=1.0)

    def _iterate(self) -> None:
        """One scan; on match — run the full activation sequence.

        Holds ``pipeline.lock`` for the whole iteration so it can't overlap
        with a manual record turn. Between iterations the lock is released,
        which is the window for the "🎤 Слушай" button to grab it.
        """
        pipeline = self._pipeline
        vad = pipeline.vad
        if vad is None:
            # Pipeline not ready yet — back off so we don't spin.
            self._stop_event.wait(timeout=0.5)
            return

        with pipeline.lock:
            if self._stop_event.is_set() or not self._enabled.is_set():
                return

            # 1. Scan: short window, brief pause, fast give-up on silence.
            try:
                scan_wav = vad.record_until_silence(
                    pause_threshold=0.5,
                    max_duration=self._scan_window,
                    initial_silence_timeout=self._scan_window,
                )
            except AudioError:
                # No speech in this window — normal path.
                return

            # 2. Transcribe scan and check for wake-word.
            try:
                text = pipeline.stt.transcribe(scan_wav).strip()
            except STTError:
                logger.exception("Wake-word scan STT failed")
                return

            if not text:
                return

            matched = contains_wake_word(text, self._wake_word, self._aliases)
            logger.info(
                "Wake-word scan: %r (match=%s)", text[:80], matched
            )
            if not matched:
                return

            # 3. Wake-word heard — beep, record question, process.
            # Сразу ставим anti-screensaver hold: запись/STT/LLM/TTS дальше
            # могут занять минуту+, а turn_start в pipeline отсчитает 120с
            # только от своей точки. Здесь окно "услышали → запись" тоже
            # должно быть защищено.
            keep_awake.acquire(KEEP_AWAKE_AFTER_TURN_S, reason="wake_word")
            self._emit(STATE_WAKE_HEARD, text)
            self._play_beep(self._beep_on)

            self._emit(STATE_WAKE_ACTIVE)
            # Восстанавливаем «свежий» порог после дрейфа во время
            # сканирующих итераций, и даём 200 мс тишины, чтобы хвост
            # бипа / реверберация динамиков в комнате успели затухнуть
            # до начала активной записи.
            vad.reset_threshold()
            time.sleep(0.2)
            try:
                question_wav = vad.record_until_silence(
                    max_duration=self._active_timeout + 30.0,
                    initial_silence_timeout=self._active_timeout,
                )
            except AudioError:
                logger.info(
                    "Wake-word: user silent for %.1fs — cancelling",
                    self._active_timeout,
                )
                self._play_beep(self._beep_off)
                self._emit(STATE_STANDBY_IDLE)
                return

            # 4. Run the full turn on the recorded question.
            self._emit(STATE_WAKE_PROCESSING)
            try:
                result = pipeline._process_voice_input_locked(  # noqa: SLF001
                    on_stage=None,
                    wav_in=question_wav,
                )
                self._emit("turn_result", result)
            except VoiceAIError:
                logger.exception("Wake-word: turn failed")

            # Tell the user audibly that we're back to listening for the
            # wake-word. Same beep as the timeout path — in both cases the
            # meaning is "активный режим закрыт, снова жду «шурочку»".
            self._play_beep(self._beep_off)
            self._emit(STATE_STANDBY_IDLE)

    # ---- helpers ------------------------------------------------------------

    def _play_beep(self, samples) -> None:
        logger.info(
            "Playing wake-word beep (%d samples @ %d Hz)",
            len(samples), WAKE_WORD_BEEP_SAMPLE_RATE,
        )
        try:
            self._pipeline.player.play_array(
                samples, WAKE_WORD_BEEP_SAMPLE_RATE, blocking=True
            )
        except AudioError:
            logger.exception("Beep playback failed")

    def _emit(self, state: str, payload: object = None) -> None:
        if self._on_state is None:
            return
        try:
            self._on_state(state, payload)
        except Exception:
            logger.exception("on_state callback raised")


__all__ = [
    "WakeWordListener",
    "contains_wake_word",
    "STATE_STANDBY_IDLE",
    "STATE_WAKE_HEARD",
    "STATE_WAKE_ACTIVE",
    "STATE_WAKE_PROCESSING",
    "STATE_WAKE_DISABLED",
]
