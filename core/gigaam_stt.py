"""Опциональное распознавание речи через GigaAM-v3 (Сбер, только русский).

Включается в ``settings.toml``::

    [stt]
    provider = "gigaam"

или на странице «Настройки» нового интерфейса (после перезапуска).

Почему это полезно: GigaAM — модель с декодером CTC/RNN-T без текстового
«языкового» декодера, обученного на субтитрах, поэтому на тишине она не
выдумывает целые фразы вроде «Продолжение следует». По замерам авторов
средняя ошибка на русских наборах заметно ниже, чем у Whisper. Варианты
``e2e_rnnt`` / ``e2e_ctc`` сразу расставляют пунктуацию и заглавные буквы.

Загрузка — через ``transformers`` (``trust_remote_code``) из репозитория
``ai-sage/GigaAM-v3``; веса скачиваются при первом запуске в
``models/gigaam``. Официальный пакет ``gigaam`` не используется: он требует
numpy 2.x, а проект закреплён на numpy 1.26 ради синтеза речи. Зависимости —
``requirements-gigaam.txt``.

Особенности, которые здесь учтены:

* модель читает звук через ffmpeg — загрузчик подменяется на чтение
  ``soundfile`` из памяти, ffmpeg не нужен;
* один вызов ограничен 25 с — длинный звук режется по самым тихим местам;
* оценок уверенности по сегментам нет, поэтому к тексту применяются только
  схлопывание повторов и удаление фраз субтитров.
"""

from __future__ import annotations

import gc
import logging
import sys
import time
from pathlib import Path

import numpy as np

from config import MODELS_DIR
from core.base import STTProvider, model_device
from core.stt import _load_audio_float32, _vram_snapshot
from core.transcript_filter import clean_transcript
from utils.errors import STTError

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000

INSTALL_HINT = (
    "Для GigaAM-v3 установите зависимости в тот же Python: "
    "pip install -r requirements-gigaam.txt"
)


def split_audio(audio: np.ndarray, sample_rate: int = SAMPLE_RATE, *,
                max_seconds: float = 22.0, search_seconds: float = 4.0,
                frame_ms: int = 50) -> list[np.ndarray]:
    """Разрезать звук на куски не длиннее ``max_seconds`` по самым тихим местам.

    Точка разреза ищется в последних ``search_seconds`` каждого окна: кадр с
    минимальной энергией. Порядок и все отсчёты сохраняются.
    """
    limit = int(max_seconds * sample_rate)
    if limit <= 0 or len(audio) <= limit:
        return [audio] if len(audio) else []
    frame = max(1, int(sample_rate * frame_ms / 1000))
    search = max(frame, int(search_seconds * sample_rate))
    chunks: list[np.ndarray] = []
    start = 0
    while len(audio) - start > limit:
        end = start + limit
        low = max(start + frame, end - search)
        window = audio[low:end]
        count = len(window) // frame
        if count > 0:
            energy = (window[:count * frame].astype(np.float64).reshape(count, frame) ** 2).mean(axis=1)
            # Самый поздний из самых тихих кадров: куски выходят длиннее.
            quietest = count - 1 - int(np.argmin(energy[::-1]))
            cut = low + quietest * frame + frame // 2
        else:
            cut = end
        cut = min(max(cut, start + frame), end)
        chunks.append(audio[start:cut])
        start = cut
    chunks.append(audio[start:])
    return [chunk for chunk in chunks if len(chunk)]


