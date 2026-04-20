"""Background microphone reader with RMS monitoring.

Opens the mic exactly once and runs a daemon thread that:
  * reads fixed-size int16 chunks from ``sounddevice``
  * computes per-chunk RMS (int16 amplitude scale, 0..32767)
  * maintains a sliding-window ``noise_floor`` — but only while the consumer
    says ``speech_active == False`` (so a loud utterance never pollutes the
    running shush level)
  * emits ``(rms, percent)`` to a bounded queue (for UI level bar) and
    optionally to a user-supplied callback
  * exposes a ``chunk_queue`` that stays empty unless ``recording`` is on —
    that's how Stage 1c's VAD consumes audio without double-opening the mic

Pattern adapted from ``voice_converter.py``.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections import deque
from typing import Callable

import numpy as np
import sounddevice as sd

from config import CHANNELS, CHUNK_SIZE, NOISE_HISTORY_SIZE, SAMPLE_RATE
from utils.errors import AudioError

logger = logging.getLogger(__name__)

# int16 full-scale = 32767; dividing by 327.67 maps 0..32767 → 0..100.
_INT16_PER_PERCENT = 327.67


def _rms_to_percent(rms: float) -> int:
    return int(min(100.0, max(0.0, rms / _INT16_PER_PERCENT)))


LevelCallback = Callable[[float, int], None]


class AudioStream:
    """One long-lived microphone stream with RMS monitoring."""

    def __init__(
        self,
        on_level_update: LevelCallback | None = None,
        sample_rate: int = SAMPLE_RATE,
        channels: int = CHANNELS,
        chunk_size: int = CHUNK_SIZE,
        device: int | str | None = None,
    ) -> None:
        self._on_level_update = on_level_update
        self._sample_rate = sample_rate
        self._channels = channels
        self._chunk_size = chunk_size
        self._device = device

        self._stream: sd.RawInputStream | None = None
        self._thread: threading.Thread | None = None
        self._running = False

        # Shared state — always accessed under ``_lock``.
        self._lock = threading.Lock()
        self._current_rms = 0.0
        self._noise_history: deque[float] = deque(maxlen=NOISE_HISTORY_SIZE)
        self._noise_floor_rms = 0.0
        self._speech_active = False
        self._recording = False

        # Bounded: drops oldest UI events if the consumer lags.
        self._level_queue: queue.Queue[tuple[float, int]] = queue.Queue(maxsize=10)
        # Unbounded while recording is on — VAD drains fast. Cleared on start/stop of recording.
        self._chunk_queue: queue.Queue[tuple[np.ndarray, float]] = queue.Queue()

    # ---- lifecycle ----

    def start(self) -> None:
        if self._running:
            return
        try:
            self._stream = sd.RawInputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype="int16",
                blocksize=self._chunk_size,
                device=self._device,
            )
            self._stream.start()
        except Exception as exc:
            raise AudioError(f"Failed to open microphone: {exc}") from exc

        self._running = True
        self._thread = threading.Thread(
            target=self._audio_loop, name="AudioStream", daemon=True
        )
        self._thread.start()
        logger.info(
            "AudioStream started: %d Hz, %d ch, chunk=%d",
            self._sample_rate,
            self._channels,
            self._chunk_size,
        )

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                logger.exception("Error while closing mic stream")
            self._stream = None
        logger.info("AudioStream stopped")

    def __enter__(self) -> "AudioStream":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    # ---- public state ----

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_rms(self) -> float:
        with self._lock:
            return self._current_rms

    @property
    def noise_floor_rms(self) -> float:
        with self._lock:
            return self._noise_floor_rms

    @property
    def noise_floor_percent(self) -> int:
        return _rms_to_percent(self.noise_floor_rms)

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def chunk_size(self) -> int:
        return self._chunk_size

    @property
    def level_queue(self) -> "queue.Queue[tuple[float, int]]":
        return self._level_queue

    @property
    def chunk_queue(self) -> "queue.Queue[tuple[np.ndarray, float]]":
        """Chunks are only pushed here while ``recording`` is on (see Stage 1c)."""
        return self._chunk_queue

    def set_speech_active(self, active: bool) -> None:
        """Pause/resume noise-floor updates. Called by VAD during utterances."""
        with self._lock:
            self._speech_active = active

    def start_recording(self) -> None:
        """Begin feeding chunks into ``chunk_queue``. Drains any stale entries."""
        with self._lock:
            self._recording = True
        # Drain outside the lock to keep critical section short.
        self._drain_queue(self._chunk_queue)

    def stop_recording(self) -> None:
        with self._lock:
            self._recording = False

    # ---- internals ----

    def _audio_loop(self) -> None:
        assert self._stream is not None
        chunk = self._chunk_size
        while self._running:
            try:
                raw, overflowed = self._stream.read(chunk)
                if overflowed:
                    logger.warning("AudioStream input overflow — chunks dropped")
                samples = np.frombuffer(bytes(raw), dtype=np.int16)
                rms = _compute_rms_int16(samples)
            except Exception:
                logger.exception("AudioStream read failed; terminating loop")
                break

            with self._lock:
                self._current_rms = rms
                if not self._speech_active:
                    self._noise_history.append(rms)
                    if self._noise_history:
                        self._noise_floor_rms = float(
                            sum(self._noise_history) / len(self._noise_history)
                        )
                recording_now = self._recording

            percent = _rms_to_percent(rms)

            try:
                self._level_queue.put_nowait((rms, percent))
            except queue.Full:
                # Drop oldest, push newest — UI consumers care about "now".
                try:
                    self._level_queue.get_nowait()
                    self._level_queue.put_nowait((rms, percent))
                except queue.Empty:
                    pass

            if self._on_level_update is not None:
                try:
                    self._on_level_update(rms, percent)
                except Exception:
                    logger.exception("on_level_update callback raised")

            if recording_now:
                try:
                    # Copy: frombuffer returns a view over raw, which we'd overwrite.
                    self._chunk_queue.put_nowait((samples.copy(), rms))
                except queue.Full:
                    # chunk_queue is unbounded by construction, but guard anyway.
                    pass

    @staticmethod
    def _drain_queue(q: "queue.Queue") -> None:
        while True:
            try:
                q.get_nowait()
            except queue.Empty:
                return


def _compute_rms_int16(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    arr = samples.astype(np.float64)
    return float(np.sqrt(np.mean(arr * arr)))
