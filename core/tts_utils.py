"""TTS helper utilities.

Keeps ``core/tts.py`` focused on model I/O. Two concerns live here:

  * **Speaker reference resolution** — XTTS-v2 is a zero-shot voice cloner. It
    needs a short WAV of the target voice; ``config.TTS_SPEAKER_WAV`` points to
    it. We resolve the path (relative to ``BASE_DIR``) and fail early with a
    pointed error if it's missing, so the user doesn't hit a cryptic torchaudio
    stacktrace mid-synthesis.
  * **Output path generation** — unique, timestamped WAV names under
    ``config.TTS_OUTPUT_DIR`` so repeated runs don't clobber each other.
"""

from __future__ import annotations

import itertools
import logging
import time
from pathlib import Path

from config import BASE_DIR, TTS_OUTPUT_DIR, TTS_SPEAKER_WAV
from utils.errors import TTSError

logger = logging.getLogger(__name__)


def resolve_speaker_wav(override: str | Path | None = None) -> Path:
    """Return an absolute path to the speaker-reference WAV, or raise.

    ``override`` wins if given; otherwise we use ``config.TTS_SPEAKER_WAV``.
    Relative paths are resolved against ``BASE_DIR``.
    """
    raw = override if override is not None else TTS_SPEAKER_WAV
    if not raw:
        raise TTSError(
            "TTS_SPEAKER_WAV is empty — set it in config.py to a short WAV of "
            "the target voice (6–30 сек recommended)."
        )
    p = Path(raw)
    if not p.is_absolute():
        p = (BASE_DIR / p).resolve()
    if not p.is_file():
        raise TTSError(
            f"Speaker reference WAV not found: {p}. Update TTS_SPEAKER_WAV in "
            "config.py or place a short voice sample at this path."
        )
    return p


def prepare_output_dir() -> Path:
    """Ensure ``TTS_OUTPUT_DIR`` exists and return it as an absolute path."""
    p = Path(TTS_OUTPUT_DIR)
    if not p.is_absolute():
        p = (BASE_DIR / p).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


# Process-local counter to disambiguate sub-ms calls in the same timestamp.
_seq = itertools.count()


def make_output_path(prefix: str = "tts") -> Path:
    """Generate a unique WAV path under the TTS output dir."""
    out_dir = prepare_output_dir()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    seq = next(_seq)
    return out_dir / f"{prefix}_{stamp}_{seq:04d}.wav"
