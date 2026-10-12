"""Очистка результата распознавания от галлюцинаций.

Whisper обучен на субтитрах YouTube, поэтому на тишине, шуме и обрывках
речи он «дописывает» типовые концовки роликов: «Продолжение следует»,
«Спасибо за просмотр», «Субтитры сделал DimaTorzok». Здесь три слоя защиты,
независимые от модели и железа (тестируются без torch):

1. ``filter_segments`` — отбрасывает сегменты Whisper по его собственным
   оценкам: ``no_speech_prob`` (модель считает, что речи не было),
   ``avg_logprob`` (уверенность в тексте) и ``compression_ratio``
   (зацикленный повтор).
2. ``deloop`` — схлопывает фразу, повторённую подряд больше
   ``max_repeats`` раз («да да да да да да» → «да»).
3. ``strip_hallucinations`` — удаляет известные фразы субтитров:
   «сильные» (в обычной речи не встречаются) — как отдельное предложение
   и в хвосте текста; «слабые» («Спасибо», «Пока») — только если весь
   текст состоит из них и есть признак неречи (профиль команд или сомнение
   Whisper). Так диктовка «Спасибо.» после реальной речи не теряется.

Точка входа — ``clean_transcript``. Конфигурация — секция ``[stt.filter]``
(``config_model.STTFilterSettings``); подходит любой объект с теми же
атрибутами.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Словари галлюцинаций (в нормализованном виде: нижний регистр, «е» вместо
# «ё», без пунктуации, одиночные пробелы)
# --------------------------------------------------------------------------- #

# Сильные: в живой диктовке как отдельная фраза практически не встречаются.
STRONG_PHRASES: frozenset[str] = frozenset({
    "продолжение следует",
    "спасибо за просмотр",
    "спасибо за просмотр видео",
    "спасибо что посмотрели",
    "спасибо что смотрите",
    "подписывайтесь на канал",
    "подписывайтесь на наш канал",
    "подписывайтесь на мой канал",
    "не забудьте подписаться на канал",
    "не забудьте подписаться",
    "ставьте лайки",
    "ставьте лайк",
    "ставьте лайки и подписывайтесь на канал",
    "ставьте лайки подписывайтесь на канал",
    "редактор субтитров",
    "субтитры подготовил",
    "субтитры сделал",
    "субтитры делал",
    "субтитры создавал",
    "игорь дмитриев",
    "до новых встреч на канале",
    "увидимся в следующем видео",
    "всем пока до новых встреч",
})

# Слабые: обычные слова, которые Whisper часто выдаёт на тишине.
WEAK_PHRASES: frozenset[str] = frozenset({
    "спасибо",
    "спасибо большое",
    "большое спасибо",
    "всем спасибо",
    "спасибо за внимание",
    "благодарю за внимание",
    "до свидания",
    "до встречи",
    "до новых встреч",
    "всем пока",
    "пока",
    "пока пока",
    "угу",
    "ага",
    "ну",
    "м",
    "мм",
    "хм",
    "э",
    "а",
})

# Предложение целиком — титры субтитров.
_STRONG_SENTENCE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p) for p in (
        r"^(?:редактор|корректор|автор|переводчик) субтитров\b.*$",
        r"^субтитры (?:сделал|сделала|делал|делала|подготовил|подготовила|"
        r"создавал|создавала|создал|создала|предоставил|предоставлены|"
        r"подогнал|подогнала)\b.*$",
        r"^корректор(?: [а-яa-z] [а-яa-z]+)?$",
        r"^.*\b(?:dimatorzok|диматорзок)\b.*$",
        r"^.*\bamara org\b.*$",
    )
)

# Звуковые пометки в скобках/звёздочках: [Музыка], (смех), *аплодисменты*.
_SOUND_TAG_RE = re.compile(r"[\[\(\*♪][^\[\]\(\)\*♪]{0,40}[\]\)\*♪]")
_SOUND_TAG_STEMS = (
    "музык", "аплодисм", "смех", "смеет", "тишин", "шум", "звук", "вздох",
    "кашел", "кашля", "дыхан", "заставк", "песн", "поет", "играет",
)

_PUNCT_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
_TRAILING_JUNK_RE = re.compile(r"[\s,;:—–\-]+$")


def normalize(text: str) -> str:
    """Нижний регистр, «ё» → «е», пунктуация → пробел, одиночные пробелы."""
    text = text.lower().replace("ё", "е")
    text = _PUNCT_RE.sub(" ", text)
    return " ".join(text.split())


# --------------------------------------------------------------------------- #
# Сегменты Whisper
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SegmentInfo:
    """Сегмент распознавания с оценками модели (``None`` — оценки нет)."""

    text: str
    no_speech_prob: float | None = None
    avg_logprob: float | None = None
    compression_ratio: float | None = None

    @classmethod
    def from_whisper(cls, segment: dict) -> "SegmentInfo":
        def number(key: str) -> float | None:
            value = segment.get(key)
            try:
                return None if value is None else float(value)
            except (TypeError, ValueError):
                return None

        return cls(
            text=str(segment.get("text") or ""),
            no_speech_prob=number("no_speech_prob"),
            avg_logprob=number("avg_logprob"),
            compression_ratio=number("compression_ratio"),
        )

    def describe(self) -> str:
        def fmt(value: float | None) -> str:
            return "—" if value is None else f"{value:.2f}"

        return (f"no_speech={fmt(self.no_speech_prob)} logprob={fmt(self.avg_logprob)} "
                f"compression={fmt(self.compression_ratio)}")


def segment_rejection(segment: SegmentInfo, cfg) -> str | None:
    """Причина отбросить сегмент или ``None``, если он похож на речь."""
    if not normalize(segment.text):
        return "пустой сегмент"
    ns, lp, cr = segment.no_speech_prob, segment.avg_logprob, segment.compression_ratio
    if cr is not None and cr > cfg.compression_ratio_threshold:
        return f"зацикленный повтор (compression={cr:.2f})"
    if ns is not None and ns >= cfg.no_speech_hard_threshold:
        return f"модель не слышит речи (no_speech={ns:.2f})"
    if ns is not None and lp is not None and ns >= cfg.no_speech_threshold and lp < cfg.logprob_threshold:
        return f"нет речи и низкая уверенность (no_speech={ns:.2f}, logprob={lp:.2f})"
    return None


def filter_segments(segments: Sequence[SegmentInfo], cfg) -> tuple[list[SegmentInfo], list[str]]:
    """Разделить сегменты на сохранённые и причины отброшенных."""
    kept: list[SegmentInfo] = []
    removed: list[str] = []
    for segment in segments:
        reason = segment_rejection(segment, cfg)
        if reason is None:
            kept.append(segment)
        else:
            removed.append(f"сегмент {segment.text.strip()!r}: {reason}")
    return kept, removed


# --------------------------------------------------------------------------- #
# Повторы
# --------------------------------------------------------------------------- #


def deloop(text: str, max_repeats: int = 3, max_ngram: int = 10) -> str:
    """Схлопнуть n-грамму, повторённую подряд больше ``max_repeats`` раз.

    Сравнение по нормализованным словам; сохраняется первое вхождение в
    исходном написании. «да да да» (3 раза) не трогается.
    """
    tokens = text.split()
    norms = [normalize(token) for token in tokens]
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        collapsed = False
        if norms[i]:
            for size in range(1, max_ngram + 1):
                if i + size * (max_repeats + 1) > n:
                    break
                pattern = norms[i:i + size]
                if not all(pattern):
                    continue
                count = 1
                while norms[i + count * size:i + (count + 1) * size] == pattern:
                    count += 1
                if count > max_repeats:
                    out.extend(tokens[i:i + size])
                    i += size * count
                    collapsed = True
                    break
        if not collapsed:
            out.append(tokens[i])
            i += 1
    return " ".join(out)


# --------------------------------------------------------------------------- #
# Фразы-галлюцинации
# --------------------------------------------------------------------------- #


def _strip_sound_tags(text: str) -> tuple[str, list[str]]:
    removed: list[str] = []

    def replace(match: re.Match[str]) -> str:
        inner = normalize(match.group(0))
        if inner and len(inner.split()) <= 4 and any(stem in inner for stem in _SOUND_TAG_STEMS):
            removed.append(f"звуковая пометка {match.group(0)!r}")
            return " "
        return match.group(0)

    cleaned = _SOUND_TAG_RE.sub(replace, text)
    return " ".join(cleaned.split()), removed


def _is_strong(norm: str, extra: frozenset[str]) -> bool:
    return norm in STRONG_PHRASES or norm in extra or any(
        pattern.match(norm) for pattern in _STRONG_SENTENCE_PATTERNS
    )


def _strip_strong_suffix(sentence: str, phrases: Iterable[str]) -> tuple[str, str | None]:
    """Отрезать сильную фразу в конце предложения: «…хлеб, спасибо за просмотр»."""
    words = sentence.split()
    indexed = [(index, normalize(word)) for index, word in enumerate(words)]
    indexed = [(index, norm) for index, norm in indexed if norm]
    flat = [part for _, norm in indexed for part in norm.split()]
    for phrase in sorted(phrases, key=len, reverse=True):
        target = phrase.split()
        if len(target) < 2 or len(flat) <= len(target) or flat[-len(target):] != target:
            continue
        # Найти слово, с которого начинается фраза (слово может дать >1 токена).
        remaining = len(target)
        cut_at = len(words)
        for index, norm in reversed(indexed):
            remaining -= len(norm.split())
            cut_at = index
            if remaining <= 0:
                break
        if remaining < 0:
            continue
        head = _TRAILING_JUNK_RE.sub("", " ".join(words[:cut_at]))
        return head, phrase
    return sentence, None


def strip_hallucinations(
    text: str,
    *,
    profile: str = "command",
    suspicious: bool = False,
    extra_phrases: Iterable[str] = (),
) -> tuple[str, list[str]]:
    """Удалить фразы-галлюцинации. Возвращает (текст, причины удалений)."""
    extra = frozenset(normalize(p) for p in extra_phrases if normalize(p))
    text, removed = _strip_sound_tags(text)
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
    kept: list[str] = []
    for sentence in sentences:
        norm = normalize(sentence)
        if not norm:
            continue
        if _is_strong(norm, extra):
            removed.append(f"фраза субтитров {sentence!r}")
            continue
        kept.append(sentence)
    if kept:
        tail, phrase = _strip_strong_suffix(kept[-1], STRONG_PHRASES | extra)
        if phrase is not None:
            removed.append(f"хвост {phrase!r}")
            if normalize(tail):
                kept[-1] = tail
            else:
                kept.pop()
    result = " ".join(kept).strip()
    norm = normalize(result)
    if norm and norm in WEAK_PHRASES and (profile == "command" or suspicious):
        removed.append(f"короткая фраза {result!r}")
        result = ""
    if not normalize(result):
        result = ""
    return result, removed


# --------------------------------------------------------------------------- #
# Точка входа
# --------------------------------------------------------------------------- #


@dataclass
class FilterOutcome:
    text: str
    removed: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.removed)


def _default_cfg():
    from config_model import STTFilterSettings

    return STTFilterSettings()


def clean_transcript(
    text: str,
    *,
    segments: Sequence[SegmentInfo] | None = None,
    profile: str = "command",
    cfg=None,
) -> FilterOutcome:
    """Полная очистка: сегменты → повторы → фразы-галлюцинации.

    ``segments=None`` (модель без оценок, например GigaAM) пропускает
    первый слой. При ``cfg.enabled = False`` текст возвращается как есть.
    """
    cfg = cfg if cfg is not None else _default_cfg()
    raw = (text or "").strip()
    if not getattr(cfg, "enabled", True):
        return FilterOutcome(raw)

    removed: list[str] = []
    suspicious = False
    if segments:
        kept, dropped = filter_segments(segments, cfg)
        removed.extend(dropped)
        raw = "".join(segment.text for segment in kept).strip()
        suspicious = any(
            segment.no_speech_prob is not None and segment.no_speech_prob >= cfg.suspicious_no_speech
            for segment in kept
        )
    delooped = deloop(raw, max_repeats=cfg.max_repeats)
    if delooped != raw:
        removed.append("схлопнут повтор")
    cleaned, phrases = strip_hallucinations(
        delooped,
        profile=profile,
        suspicious=suspicious,
        extra_phrases=getattr(cfg, "extra_phrases", ()),
    )
    removed.extend(phrases)
    return FilterOutcome(cleaned, removed)


__all__ = [
    "FilterOutcome",
    "SegmentInfo",
    "STRONG_PHRASES",
    "WEAK_PHRASES",
    "clean_transcript",
    "deloop",
    "filter_segments",
    "normalize",
    "segment_rejection",
    "strip_hallucinations",
]
