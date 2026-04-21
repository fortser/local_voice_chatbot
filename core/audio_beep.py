"""In-memory beep generation for wake-word activation/cancel signals.

Pure sine with short linear fade-in / fade-out to avoid clicks on start/end.
Returned as float32 in [-1, 1] — the shape ``AudioPlayer.play_array`` expects.
"""

from __future__ import annotations

import numpy as np


def generate_beep(
    freq_hz: float,
    duration_ms: float,
    sample_rate: int = 24000,
    amplitude: float = 0.3,
    fade_ms: float = 10.0,
) -> np.ndarray:
    """Return a mono sine wave as float32.

    The fade window is applied to both ends so the speaker doesn't pop.
    ``amplitude`` stays well below 1.0 by default — the signal is meant to
    be a short cue, not to overlap speech.
    """
    n = max(1, int(sample_rate * duration_ms / 1000.0))
    t = np.arange(n, dtype=np.float32) / float(sample_rate)
    wave = amplitude * np.sin(2.0 * np.pi * freq_hz * t).astype(np.float32)

    fade_n = min(n // 2, max(1, int(sample_rate * fade_ms / 1000.0)))
    if fade_n > 0:
        ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
        wave[:fade_n] *= ramp
        wave[-fade_n:] *= ramp[::-1]
    return wave


__all__ = ["generate_beep"]
