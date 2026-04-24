"""Audio playback utilities.

Thin wrapper over ``sounddevice`` + ``soundfile`` that blocks until the WAV
finishes playing. Keeps one shared output stream concept simple — we don't
need mixing or queueing for the MVP (TTS output is one-at-a-time).
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from utils.errors import AudioError, CancelledError

logger = logging.getLogger(__name__)


class AudioPlayer:
    """Plays WAV files synchronously via the system default output device."""

    def __init__(self, device: int | str | None = None) -> None:
        self._device = device

    def play_file(
        self,
        path: str | Path,
        blocking: bool = True,
        cancel_event: threading.Event | None = None,
    ) -> None:
        """Play the WAV at ``path``.

        Raises:
            AudioError: if the file cannot be opened or playback fails.
            CancelledError: if ``cancel_event`` is set during playback.
        """
        p = Path(path)
        if not p.is_file():
            raise AudioError(f"Audio file not found: {p}")

        try:
            data, sr = sf.read(str(p), dtype="float32", always_2d=False)
        except Exception as exc:  # soundfile raises LibsndfileError, etc.
            raise AudioError(f"Failed to read {p}: {exc}") from exc

        duration = len(data) / sr if sr else 0.0
        logger.info("Playing %s (%.2fs @ %d Hz)", p.name, duration, sr)

        try:
            sd.play(data, samplerate=sr, device=self._device)
            if blocking:
                self._wait(cancel_event)
        except CancelledError:
            raise
        except Exception as exc:
            raise AudioError(f"Playback failed for {p}: {exc}") from exc

    def play_array(
        self,
        samples: np.ndarray,
        sample_rate: int,
        blocking: bool = True,
        cancel_event: threading.Event | None = None,
    ) -> None:
        """Play a raw ``numpy`` array. Useful for in-memory TTS output."""
        if samples.size == 0:
            logger.warning("play_array called with empty buffer")
            return
        try:
            sd.play(samples, samplerate=sample_rate, device=self._device)
            if blocking:
                self._wait(cancel_event)
        except CancelledError:
            raise
        except Exception as exc:
            raise AudioError(f"Playback failed: {exc}") from exc

    @staticmethod
    def _wait(cancel_event: threading.Event | None) -> None:
        """Block until playback finishes, или cancel_event → sd.stop() + raise."""
        if cancel_event is None:
            sd.wait()
            return
        # Poll at 50ms — достаточно быстро для UX, достаточно редко,
        # чтобы не греть CPU. sd.get_stream() возвращает текущий поток.
        while True:
            if cancel_event.is_set():
                sd.stop()
                raise CancelledError("Playback cancelled by user (Esc)")
            try:
                stream = sd.get_stream()
            except Exception:
                return
            if not stream.active:
                return
            time.sleep(0.05)

    @staticmethod
    def stop() -> None:
        """Stop any in-flight playback."""
        sd.stop()
