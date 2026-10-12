"""Нейросетевой фильтр речи (Silero VAD) перед распознаванием.

Энергетический порог ``core/vad.py`` отличает громкое от тихого, но не
речь от щелчка мыши, клавиатуры, вентилятора или вдоха. Любой такой
всплеск открывал фрагмент, и Whisper получал полторы секунды почти чистой
тишины, на которой выдумывал «Продолжение следует». ``SpeechGate``
проверяет фрагмент моделью Silero VAD (CPU, доли миллисекунды на кадр):

* речи меньше ``min_speech_ms`` — фрагмент в распознавание не отправляется;
* речь есть — тишина по краям обрезается с запасом ``speech_pad_ms``,
  результат пишется во временный WAV рядом с исходным.

Если пакет ``silero-vad`` не установлен или модель не загрузилась, фильтр
пропускает звук без изменений (одно предупреждение в лог) — распознавание
работает как раньше, а очистку текста выполняет ``core/transcript_filter``.

Настройки читаются из секции ``[speech_gate]`` при каждом вызове, поэтому
переключатель в интерфейсе действует сразу.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

VAD_SAMPLE_RATE = 16000

# (audio_float32_16k, threshold, min_speech_ms, min_silence_ms, speech_pad_ms)
#   -> [(start_sample, end_sample), ...] в отсчётах 16 кГц
Detector = Callable[[np.ndarray, float, int, int, int], Sequence[tuple[int, int]]]


@dataclass(frozen=True)
class GateResult:
    """Итог проверки фрагмента.

    ``path`` — файл для распознавания (исходный или обрезанный) либо ``None``,
    если речи нет. ``reason``: speech, no_speech, too_short, disabled,
    unavailable, error.
    """

    path: str | None
    reason: str
    speech_ms: float = 0.0
    duration_ms: float = 0.0
    trimmed: bool = False

    @property
    def has_speech(self) -> bool:
        return self.path is not None


def _to_mono_float32(data: np.ndarray) -> np.ndarray:
    if data.ndim == 2:
        data = data.mean(axis=1)
    return np.ascontiguousarray(data, dtype=np.float32)


def _resample_linear(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Дешёвый ресемплинг для детектора; в распознавание идёт исходный звук."""
    if source_rate == target_rate or audio.size == 0:
        return audio
    length = max(1, int(round(audio.size * target_rate / source_rate)))
    positions = np.linspace(0, audio.size - 1, length)
    return np.interp(positions, np.arange(audio.size), audio).astype(np.float32)


def _silero_detector() -> Detector:
    """Загрузить Silero VAD из пакета ``silero-vad`` (веса внутри пакета)."""
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad

    model = load_silero_vad()

    def detect(audio, threshold, min_speech_ms, min_silence_ms, speech_pad_ms):
        with torch.no_grad():
            stamps = get_speech_timestamps(
                torch.from_numpy(audio),
                model,
                threshold=threshold,
                sampling_rate=VAD_SAMPLE_RATE,
                min_speech_duration_ms=min_speech_ms,
                min_silence_duration_ms=min_silence_ms,
                speech_pad_ms=speech_pad_ms,
            )
        return [(int(item["start"]), int(item["end"])) for item in stamps]

    return detect


