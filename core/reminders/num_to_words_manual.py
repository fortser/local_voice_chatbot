"""Ручной конвертер чисел (1–999) в русские слова + склонение единиц.

Покрывает диапазон, нужный для напоминаний: до 999 секунд/минут/часов.
Склонения: «одну минуту», «две минуты», «пять минут», «двадцать две минуты»,
«один час», «два часа», «пять часов». Ни одной внешней зависимости.
"""

from __future__ import annotations

_ONES = {
    1: "один", 2: "два", 3: "три", 4: "четыре", 5: "пять",
    6: "шесть", 7: "семь", 8: "восемь", 9: "девять", 10: "десять",
    11: "одиннадцать", 12: "двенадцать", 13: "тринадцать", 14: "четырнадцать",
    15: "пятнадцать", 16: "шестнадцать", 17: "семнадцать", 18: "восемнадцать",
    19: "девятнадцать",
}
_TENS = {
    20: "двадцать", 30: "тридцать", 40: "сорок", 50: "пятьдесят",
    60: "шестьдесят", 70: "семьдесят", 80: "восемьдесят", 90: "девяносто",
}
_HUNDREDS = {
    100: "сто", 200: "двести", 300: "триста", 400: "четыреста",
    500: "пятьсот", 600: "шестьсот", 700: "семьсот", 800: "восемьсот",
    900: "девятьсот",
}

# Формы единицы измерения для согласования: (1, 2-4, 5+).
UNIT_FORMS: dict[str, tuple[str, str, str]] = {
    "second": ("секунду", "секунды", "секунд"),
    "minute": ("минуту",  "минуты",  "минут"),
    "hour":   ("час",     "часа",    "часов"),
}

# Замены «один/два» на винительный падеж ж. р. для секунд/минут:
# «через одну минуту», «через двадцать две минуты».
_FEMININE_REPLACE = {"один": "одну", "два": "две"}


def _number_to_words(n: int) -> str:
    if n < 1 or n >= 1000:
        raise ValueError(f"Unsupported number for manual converter: {n}")
    parts: list[str] = []
    hundreds = (n // 100) * 100
    if hundreds:
        parts.append(_HUNDREDS[hundreds])
        n -= hundreds
    if n >= 20:
        tens = (n // 10) * 10
        parts.append(_TENS[tens])
        n -= tens
    if n > 0:
        parts.append(_ONES[n])
    return " ".join(parts)


def plural_form(n: int, forms: tuple[str, str, str]) -> str:
    n100 = n % 100
    if 11 <= n100 <= 19:
        return forms[2]
    n10 = n100 % 10
    if n10 == 1:
        return forms[0]
    if 2 <= n10 <= 4:
        return forms[1]
    return forms[2]


def humanize_duration(n: int, unit: str) -> str:
    """(5, "minute") → «пять минут»; (21, "minute") → «двадцать одну минуту»."""
    if unit not in UNIT_FORMS:
        raise ValueError(f"Unknown unit: {unit!r}")
    num_words = _number_to_words(n)
    if unit in ("second", "minute"):
        tokens = num_words.split()
        if tokens and tokens[-1] in _FEMININE_REPLACE:
            tokens[-1] = _FEMININE_REPLACE[tokens[-1]]
        num_words = " ".join(tokens)
    unit_word = plural_form(n, UNIT_FORMS[unit])
    return f"{num_words} {unit_word}"
