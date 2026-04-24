"""Regex-only парсер хвоста команды «напомни …».

Пример входа (хвост уже отрезан роутером):

    «20 минут проверить кашу»           → (20, "minute", "проверить кашу")
    «через 20 минут проверить кашу»     → (20, "minute", "проверить кашу")
    «5 секунд тест»                      → (5,  "second", "тест")
    «2 часа выключить духовку»          → (2,  "hour",   "выключить духовку")

Не-regex формы («через полчаса», «завтра в 9», «в 15:30») — осознанно
не поддерживаются, см. обсуждение в проектной памяти. Если regex не
срабатывает, команда отвечает fallback-фразой, в LLM не идём.
"""

from __future__ import annotations

import re

from commands.router import normalize

# Сопоставление префикса основы единицы → каноническое имя.
# Matching through startswith — ловит «секунд/секунду/секунды»,
# «минут/минуту/минуты», «час/часа/часов».
_UNIT_PREFIXES: tuple[tuple[str, str], ...] = (
    ("секунд", "second"),
    ("минут",  "minute"),
    ("час",    "hour"),
)

# Пунктуация между токенами (запятые, точки) уже снята normalize()'ом —
# здесь матчим только пробелы. Глагол — любая форма от корня «напомн»
# («напомни», «напомню», «напомнить», «напоминание») — Whisper подставляет
# разные формы, а смысл один.
_PATTERN = re.compile(
    r"^\s*"
    # Покрывает оба стебля: «напомн-» (напомни/напомню/напомнить) и
    # «напомин-» (напоминание/напоминаю) — Whisper подставляет любую форму.
    r"(?:напом\w*(?:\s+мне)?\s+)?"
    r"(?:через\s+)?"
    r"(\d+)\s+(секунд\w*|минут\w*|час\w*)\s+(.+?)\s*$",
    re.IGNORECASE,
)


def parse_reminder_tail(tail: str) -> tuple[int, str, str] | None:
    """Вернуть ``(count, unit, text)`` или ``None`` если не распарсили.

    * ``count`` — целое число (1–999 для manual-бэкенда конвертера слов)
    * ``unit`` — ``"second"`` | ``"minute"`` | ``"hour"``
    * ``text`` — то, о чём напоминать
    """
    tail = (tail or "").strip()
    if not tail:
        return None
    # Нормализуем так же, как роутер делает для матчинга команд:
    # lower + ё→е + без пунктуации. Whisper любит подсовывать запятую
    # после вводного слова («Напомни, через 30…») и точку в конце фразы —
    # регэкспу это мешало бы, а normalize() всё снимает в один приём.
    tail = normalize(tail)
    m = _PATTERN.match(tail)
    if not m:
        return None
    count = int(m.group(1))
    unit_raw = m.group(2).lower()
    text = m.group(3).strip()
    if not text or count < 1:
        return None
    for prefix, canonical in _UNIT_PREFIXES:
        if unit_raw.startswith(prefix):
            return count, canonical, text
    return None


def unit_to_seconds(count: int, unit: str) -> int:
    """Перевести ``(count, unit)`` в абсолютные секунды для fire_at."""
    if unit == "second":
        return count
    if unit == "minute":
        return count * 60
    if unit == "hour":
        return count * 3600
    raise ValueError(f"Unknown unit: {unit!r}")