class SpeechGate:
    """Фильтр речи перед STT. Потокобезопасен; модель грузится лениво."""

    def __init__(self, settings=None, *, detector: Detector | None = None,
                 detector_factory: Callable[[], Detector] | None = None) -> None:
        self._settings = settings
        self._detector = detector
        self._factory = detector_factory or _silero_detector
        self._lock = threading.Lock()
        self._unavailable: str | None = None

    # ---- state ----

    @property
    def settings(self):
        if self._settings is None:
            from config import settings

            return settings.speech_gate
        return self._settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.enabled)

    @property
    def available(self) -> bool:
        """Модель загружена или может быть загружена (без повторных попыток после сбоя)."""
        return self._unavailable is None

    @property
    def unavailable_reason(self) -> str | None:
        return self._unavailable

    def preload(self) -> bool:
        """Загрузить модель заранее (например, при запуске ассистента)."""
        if not self.enabled:
            return False
        with self._lock:
            return self._ensure_detector() is not None

    def _ensure_detector(self) -> Detector | None:
        if self._detector is not None:
            return self._detector
        if self._unavailable is not None:
            return None
        try:
            self._detector = self._factory()
            logger.info("Silero VAD загружен: фильтр речи перед распознаванием включён")
        except Exception as exc:  # ImportError, ошибки torch и т.п.
            self._unavailable = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Фильтр речи Silero VAD недоступен (%s). Звук передаётся в распознавание "
                "без проверки. Установите пакет: pip install silero-vad",
                self._unavailable,
            )
        return self._detector

    # ---- analysis ----

    def speech_regions(self, audio: np.ndarray, sample_rate: int) -> list[tuple[int, int]] | None:
        """Куски речи в отсчётах исходной частоты; ``None`` — детектор недоступен."""
        cfg = self.settings
        with self._lock:
            detector = self._ensure_detector()
            if detector is None:
                return None
            mono = _to_mono_float32(audio)
            prepared = _resample_linear(mono, sample_rate, VAD_SAMPLE_RATE)
            regions = detector(
                prepared,
                float(cfg.threshold),
                int(cfg.min_speech_ms),
                int(cfg.min_silence_ms),
                int(cfg.speech_pad_ms),
            )
        scale = sample_rate / VAD_SAMPLE_RATE
        total = len(audio)
        result = []
        for start, end in regions:
            start = max(0, min(total, int(round(start * scale))))
            end = max(0, min(total, int(round(end * scale))))
            if end > start:
                result.append((start, end))
        return result

    def filter_file(self, path: str | Path, *, purpose: str = "") -> GateResult:
        """Проверить WAV; вернуть путь для распознавания или ``None``.

        Обрезанный звук пишется в ``<имя>.speech.wav`` рядом с исходным —
        вызывающий удаляет его после распознавания (``GateResult.trimmed``).
        Ошибки чтения не скрывают исходную проблему: файл передаётся в
        распознавание как есть, и STT сообщит о ней сам.
        """
        source = str(path)
        if not self.enabled:
            return GateResult(source, "disabled")
        if self._detector is None and self._unavailable is not None:
            return GateResult(source, "unavailable")
        try:
            audio, sample_rate = sf.read(source, dtype="float32", always_2d=False)
        except Exception as exc:
            logger.debug("Фильтр речи: не удалось прочитать %s: %s", source, exc)
            return GateResult(source, "error")
        if audio.size == 0:
            return GateResult(source, "error")
        if audio.ndim == 2:
            audio = audio.mean(axis=1).astype(np.float32)
        duration_ms = len(audio) / sample_rate * 1000.0
        try:
            regions = self.speech_regions(audio, sample_rate)
        except Exception:
            logger.exception("Фильтр речи: сбой Silero VAD, звук передан без проверки")
            return GateResult(source, "error", duration_ms=duration_ms)
        if regions is None:
            return GateResult(source, "unavailable", duration_ms=duration_ms)

        cfg = self.settings
        speech_ms = sum(end - start for start, end in regions) / sample_rate * 1000.0
        label = f" ({purpose})" if purpose else ""
        if not regions:
            logger.info("Фильтр речи%s: речи нет в %.0f мс звука — распознавание пропущено",
                        label, duration_ms)
            return GateResult(None, "no_speech", 0.0, duration_ms)
        if speech_ms < cfg.min_speech_ms:
            logger.info("Фильтр речи%s: %.0f мс речи меньше порога %d мс — распознавание пропущено",
                        label, speech_ms, cfg.min_speech_ms)
            return GateResult(None, "too_short", speech_ms, duration_ms)

        start, end = regions[0][0], regions[-1][1]
        if start <= 0 and end >= len(audio):
            return GateResult(source, "speech", speech_ms, duration_ms)
        target = Path(source).with_name(Path(source).stem + ".speech.wav")
        try:
            sf.write(str(target), audio[start:end], sample_rate, subtype="PCM_16")
        except Exception:
            logger.exception("Фильтр речи: не удалось записать обрезанный звук")
            return GateResult(source, "speech", speech_ms, duration_ms)
        logger.debug("Фильтр речи%s: %.0f мс речи, обрезано %.0f → %.0f мс", label, speech_ms,
                     duration_ms, (end - start) / sample_rate * 1000.0)
        return GateResult(str(target), "speech", speech_ms, duration_ms, trimmed=True)


_shared: SpeechGate | None = None
_shared_lock = threading.Lock()


def get_speech_gate() -> SpeechGate:
    """Общий экземпляр для ассистента и речевых инструментов."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = SpeechGate()
        return _shared


def set_speech_gate(gate: SpeechGate | None) -> None:
    """Подменить общий экземпляр (тесты) или сбросить его (``None``)."""
    global _shared
    with _shared_lock:
        _shared = gate


def discard(result: GateResult) -> None:
    """Удалить обрезанный временный файл, созданный ``filter_file``."""
    if result.trimmed and result.path:
        try:
            Path(result.path).unlink(missing_ok=True)
        except OSError:
            logger.debug("Не удалось удалить %s", result.path, exc_info=True)


__all__ = [
    "GateResult",
    "SpeechGate",
    "VAD_SAMPLE_RATE",
    "discard",
    "get_speech_gate",
    "set_speech_gate",
]
