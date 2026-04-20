"""Audio preprocessing: RMS computation, normalisation, resampling.

The RMS utility here is the "file-level" flavour (read the whole WAV and
compute RMS in int16 domain) — compatible with the calibration numbers used in
voice_converter.py. The chunk-level RMS used by AudioStream in Stage 1b will
live alongside it and share the same int16 convention.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import soundfile as sf

from config import CHANNELS, SAMPLE_RATE
from utils.errors import AudioError

logger = logging.getLogger(__name__)

# Keep RMS scale consistent with int16 audio (max amplitude = 32767).
_INT16_MAX = 32767.0


def compute_rms(source: str | Path | np.ndarray, sample_rate: int | None = None) -> float:
    """Compute RMS of a WAV file (path) or an int16/float array.

    For file paths: reads at native SR and dtype. The returned value is on the
    int16 amplitude scale (0..32767) so thresholds stay comparable to the
    chunk-level RMS produced by AudioStream.
    """
    if isinstance(source, (str, Path)):
        samples, _ = sf.read(str(source), dtype="int16", always_2d=False)
    else:
        samples = source

    if samples.size == 0:
        return 0.0

    if samples.ndim == 2:
        samples = samples.mean(axis=1)

    if np.issubdtype(samples.dtype, np.floating):
        # float samples are in [-1.0, 1.0]; lift to int16 scale for parity.
        arr = samples.astype(np.float64) * _INT16_MAX
    else:
        arr = samples.astype(np.float64)

    return float(np.sqrt(np.mean(arr * arr)))


def normalize_audio(
    input_path: str | Path,
    output_path: str | Path,
    target_sample_rate: int = SAMPLE_RATE,
    target_channels: int = CHANNELS,
    peak_dbfs: float = -1.0,
) -> Path:
    """Normalise a WAV: resample, downmix, peak-normalise to ``peak_dbfs``.

    Writes 16-bit PCM WAV. Returns the output path.
    """
    in_path = Path(input_path)
    out_path = Path(output_path)
    if not in_path.is_file():
        raise AudioError(f"Input audio not found: {in_path}")

    data, sr = sf.read(str(in_path), dtype="float32", always_2d=False)
    if data.size == 0:
        raise AudioError(f"Input audio is empty: {in_path}")

    # Downmix to mono if needed.
    if data.ndim == 2 and target_channels == 1:
        data = data.mean(axis=1)

    # Resample if needed (librosa handles fractional ratios cleanly).
    if sr != target_sample_rate:
        import librosa  # local import: librosa pulls in a large dep tree

        data = librosa.resample(
            data.astype(np.float32),
            orig_sr=sr,
            target_sr=target_sample_rate,
        )
        sr = target_sample_rate

    # Peak-normalise: scale so max |sample| = target_peak.
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 0:
        target_peak = 10 ** (peak_dbfs / 20.0)
        data = data * (target_peak / peak)

    # Clip defensively, cast to int16.
    data = np.clip(data, -1.0, 1.0)
    pcm16 = (data * _INT16_MAX).astype(np.int16)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), pcm16, sr, subtype="PCM_16")
    logger.info(
        "Normalised %s -> %s (%d Hz, %d ch, peak %.1f dBFS)",
        in_path.name,
        out_path.name,
        sr,
        target_channels,
        peak_dbfs,
    )
    return out_path


def resample_audio(
    samples: np.ndarray,
    orig_sr: int,
    target_sr: int,
) -> np.ndarray:
    """Resample an in-memory float array to ``target_sr``."""
    if orig_sr == target_sr:
        return samples
    import librosa

    return librosa.resample(
        samples.astype(np.float32),
        orig_sr=orig_sr,
        target_sr=target_sr,
    )
