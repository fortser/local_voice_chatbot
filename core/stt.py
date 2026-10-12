"""Speech-to-text via OpenAI Whisper.

Single-model wrapper around ``openai-whisper``:

  * ``load_model()``  — pulls the model into VRAM (or RAM for CPU), logs before/
    after allocation so it's easy to spot leaks in ``logs/voice_ai.log``.
  * ``transcribe(path)`` — returns the decoded text. Language is fixed by
    ``config.WHISPER_LANGUAGE`` so Whisper's auto-detector doesn't randomly
    swap to English on short utterances.
  * ``unload_model()`` — drops the reference, ``gc.collect()`` + ``torch.cuda.
    empty_cache()`` so VRAM is actually freed for the GPU swap with XTTS in
    Stage 4.

We intentionally keep this dumb: no streaming, no multi-language routing.
Silence is screened out before us by ``core/speech_gate`` (Silero VAD); the
text Whisper returns is cleaned by ``core/transcript_filter`` using Whisper's
own per-segment scores (``no_speech_prob``, ``avg_logprob``,
``compression_ratio``) plus a list of typical subtitle hallucinations.
"""

from __future__ import annotations

import gc
import logging
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from config import (
    MODELS_DIR,
    SAMPLE_RATE,
    WHISPER_DEVICE,
    WHISPER_LANGUAGE,
    WHISPER_MODEL_SIZE,
)
from core.base import STTProvider, model_device
from core.transcript_filter import SegmentInfo, clean_transcript
from utils.errors import STTError

# Whisper expects audio at this rate. Anything else gets resampled by us.
_WHISPER_SR = 16000

logger = logging.getLogger(__name__)


def _vram_snapshot() -> str:
    """Return a short ``allocated / reserved`` string, or '(no cuda)'."""
    try:
        import torch

        if not torch.cuda.is_available():
            return "(no cuda)"
        alloc = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        return f"alloc={alloc:.2f} GiB, reserved={reserved:.2f} GiB"
    except Exception as exc:
        return f"(vram query failed: {exc})"


