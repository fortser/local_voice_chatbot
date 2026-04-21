"""Voice Activity Detection built on top of ``AudioStream``.

Doesn't open the mic — reuses the long-lived stream from Stage 1b. Two public
operations:

* ``calibrate(duration)`` — listens to ``duration`` seconds of (intended)
  silence, records every chunk's RMS, sets ``threshold = max_rms * 1.8`` with a
  floor of ``MIN_ENERGY_THRESHOLD``. Returns ``(avg_noise_rms, threshold)``.

* ``record_until_silence(pause_threshold)`` — listens for the first chunk above
  threshold, then keeps accumulating until ``pause_threshold`` seconds have
  passed without a loud chunk. Writes a 16-bit mono WAV and returns its path.

Between calls the detector dynamically drifts the threshold toward the
observed floor (``threshold ← threshold·(1-d) + rms·d·r``), but only while
no speech is in progress — otherwise a single long utterance would relax the
threshold and miss the tail.
"""

from __future__ import annotations

import logging
import queue
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from config import (
    CALIBRATION_DURATION,
    CALIBRATION_MULTIPLIER,
    DYNAMIC_ENERGY_DAMPING,
    DYNAMIC_ENERGY_RATIO,
    MIN_ENERGY_THRESHOLD,
    PAUSE_THRESHOLD,
)
from core.audio_stream import AudioStream
from utils.errors import AudioError

logger = logging.getLogger(__name__)

_CHUNK_GET_TIMEOUT = 0.5  # sec — how long to wait for a chunk before re-checking deadlines


