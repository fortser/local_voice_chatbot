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

from bootstrap import bootstrap
from config import (
    CALIBRATION_DURATION,
    IPC_HOST,
    IPC_PORT,
    SILERO_DEVICE,
    TTS_DEVICE,
    TTS_PROVIDER,
)
from core import create_llm_provider, create_stt_provider, create_tts_provider
from core.audio_output import AudioPlayer
from core.audio_stream import AudioStream
from core.vad import VoiceActivityDetector
from utils.errors import (
    AudioError,
    LLMError,
    STTError,
    TTSError,
    VoiceAIError,
)

logger = logging.getLogger(__name__)

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
        # One lock shared by the console REPL and every IPC handler — prevents
        # overlapping mic access, overlapping GPU-swap, overlapping model I/O.
        self._lock = threading.Lock()

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    # ---- lifecycle ----

    def start(self) -> None:
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
            noise, threshold = self._vad.calibrate()
            print(
                f"  шум={noise:.0f} RMS, порог={threshold:.0f} "
                f"(за {time.monotonic() - t0:.1f}с)"
            )

            print("Загружаю Whisper…")
            t0 = time.monotonic()
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

    def process_voice_input(self) -> TurnResult:
        assert self._vad is not None, "start() must be called first"
        # Acquire the shared lock for the whole turn — blocks IPC handlers
        # from touching the mic/models until we're done. Console callers
        # accept this blocking; they're interactive anyway.
        with self._lock:
            return self._process_voice_input_locked()

    def _process_voice_input_locked(self) -> TurnResult:
        assert self._vad is not None
        t_total = time.monotonic()

        # 1. Record
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
        print("📝 Распознаю…")
        try:
            user_text = self._stt.transcribe(wav_in).strip()
        except STTError as exc:
            logger.exception("STT failed")
            return TurnResult(
                "", "", wav_in, None,
                time.monotonic() - t_total,
                f"stt: {exc}",
            )

        if not user_text:
            wav_out = self._speak_safely(FALLBACK_NO_SPEECH)
            return TurnResult(
                "", FALLBACK_NO_SPEECH, wav_in, wav_out,
                time.monotonic() - t_total,
            )

        print(f"   «{user_text}»")

        # 3. LLM
        print("🧠 Думаю…")
        try:
            llm_text = self._llm.generate(user_text).strip()
        except LLMError as exc:
            logger.exception("LLM failed")
            wav_out = self._speak_safely(FALLBACK_LLM_ERROR)
            return TurnResult(
                user_text, FALLBACK_LLM_ERROR, wav_in, wav_out,
                time.monotonic() - t_total,
                f"llm: {exc}",
            )
        except VoiceAIError as exc:  # e.g. ConfigError from LM Studio auto-resolve
            logger.exception("LLM failed (config)")
            wav_out = self._speak_safely(FALLBACK_LLM_ERROR)
            return TurnResult(
                user_text, FALLBACK_LLM_ERROR, wav_in, wav_out,
                time.monotonic() - t_total,
                f"llm-config: {exc}",
            )

        if not llm_text:
            wav_out = self._speak_safely(FALLBACK_EMPTY_LLM)
            return TurnResult(
                user_text, FALLBACK_EMPTY_LLM, wav_in, wav_out,
                time.monotonic() - t_total,
            )

        print(f"   «{llm_text}»")

        # 4+5. TTS + playback
        wav_out = self._speak_safely(llm_text)
        return TurnResult(
            user_text, llm_text, wav_in, wav_out,
            time.monotonic() - t_total,
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
                    wav_out = self._speak(llm_text, play=False)
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
                wav_out = self._speak(llm_text, play=False)
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

    # ---- TTS helpers ----

    def _speak(self, text: str, *, play: bool = True) -> str:
        """Synthesize. Optionally play. GPU-swap when required. Raises on failure.

        ``play=False`` is the IPC path: the caller just wants a WAV on disk
        to fetch or serve; playing it locally would be surprising.
        """
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

        if play:
            print("🔊 Воспроизвожу…")
            self._player.play_file(wav)
        return wav

    def _speak_safely(self, text: str) -> str | None:
        """Like :meth:`_speak` but swallows TTS/playback errors into a warning."""
        try:
            return self._speak(text)
        except TTSError as exc:
            logger.exception("TTS failed")
            print(f"⚠ TTS ошибка: {exc}")
        except AudioError as exc:
            logger.exception("Playback failed")
            print(f"⚠ воспроизведение не удалось: {exc}")
        return None


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
        choices=["console", "ipc"],
        default="console",
        help=(
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

    if args.mode == "console":
        return run_console_mode(
            with_ipc=not args.no_ipc, ipc_host=args.host, ipc_port=args.port
        )
    if args.mode == "ipc":
        return run_ipc_mode(ipc_host=args.host, ipc_port=args.port)

    return 1


if __name__ == "__main__":
    sys.exit(main())
