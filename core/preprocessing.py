"""Audio preprocessing: RMS computation, normalisation, resampling, denoise.

The RMS utility here is the "file-level" flavour (read the whole WAV and
compute RMS in int16 domain) — compatible with the calibration numbers used in
voice_converter.py. The chunk-level RMS used by AudioStream in Stage 1b will
live alongside it and share the same int16 convention.

``enhance_audio()`` is a lazy wrapper around DeepFilterNet — нейросетевой
денойзер, применяется к WAV от VAD перед STT, чтобы Whisper получал
более чистый сигнал (особенно критично для BT-гарнитур через HFP-кодек).
"""

from __future__ import annotations

import logging
import threading
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


# ====== DeepFilterNet denoise (Этап 9) ======
#
# Нейросетевое шумоподавление перед Whisper. Главный клиент — владельцы
# BT-гарнитур: HFP-кодек режет полосу и добавляет нестационарный шум,
# на котором Whisper галлюцинирует. DFN предсказывает маску чистой речи
# в спектральной области и возвращает WAV, максимально близкий к
# студийному — это условия, на которых Whisper обучался.
#
# Модель грузится один раз (lazy singleton) и держится в памяти на CPU.
# На VRAM не лезем специально: у нас уже идёт свап Whisper↔XTTS на CUDA,
# третий житель VRAM сломает хрупкий баланс.

_DF_LOCK = threading.Lock()
_DF_STATE: tuple | None = None  # (model, df_state, sr)


def _get_deepfilter():
    """Lazy-инициализация DeepFilterNet. Thread-safe, одна загрузка на процесс.

    Returns ``(model, df_state, sr)`` или поднимает ``AudioError`` если
    пакет не установлен / не загрузился.
    """
    global _DF_STATE
    if _DF_STATE is not None:
        return _DF_STATE
    with _DF_LOCK:
        if _DF_STATE is not None:
            return _DF_STATE
        try:
            from df.enhance import init_df
        except ImportError as exc:
            raise AudioError(
                "DeepFilterNet не установлен. Выполните: pip install deepfilternet"
            ) from exc

        import os
        import torch
        from config import DEEPFILTER_DEVICE, LOGS_DIR

        # DFN по умолчанию пишет enhance.log в CWD — уводим в logs/, чтобы
        # не засорять корень проекта.
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        df_log = str(LOGS_DIR / "deepfilternet.log")

        device = DEEPFILTER_DEVICE.lower()
        logger.info("DeepFilterNet: загрузка модели (target=%s)...", device)

        # DFN внутри `enhance()` кеширует устройство через get_device() и
        # кладёт признаки туда же, куда модель. Простое `model.to('cpu')`
        # после init_df() НЕ работает — фичи всё равно уезжают на CUDA
        # (ошибка "Input type (torch.cuda.FloatTensor) and weight type ...").
        # Единственный надёжный способ усадить DFN на CPU — временно
        # скрыть CUDA от torch на момент init_df(), чтобы get_device()
        # закешировал CPU. Whisper уже загружен выше и свой device держит
        # в собственном кеше — ему это не мешает.
        saved_cuda_visible = None
        cuda_was_available = torch.cuda.is_available()
        if device == "cpu" and cuda_was_available:
            saved_cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES")
            os.environ["CUDA_VISIBLE_DEVICES"] = ""
            # Сбросить кеш torch, чтобы is_available() пересчитался
            try:
                torch.cuda.is_available.cache_clear()  # type: ignore[attr-defined]
            except AttributeError:
                pass

        try:
            model, df_state, _ = init_df(log_file=df_log)
        except Exception as exc:
            raise AudioError(f"DeepFilterNet: init_df failed: {exc}") from exc
        finally:
            if saved_cuda_visible is not None:
                os.environ["CUDA_VISIBLE_DEVICES"] = saved_cuda_visible
            elif device == "cpu" and cuda_was_available:
                os.environ.pop("CUDA_VISIBLE_DEVICES", None)

        model.eval()
        sr = int(df_state.sr())
        _DF_STATE = (model, df_state, sr)
        logger.info("DeepFilterNet: модель загружена (device=%s), sr=%d",
                    device, sr)
        return _DF_STATE


def preload_deepfilter() -> None:
    """Прогреть модель DFN в фоне, чтобы первая фраза не ловила задержку.

    Вызывать из ``VoicePipeline.start()`` если ``USE_DEEPFILTER=True``.
    Если загрузка упала — логируем и тихо пропускаем, пайплайн дальше
    сам сработает fallback'ом на исходный WAV.
    """
    try:
        _get_deepfilter()
    except AudioError as exc:
        logger.warning("DeepFilterNet preload failed: %s", exc)


def enhance_audio(
    input_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Прогнать WAV через DeepFilterNet и сохранить очищенный файл.

    Работает на CPU, добавляет ~15–50 мс на типичную команду 1–3 секунды.
    При любой ошибке (модель не загрузилась, битый WAV) поднимает
    ``AudioError`` — вызывающий код должен упасть в fallback на исходный
    WAV, а не ломать турн.
    """
    import torch
    from df.enhance import enhance, load_audio, save_audio

    in_path = Path(input_path)
    out_path = Path(output_path)
    if not in_path.is_file():
        raise AudioError(f"enhance_audio: input not found: {in_path}")

    model, df_state, _ = _get_deepfilter()
    try:
        audio, _ = load_audio(str(in_path), sr=df_state.sr())
        with torch.no_grad():
            enhanced = enhance(model, df_state, audio)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        save_audio(str(out_path), enhanced, df_state.sr())
    except Exception as exc:
        raise AudioError(f"enhance_audio failed: {exc}") from exc
    return out_path
