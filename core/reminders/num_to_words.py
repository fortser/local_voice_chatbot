"""Фабрика конвертера чисел в слова.

Переключается через ``config.NUM_TO_WORDS_BACKEND``:

* ``"manual"``    — словарь 1–999 в `num_to_words_manual`, без зависимостей
* ``"num2words"`` — библиотека num2words, покрывает любые числа

Идея — собрать оба варианта, сравнить качество озвучки на ухо в течение
нескольких дней и выбрать тот, что звучит естественнее. Переключение
делается правкой одной строки в config.py.
"""

from __future__ import annotations

import logging

from config import NUM_TO_WORDS_BACKEND

logger = logging.getLogger(__name__)


def humanize_duration(n: int, unit: str) -> str:
    """Делегирует выбранному бэкенду. Бэкенд подгружается лениво."""
    backend = (NUM_TO_WORDS_BACKEND or "manual").lower()
    if backend == "num2words":
        from core.reminders import num_to_words_external
        return num_to_words_external.humanize_duration(n, unit)
    if backend == "manual":
        from core.reminders import num_to_words_manual
        return num_to_words_manual.humanize_duration(n, unit)
    raise ValueError(
        f"Unknown NUM_TO_WORDS_BACKEND: {backend!r} "
        f"(ожидаю 'manual' или 'num2words')"
    )