class WhisperSTT(STTProvider):
    """OpenAI Whisper backend (large-v3 by default)."""

    def __init__(
        self,
        model_size: str = WHISPER_MODEL_SIZE,
        device: str = WHISPER_DEVICE,
        language: str = WHISPER_LANGUAGE,
        download_root: str | Path = MODELS_DIR,
        filter_settings=None,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._language = language
        self._download_root = Path(download_root)
        self._filter_settings = filter_settings
        self._model = None

    @property
    def filter_settings(self):
        """Секция ``[stt.filter]``; читается при каждом вызове (переключатель в UI)."""
        if self._filter_settings is None:
            from config import settings

            return settings.stt.filter
        return self._filter_settings

    # ---- STTProvider ----

    @property
    def model_name(self) -> str:
        return self._model_size

    @property
    def device(self) -> str:
        return model_device(self._model, self._device)

    def load_model(self) -> None:
        if self._model is not None:
            logger.debug("Whisper already loaded, skipping")
            return

        self._download_root.mkdir(parents=True, exist_ok=True)

        try:
            import whisper
        except ImportError as exc:
            raise STTError(
                "openai-whisper is not installed — run `pip install -r requirements.txt`"
            ) from exc

        if str(self._device).split(":", 1)[0].lower() == "cuda":
            import torch

            if not torch.cuda.is_available():
                reason = (
                    "Установлена сборка PyTorch без поддержки CUDA."
                    if torch.version.cuda is None
                    else "PyTorch поддерживает CUDA, но видеокарта недоступна. Проверьте драйвер NVIDIA."
                )
                raise STTError(
                    f"Whisper настроен на {self._device}, но CUDA недоступна. {reason} "
                    f"Python: {sys.executable}. PyTorch: {torch.__version__}. "
                    "Для работы на NVIDIA установите CUDA-сборку PyTorch в этот Python. "
                    'Для работы на процессоре задайте whisper_device = "cpu" '
                    "в секции [stt] файла settings.toml."
                )

        logger.info(
            "Loading Whisper %s on %s (VRAM before: %s)",
            self._model_size,
            self._device,
            _vram_snapshot(),
        )
        t0 = time.monotonic()
        try:
            self._model = whisper.load_model(
                self._model_size,
                device=self._device,
                download_root=str(self._download_root),
            )
        except Exception as exc:
            raise STTError(
                f"Failed to load Whisper {self._model_size} on {self._device}: {exc}"
            ) from exc
        elapsed = time.monotonic() - t0
        logger.info(
            "Whisper loaded in %.1fs (VRAM after: %s)", elapsed, _vram_snapshot()
        )

    def transcribe(self, audio_path: str, *, profile: str = "command") -> str:
        if profile not in {"command", "dictation"}:
            raise STTError(f"Unknown transcription profile: {profile}")
        if self._model is None:
            raise STTError("Whisper model not loaded — call load_model() first")

        p = Path(audio_path)
        if not p.is_file():
            raise STTError(f"Audio file not found: {p}")

        logger.info("Transcribing %s (lang=%s)", p.name, self._language)
        t0 = time.monotonic()
        try:
            # Skip whisper.audio.load_audio (it shells out to ffmpeg, which we
            # don't require). Our pipeline already writes 16 kHz mono PCM16,
            # so we just read it into float32 [-1, 1] and hand whisper the array.
            audio = _load_audio_float32(p)
            # initial_prompt даёт Whisper контекст: на одиночных словах
            # (например wake-word «Шурочка») без подсказки модель склонна
            # подменять ввод частотными фразами из тренировочного корпуса
            # («Спасибо», «Продолжение следует»). Подсказка с нужными
            # именами резко уменьшает такие подмены.
            # condition_on_previous_text=False — каждый вызов независим,
            # без переноса «воображаемого контекста» между утеrances.
            result = self._model.transcribe(
                audio,
                language=self._language,
                fp16=(self._device == "cuda"),
                initial_prompt="Шурочка, Шура, Пайтон, Линукс." if profile == "command" else None,
                condition_on_previous_text=False,
            )
        except Exception as exc:
            raise STTError(f"Whisper transcription failed for {p}: {exc}") from exc
        elapsed = time.monotonic() - t0

        text = (result.get("text") or "").strip()
        logger.info(
            "Transcription done in %.2fs: %r", elapsed, text[:120] + ("…" if len(text) > 120 else "")
        )
        segments = [
            SegmentInfo.from_whisper(segment)
            for segment in (result.get("segments") or [])
            if isinstance(segment, dict)
        ]
        for segment in segments:
            logger.debug("Whisper segment %r: %s", segment.text.strip()[:80], segment.describe())
        outcome = clean_transcript(
            text, segments=segments or None, profile=profile, cfg=self.filter_settings
        )
        if outcome.changed:
            logger.info(
                "Фильтр галлюцинаций (%s): %r → %r; %s",
                profile, text[:120], outcome.text[:120], "; ".join(outcome.removed),
            )
        return outcome.text

    def unload_model(self) -> None:
        if self._model is None:
            return
        logger.info("Unloading Whisper (VRAM before: %s)", _vram_snapshot())
        self._model = None
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            logger.debug("torch cleanup skipped", exc_info=True)
        logger.info("Whisper unloaded (VRAM after: %s)", _vram_snapshot())

    # ---- misc ----

    @property
    def is_loaded(self) -> bool:
        return self._model is not None


def _load_audio_float32(path: Path) -> np.ndarray:
    """Read a WAV into mono float32 at 16 kHz — the format whisper wants.

    Bypasses ``whisper.audio.load_audio`` (which shells out to ffmpeg); our
    recordings are already PCM16/16k/mono, so this is a straight cast. If a
    user feeds a non-16k file, we resample via librosa to stay compatible.
    """
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if data.size == 0:
        raise STTError(f"Audio file is empty: {path}")
    if data.ndim == 2:
        data = data.mean(axis=1)
    if sr != _WHISPER_SR:
        import librosa

        data = librosa.resample(data, orig_sr=sr, target_sr=_WHISPER_SR)
    return np.ascontiguousarray(data, dtype=np.float32)
