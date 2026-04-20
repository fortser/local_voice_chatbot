"""Text-to-speech via Silero (v4_ru / v5).

Why Silero alongside XTTS:

  * Нативная русская модель (xenia/baya/kseniya/aidar/eugene), звучит чище,
    чем мультиязычный XTTS — особенно на интонациях и ударениях.
  * ~60 МБ модель, real-time на CPU — освобождает GPU под Whisper, так что
    pipeline Stage 5 не требует GPU-swap.
  * Torch-only; грузится через ``torch.hub.load`` и кешируется в
    ``~/.cache/torch/hub/``. Первый запуск скачивает модель из интернета.

Ограничения:

  * Non-commercial (CC BY-NC-SA 4.0) — то же семейство ограничений, что и CPML
    у XTTS. Для личного ассистента подходит.
  * Нет voice-cloning. Для клонирования — оставить ``TTS_PROVIDER="xtts"``.
  * Максимум ~1000 символов на вызов ``apply_tts``. Для длинных ответов LLM
    (Stage 5) придётся резать по предложениям — это вне scope Stage 4.

Интерфейс такой же, как у ``XTSTTTS``, чтобы ``create_tts_provider`` был
drop-in — оркестрация не различает бэкенды.
"""

from __future__ import annotations

import gc
import logging
import re
import time
from pathlib import Path

import soundfile as sf

from config import (
    SILERO_DEVICE,
    SILERO_INTENSITY,
    SILERO_MODEL,
    SILERO_PUT_ACCENT,
    SILERO_PUT_STRESS_HOMO,
    SILERO_PUT_YO,
    SILERO_PUT_YO_HOMO,
    SILERO_SAMPLE_RATE,
    SILERO_SPEAKER,
    TTS_LANGUAGE,
)
from core.base import TTSProvider
from core.tts_utils import make_output_path
from utils.errors import TTSError

logger = logging.getLogger(__name__)

# Silero TTS поддерживает только эти частоты дискретизации.
_ALLOWED_SR = (8000, 24000, 48000)

# Silero v5_4_ru tacotron держит кириллический symbol_set: буквы, цифры,
# пробелы и базовая пунктуация. Любой другой символ (emoji, латиница,
# markdown-хедер, "#", ">" и т.п.) роняет apply_tts KeyError'ом.
# LLM регулярно возвращает такое — приходится скрабить вход, иначе Stage 5
# на каждом третьем ответе падает в fallback.
_SILERO_ALLOWED_RE = re.compile(r"[^а-яА-ЯёЁ0-9\s.,!?;:—–\-()\"'+]")
_WHITESPACE_RUN_RE = re.compile(r"\s+")


def _sanitize_for_silero(text: str) -> str:
    """Scrub chars the Russian tacotron doesn't know.

    Unknown chars are replaced with a space (rather than dropped) so word
    boundaries survive — "Ильич Lenin" → "Ильич ", not "ИльичLenin".
    """
    cleaned = _SILERO_ALLOWED_RE.sub(" ", text)
    return _WHITESPACE_RUN_RE.sub(" ", cleaned).strip()


# Лёгкий транслит EN→RU для случаев, когда LLM всё же вернула латиницу
# (даже с system-prompt'ом такое бывает: аббревиатуры, имена). Без транслита
# латинские рунты дропнулись бы в санитайзере — пользователь услышал бы
# дыры в ответе. Транслит фонетически приблизительный; для чистого UX
# правильнее всё равно заставить модель отвечать кириллицей.
_EN_RU_DIGRAPHS: tuple[tuple[str, str], ...] = (
    ("sch", "щ"),
    ("shch", "щ"),
    ("ch", "ч"),
    ("sh", "ш"),
    ("zh", "ж"),
    ("kh", "х"),
    ("ts", "ц"),
    ("ya", "я"),
    ("yu", "ю"),
    ("yo", "ё"),
    ("th", "т"),
    ("ph", "ф"),
    ("ck", "к"),
    ("qu", "кв"),
    ("ee", "и"),
    ("oo", "у"),
    ("ou", "у"),
    ("ai", "эй"),
    ("ay", "эй"),
    ("ey", "эй"),
    ("ie", "и"),
)

_EN_RU_SINGLE: dict[str, str] = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф",
    "g": "г", "h": "х", "i": "и", "j": "дж", "k": "к", "l": "л",
    "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р",
    "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "кс",
    "y": "й", "z": "з",
}

_LATIN_RUN_RE = re.compile(r"[A-Za-z]+")


def _transliterate_word(word: str) -> str:
    lower = word.lower()
    out: list[str] = []
    i = 0
    n = len(lower)
    while i < n:
        matched = False
        for digraph, cyr in _EN_RU_DIGRAPHS:
            ln = len(digraph)
            if lower[i:i + ln] == digraph:
                out.append(cyr)
                i += ln
                matched = True
                break
        if not matched:
            out.append(_EN_RU_SINGLE.get(lower[i], ""))
            i += 1
    result = "".join(out)
    if word and word[0].isupper() and result:
        result = result[0].upper() + result[1:]
    return result


def _transliterate_latin(text: str) -> str:
    """Replace every Latin-letter run with a Cyrillic phonetic approximation."""
    return _LATIN_RUN_RE.sub(lambda m: _transliterate_word(m.group(0)), text)


