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

We intentionally keep this dumb: no streaming, no multi-language routing, no
VAD-inside-VAD. The pipeline already hands us a clean utterance WAV.
"""

from __future__ import annotations

import gc
import logging
import re
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
from core.base import STTProvider
from utils.errors import STTError

# Whisper expects audio at this rate. Anything else gets resampled by us.
_WHISPER_SR = 16000

logger = logging.getLogger(__name__)

# Известные фразы-галлюцинации русскоязычного Whisper (особенно large-v3)
# на тишине / очень коротком / шумном входе. Возникают потому, что модель
# обучалась на YouTube-субтитрах, где такие концовки частотны. Если
# транскрипция после нормализации совпадает ровно с одной из этих фраз —
# считаем это «неречью» и возвращаем пустую строку.
_HALLUCINATION_PHRASES: frozenset[str] = frozenset(
    _p.strip() for _p in [
        "продолжение следует",
        "спасибо за просмотр",
        "субтитры делал dimatorzok",
        "субтитры подготовил dimatorzok",
        "субтитры сделал dimatorzok",
        "субтитры подготовил",
        "субтитры сделал",
        "субтитры делал",
        "редактор субтитров",
        "корректор",
        "игорь дмитриев",
        "субтитры создавал dimatorzok",
        "подписывайтесь на канал",
        "ставьте лайки",
        "спасибо за внимание",
    ]
)

_NORMALIZE_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)


def _is_hallucination(text: str) -> bool:
    """True iff ``text`` после нормализации совпадает с известной фразой-галлюцинацией."""
    if not text:
        return False
    normalized = _NORMALIZE_RE.sub(" ", text.lower()).strip()
    normalized = " ".join(normalized.split())
    return normalized in _HALLUCINATION_PHRASES


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
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._language = language
        self._download_root = Path(download_root)
        self._model = None

    # ---- STTProvider ----

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

    def transcribe(self, audio_path: str) -> str:
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
                initial_prompt="Шурочка, Шура, Пайтон, Линукс.",
                condition_on_previous_text=False,
            )
        except Exception as exc:
            raise STTError(f"Whisper transcription failed for {p}: {exc}") from exc
        elapsed = time.monotonic() - t0

        text = (result.get("text") or "").strip()
        logger.info(
            "Transcription done in %.2fs: %r", elapsed, text[:120] + ("…" if len(text) > 120 else "")
        )
        if _is_hallucination(text):
            logger.info("Filtered Whisper hallucination phrase: %r → ''", text)
            return ""
        return text

    def unload_model(self) -> None:
        if self._model is None:
            return
        logger.info("Unloading Whisper (VRAM before: %s)", _vram_snapshot())
        del self._model
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