def _result_text(result) -> str:
    """GigaAM возвращает строку или объект с полем ``text`` — в зависимости от версии."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    text = getattr(result, "text", None)
    if text is None and isinstance(result, dict):
        text = result.get("text")
    return str(text or "")


def _array_audio_loader(original):
    """Загрузчик звука для GigaAM: массив из памяти или файл через soundfile."""

    def load_audio(audio, sample_rate: int = SAMPLE_RATE, *args, **kwargs):
        import torch

        if isinstance(audio, np.ndarray):
            data = audio
        elif isinstance(audio, torch.Tensor):
            return audio.float()
        else:
            try:
                data = _load_audio_float32(Path(audio))
            except Exception:
                if original is None:
                    raise
                return original(audio, sample_rate, *args, **kwargs)
        return torch.from_numpy(np.ascontiguousarray(data, dtype=np.float32))

    load_audio.__shura_patched__ = True
    return load_audio


class GigaAMSTT(STTProvider):
    """GigaAM-v3 из Hugging Face (``ai-sage/GigaAM-v3``)."""

    def __init__(
        self,
        model_id: str | None = None,
        revision: str | None = None,
        device: str | None = None,
        download_root: str | Path | None = None,
        max_chunk_s: float | None = None,
        filter_settings=None,
    ) -> None:
        cfg = None
        if None in (model_id, revision, device, max_chunk_s):
            from config import settings

            cfg = settings.stt.gigaam
        self._model_id = model_id or cfg.model
        self._revision = revision or cfg.revision
        self._device = device or cfg.device
        self._max_chunk_s = float(max_chunk_s if max_chunk_s is not None else cfg.max_chunk_s)
        self._download_root = Path(download_root) if download_root else Path(MODELS_DIR) / "gigaam"
        self._filter_settings = filter_settings
        self._model = None
        self._array_input = False

    # ---- metadata ----

    @property
    def model_name(self) -> str:
        return f"GigaAM-v3 {self._revision}"

    @property
    def device(self) -> str:
        return model_device(self._model, self._device)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def filter_settings(self):
        if self._filter_settings is None:
            from config import settings

            return settings.stt.filter
        return self._filter_settings

    # ---- lifecycle ----

    def load_model(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModel
        except ImportError as exc:
            raise STTError(f"{INSTALL_HINT}. Не найден модуль: {exc.name}") from exc

        if str(self._device).split(":", 1)[0].lower() == "cuda" and not torch.cuda.is_available():
            raise STTError(
                f"GigaAM настроен на {self._device}, но CUDA недоступна. "
                f"Python: {sys.executable}. PyTorch: {torch.__version__}. "
                'Для работы на процессоре задайте device = "cpu" в секции [stt.gigaam] '
                "файла settings.toml."
            )

        self._download_root.mkdir(parents=True, exist_ok=True)
        logger.info("Loading GigaAM %s (%s) on %s (VRAM before: %s)",
                    self._model_id, self._revision, self._device, _vram_snapshot())
        started = time.monotonic()
        try:
            model = AutoModel.from_pretrained(
                self._model_id,
                revision=self._revision,
                trust_remote_code=True,
                cache_dir=str(self._download_root),
            )
            model = model.to(self._device)
            model.eval()
        except ImportError as exc:
            raise STTError(f"{INSTALL_HINT}. Не найден модуль: {exc.name}") from exc
        except Exception as exc:
            raise STTError(
                f"Не удалось загрузить GigaAM {self._model_id} ({self._revision}) "
                f"на {self._device}: {exc}"
            ) from exc
        self._array_input = self._patch_audio_loader(model)
        self._model = model
        logger.info("GigaAM loaded in %.1fs (VRAM after: %s, ffmpeg %s)",
                    time.monotonic() - started, _vram_snapshot(),
                    "не нужен" if self._array_input else "используется")

    @staticmethod
    def _patch_audio_loader(model) -> bool:
        """Подменить ``load_audio`` в модуле модели, чтобы не вызывать ffmpeg."""
        patched = False
        modules = {type(model).__module__}
        inner = getattr(model, "model", None)
        if inner is not None:
            modules.add(type(inner).__module__)
        for name in modules:
            module = sys.modules.get(name)
            original = getattr(module, "load_audio", None) if module else None
            if original is None:
                continue
            if not getattr(original, "__shura_patched__", False):
                module.load_audio = _array_audio_loader(original)
            patched = True
        if not patched:
            logger.warning("GigaAM: загрузчик звука не найден — нужен ffmpeg в PATH")
        return patched

    def unload_model(self) -> None:
        if self._model is None:
            return
        logger.info("Unloading GigaAM (VRAM before: %s)", _vram_snapshot())
        self._model = None
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            logger.debug("torch cleanup skipped", exc_info=True)

    # ---- recognition ----

    def _transcribe_chunk(self, chunk: np.ndarray, workdir: Path | None) -> str:
        import torch

        if self._array_input:
            argument = chunk
        else:
            import soundfile as sf

            assert workdir is not None
            argument = str(workdir / f"chunk_{time.monotonic_ns()}.wav")
            sf.write(argument, chunk, SAMPLE_RATE, subtype="PCM_16")
        with torch.inference_mode():
            return _result_text(self._model.transcribe(argument)).strip()

    def transcribe(self, audio_path: str, *, profile: str = "command") -> str:
        if profile not in {"command", "dictation"}:
            raise STTError(f"Unknown transcription profile: {profile}")
        if self._model is None:
            raise STTError("GigaAM model not loaded — call load_model() first")
        path = Path(audio_path)
        if not path.is_file():
            raise STTError(f"Audio file not found: {path}")
        audio = _load_audio_float32(path)
        chunks = split_audio(audio, SAMPLE_RATE, max_seconds=self._max_chunk_s)
        logger.info("Transcribing %s with GigaAM (%d part(s))", path.name, len(chunks))
        started = time.monotonic()
        texts: list[str] = []
        try:
            if self._array_input:
                texts = [self._transcribe_chunk(chunk, None) for chunk in chunks]
            else:
                import tempfile

                with tempfile.TemporaryDirectory(prefix="gigaam-") as directory:
                    texts = [self._transcribe_chunk(chunk, Path(directory)) for chunk in chunks]
        except STTError:
            raise
        except Exception as exc:
            raise STTError(f"GigaAM transcription failed for {path}: {exc}") from exc
        text = " ".join(part for part in texts if part).strip()
        logger.info("GigaAM done in %.2fs: %r", time.monotonic() - started, text[:120])
        outcome = clean_transcript(text, segments=None, profile=profile, cfg=self.filter_settings)
        if outcome.changed:
            logger.info("Фильтр галлюцинаций (%s, GigaAM): %r → %r; %s",
                        profile, text[:120], outcome.text[:120], "; ".join(outcome.removed))
        return outcome.text


__all__ = ["GigaAMSTT", "INSTALL_HINT", "split_audio"]