class SileroTTS(TTSProvider):
    """Silero TTS backend (русская модель по умолчанию, CPU-friendly)."""

    def __init__(
        self,
        model_id: str = SILERO_MODEL,
        speaker: str = SILERO_SPEAKER,
        language: str = TTS_LANGUAGE,
        device: str = SILERO_DEVICE,
        sample_rate: int = SILERO_SAMPLE_RATE,
        put_accent: bool = SILERO_PUT_ACCENT,
        put_yo: bool = SILERO_PUT_YO,
        put_stress_homo: bool = SILERO_PUT_STRESS_HOMO,
        put_yo_homo: bool = SILERO_PUT_YO_HOMO,
        intensity: int | None = SILERO_INTENSITY,
    ) -> None:
        if sample_rate not in _ALLOWED_SR:
            raise TTSError(
                f"Silero supports only {_ALLOWED_SR}, got {sample_rate}. "
                "Update SILERO_SAMPLE_RATE in config.py."
            )
        self._model_id = model_id
        self._speaker = speaker
        self._language = language
        self._device = device
        self._sample_rate = sample_rate
        self._put_accent = put_accent
        self._put_yo = put_yo
        self._put_stress_homo = put_stress_homo
        self._put_yo_homo = put_yo_homo
        self._intensity = intensity
        # Whether this model accepts v5-only kwargs (homograph/intensity).
        # Probed post-load so we can warn on mismatched config without
        # string-matching model names everywhere.
        self._supports_v5_kwargs = False
        self._model = None

    # ---- TTSProvider ----

    def load_model(self) -> None:
        if self._model is not None:
            logger.debug("Silero already loaded, skipping")
            return

        try:
            import torch
        except ImportError as exc:
            raise TTSError("torch is required for Silero TTS") from exc

        logger.info(
            "Loading Silero %s/%s on %s", self._language, self._model_id, self._device
        )
        t0 = time.monotonic()
        try:
            # torch.hub caches the model under ~/.cache/torch/hub/.
            # trust_repo=True suppresses the interactive prompt on first run.
            model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-models",
                model="silero_tts",
                language=self._language,
                speaker=self._model_id,
                trust_repo=True,
            )
            model.to(torch.device(self._device))
        except Exception as exc:
            raise TTSError(
                f"Failed to load Silero {self._language}/{self._model_id}: {exc}"
            ) from exc

        # Валидация спикера — Silero молча использует первого, если имя
        # неизвестно; ловим это явно.
        available = getattr(model, "speakers", None)
        if available and self._speaker not in available:
            raise TTSError(
                f"Silero speaker {self._speaker!r} не найден в модели "
                f"{self._model_id}. Доступны: {sorted(available)}"
            )

        # Detect v5-only kwargs by introspecting apply_tts signature — keeps
        # v4 users backward-compatible without version-string parsing.
        import inspect

        apply_params = inspect.signature(model.apply_tts).parameters
        self._supports_v5_kwargs = "intensity" in apply_params

        self._model = model
        elapsed = time.monotonic() - t0
        logger.info(
            "Silero loaded in %.1fs (speaker=%s, sr=%d, v5_kwargs=%s)",
            elapsed, self._speaker, self._sample_rate, self._supports_v5_kwargs,
        )

    def synthesize(self, text: str) -> str:
        if self._model is None:
            raise TTSError("Silero model not loaded — call load_model() first")

        raw = (text or "").strip()
        if not raw:
            raise TTSError("Cannot synthesize empty text")
        translit = _transliterate_latin(raw)
        clean = _sanitize_for_silero(translit)
        if not clean:
            raise TTSError(
                "Cannot synthesize — input contained no Silero-compatible chars "
                "(even after latin→cyrillic transliteration)."
            )
        if len(clean) != len(raw):
            logger.info(
                "Silero preprocess: %d → %d chars (translit + scrub emoji/markdown)",
                len(raw), len(clean),
            )

        out_path = make_output_path(prefix="silero")
        logger.info(
            "Synthesizing %d chars (speaker=%s, sr=%d) → %s",
            len(clean), self._speaker, self._sample_rate, out_path.name,
        )
        t0 = time.monotonic()
        kwargs: dict = {
            "text": clean,
            "speaker": self._speaker,
            "sample_rate": self._sample_rate,
            "put_accent": self._put_accent,
            "put_yo": self._put_yo,
        }
        # Homograph handling and question intensity are v5-only; v4 raises on them.
        if self._supports_v5_kwargs:
            kwargs["put_stress_homo"] = self._put_stress_homo
            kwargs["put_yo_homo"] = self._put_yo_homo
            if self._intensity is not None:
                kwargs["intensity"] = self._intensity
        try:
            audio = self._model.apply_tts(**kwargs)
        except Exception as exc:
            raise TTSError(f"Silero synthesis failed: {exc}") from exc

        # apply_tts returns a 1-D torch.Tensor of float32 in [-1, 1].
        samples = audio.detach().cpu().numpy()
        try:
            sf.write(str(out_path), samples, self._sample_rate, subtype="PCM_16")
        except Exception as exc:
            raise TTSError(f"Failed to write {out_path}: {exc}") from exc

        elapsed = time.monotonic() - t0
        logger.info("Synthesis done in %.2fs → %s", elapsed, out_path)
        return str(out_path)

    def unload_model(self) -> None:
        if self._model is None:
            return
        logger.info("Unloading Silero")
        del self._model
        self._model = None
        gc.collect()
        # Silero обычно живёт на CPU, но на cuda тоже чистим.
        try:
            import torch

            if torch.cuda.is_available() and self._device != "cpu":
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            logger.debug("torch cleanup skipped", exc_info=True)
        logger.info("Silero unloaded")

    @property
    def is_loaded(self) -> bool:
        return self._model is not None
