"""Конвертер чисел через библиотеку ``num2words``.

Альтернатива :mod:`num_to_words_manual`. Плюсы — покрывает любые числа,
даты, валюты; минус — внешняя зависимость (~150 KB). Сравнение качества
и ощущаемой корректности на слух — в ``check_stage_10.py``.

Склонение единицы измерения и винительный падеж для ж. р. берём из
manual-модуля, чтобы сравнивать только сам конвертер числа в слова.
"""

from __future__ import annotations

from core.reminders.num_to_words_manual import (
    UNIT_FORMS,
    plural_form,
)

try:
    from num2words import num2words as _num2words
except ImportError:  # pragma: no cover — проверяется в check_stage_10
    _num2words = None


_FEMININE_REPLACE = {"один": "одну", "одна": "одну", "два": "две"}


def humanize_duration(n: int, unit: str) -> str:
    if _num2words is None:
        raise RuntimeError(
            "num2words не установлен. pip install num2words, либо переключите "
            "NUM_TO_WORDS_BACKEND='manual' в config.py"
        )
    if unit not in UNIT_FORMS:
        raise ValueError(f"Unknown unit: {unit!r}")
    num_words = _num2words(n, lang="ru")
    if unit in ("second", "minute"):
        tokens = num_words.split()
        if tokens and tokens[-1] in _FEMININE_REPLACE:
            tokens[-1] = _FEMININE_REPLACE[tokens[-1]]
        num_words = " ".join(tokens)
    unit_word = plural_form(n, UNIT_FORMS[unit])
    return f"{num_words} {unit_word}"