class VoiceActivityDetector:
    """RMS-threshold VAD driven by a shared ``AudioStream``."""

    def __init__(
        self,
        stream: AudioStream,
        *,
        calibration_multiplier: float = CALIBRATION_MULTIPLIER,
        min_threshold: float = MIN_ENERGY_THRESHOLD,
        pause_threshold: float = PAUSE_THRESHOLD,
        damping: float = DYNAMIC_ENERGY_DAMPING,
        ratio: float = DYNAMIC_ENERGY_RATIO,
    ) -> None:
        self._stream = stream
        self._calibration_multiplier = calibration_multiplier
        self._min_threshold = float(min_threshold)
        self._pause_threshold = pause_threshold
        self._damping = damping
        self._ratio = ratio

        self._threshold = float(min_threshold)
        self._noise_rms = 0.0
        # Значение порога сразу после последней успешной calibrate(). Нужно,
        # чтобы после долгого сканирующего цикла (где threshold дрейфует вниз
        # к MIN_ENERGY_THRESHOLD) можно было восстановить «свежий» порог
        # перед активной фазой — см. reset_threshold().
        self._calibrated_threshold: float | None = None

    # ---- public state ----

    @property
    def threshold(self) -> float:
        return self._threshold

    @property
    def noise_rms(self) -> float:
        return self._noise_rms

    def reset_threshold(self) -> None:
        """Вернуть порог к значению последней calibrate().

        Во время длинного цикла сканирования (wake-word) динамический drift
        тянет порог вниз к ``MIN_ENERGY_THRESHOLD``; при таком низком пороге
        случайный клик триггерит ложный onset. Вызывайте перед активной
        фазой, чтобы начать с «калибровочного» значения.
        """
        if self._calibrated_threshold is not None:
            self._threshold = self._calibrated_threshold

    # ---- operations ----

    def calibrate(self, duration: float = CALIBRATION_DURATION) -> tuple[float, float]:
        """Listen to ``duration`` seconds of silence, derive threshold.

        Returns ``(avg_noise_rms, threshold)``. Threshold is clamped below at
        ``min_threshold`` so a perfectly silent room can't give us a threshold
        of 5.
        """
        self._require_running()
        logger.info("VAD calibration: %.1fs", duration)

        self._stream.start_recording()
        rms_values: list[float] = []
        try:
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                try:
                    _samples, rms = self._stream.chunk_queue.get(
                        timeout=_CHUNK_GET_TIMEOUT
                    )
                except queue.Empty:
                    continue
                rms_values.append(rms)
        finally:
            self._stream.stop_recording()

        if not rms_values:
            raise AudioError("Calibration captured no audio — mic not producing chunks")

        max_rms = max(rms_values)
        if max_rms <= 0.0:
            # Every chunk came back as pure zeros → driver/device mismatch.
            # Typical on Windows when the selected Bluetooth input works through
            # DirectSound/WDM-KS but silently delivers empty buffers. Switch to
            # an MME variant of the same device, or set PREFERRED_INPUT_DEVICE
            # to an explicit index from ``python -m utils.audio_devices``.
            raise AudioError(
                f"Microphone returned {len(rms_values)} silent chunks (all RMS == 0). "
                "The selected input device is not delivering audio. "
                "Run 'python -m utils.audio_devices' and pick a different "
                "PREFERRED_INPUT_DEVICE (substring or index) in config.py."
            )
        avg_rms = float(sum(rms_values) / len(rms_values))
        threshold = max(
            max_rms * self._calibration_multiplier, self._min_threshold
        )
        self._noise_rms = avg_rms
        self._threshold = float(threshold)
        self._calibrated_threshold = float(threshold)
        logger.info(
            "Calibration done: samples=%d, max=%.1f, avg=%.1f, threshold=%.1f",
            len(rms_values),
            max_rms,
            avg_rms,
            threshold,
        )
        return avg_rms, self._threshold

    def record_until_silence(
        self,
        pause_threshold: float | None = None,
        max_duration: float = 30.0,
        output_path: str | Path | None = None,
        initial_silence_timeout: float | None = None,
    ) -> str:
        """Block until a full utterance is captured; write WAV; return path.

        FSM:
            idle → (rms > threshold) → recording
            recording → (silence ≥ pause_threshold) → stop → save

        ``initial_silence_timeout`` — if set and no speech onset within that
        many seconds, abort with :class:`AudioError` instead of waiting the
        full ``max_duration``. Used by the wake-word listener to poll
        short windows and by the "active" phase to give up on silent users.
        """
        self._require_running()
        pause = pause_threshold if pause_threshold is not None else self._pause_threshold
        sample_rate = self._stream.sample_rate

        self._stream.start_recording()
        self._stream.set_speech_active(False)

        collected: list[np.ndarray] = []
        speech_started = False
        silence_started_at: float | None = None
        t_start = time.monotonic()

        try:
            while True:
                elapsed = time.monotonic() - t_start
                if elapsed > max_duration:
                    logger.warning(
                        "record_until_silence: max_duration %.1fs reached", max_duration
                    )
                    break
                if (
                    not speech_started
                    and initial_silence_timeout is not None
                    and elapsed > initial_silence_timeout
                ):
                    # No onset within the grace period — bail without writing
                    # a WAV so the caller can treat this as "silence".
                    raise AudioError(
                        f"No speech onset within {initial_silence_timeout:.1f}s"
                    )

                try:
                    samples, rms = self._stream.chunk_queue.get(
                        timeout=_CHUNK_GET_TIMEOUT
                    )
                except queue.Empty:
                    continue

                above = rms > self._threshold

                if not speech_started:
                    if above:
                        speech_started = True
                        self._stream.set_speech_active(True)
                        collected.append(samples)
                        silence_started_at = None
                        logger.info(
                            "Speech onset: rms=%.1f threshold=%.1f", rms, self._threshold
                        )
                    else:
                        # Dynamic threshold drift while waiting for speech.
                        new_threshold = (
                            self._threshold * (1.0 - self._damping)
                            + rms * self._damping * self._ratio
                        )
                        self._threshold = max(new_threshold, self._min_threshold)
                else:
                    collected.append(samples)
                    if above:
                        silence_started_at = None
                    else:
                        if silence_started_at is None:
                            silence_started_at = time.monotonic()
                        elif time.monotonic() - silence_started_at >= pause:
                            logger.info(
                                "Silence ≥ %.1fs — stopping utterance", pause
                            )
                            break
        finally:
            self._stream.set_speech_active(False)
            self._stream.stop_recording()

        if not collected:
            raise AudioError("No speech captured before max_duration")

        audio = np.concatenate(collected)
        # Trim trailing silence to ~200 ms pad so Whisper doesn't waste context.
        audio = _trim_trailing_silence(
            audio,
            sample_rate=sample_rate,
            threshold=self._threshold,
            keep_ms=200,
            chunk_size=self._stream.chunk_size,
        )

        if output_path is None:
            tmp = tempfile.NamedTemporaryFile(
                prefix="utterance_", suffix=".wav", delete=False
            )
            tmp.close()
            out = Path(tmp.name)
        else:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)

        sf.write(str(out), audio, sample_rate, subtype="PCM_16")
        duration_s = len(audio) / sample_rate
        logger.info("Utterance saved: %s (%.2fs)", out, duration_s)
        return str(out)

    # ---- internals ----

    def _require_running(self) -> None:
        if not self._stream.is_running:
            raise AudioError("AudioStream must be started before using VAD")


def _trim_trailing_silence(
    audio: np.ndarray,
    *,
    sample_rate: int,
    threshold: float,
    keep_ms: int,
    chunk_size: int,
) -> np.ndarray:
    """Strip trailing chunks whose RMS is below ``threshold``, keep ``keep_ms`` pad."""
    if audio.size == 0:
        return audio

    n_chunks = audio.size // chunk_size
    if n_chunks == 0:
        return audio

    # Walk backwards to find the last chunk above threshold.
    last_speech_chunk = -1
    for i in range(n_chunks - 1, -1, -1):
        start = i * chunk_size
        end = start + chunk_size
        window = audio[start:end].astype(np.float64)
        rms = float(np.sqrt(np.mean(window * window))) if window.size else 0.0
        if rms > threshold:
            last_speech_chunk = i
            break

    if last_speech_chunk < 0:
        return audio  # nothing above threshold — bail, don't over-trim

    pad_samples = int(sample_rate * keep_ms / 1000)
    cutoff = (last_speech_chunk + 1) * chunk_size + pad_samples
    return audio[:cutoff]
