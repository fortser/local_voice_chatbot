"""Форматирование списка активных напоминаний для голосового ответа.

Команда «перечисли напоминания» (см. ``commands.list_reminders_command``)
собирает одну строку для одного TTS-прохода — мы сознательно не плодим
N отдельных озвучек ради экономии VRAM-свопа Whisper↔XTTS и более
естественной интонации.

Формат фразы:

    Сейчас у вас три напоминания. Первое — через пять минут, проверить кашу.
    Второе — через два часа, позвонить маме. Третье — менее минуты, тест.

Если активных нет — «Активных напоминаний нет.». Если одно — «Сейчас у
вас одно напоминание: через пять минут, проверить кашу.».

Логика выбора единицы остаточного времени:

* < 60 с              → «менее минуты»
* < 1 ч               → минуты, округление до ближайшей (минимум 1)
* ≥ 1 ч               → часы, округление до ближайшего (минимум 1)

Дни/недели/месяцы не поддерживаем — ``humanize_duration`` ограничен
секундами/минутами/часами, а напоминание парсится только в этих
единицах. При очень больших интервалах (>999 часов) ``humanize_duration``
бросит ValueError; ловим и подставляем generic-формулировку, чтобы
команда не падала из-за одного экзотического напоминания.
"""

from __future__ import annotations

import time
from typing import Iterable

from core.reminders.num_to_words import humanize_duration
from core.reminders.num_to_words_manual import _number_to_words, plural_form

# Порядковые числительные среднего рода — согласуется с «напоминание».
# Сверх 10 переключаемся на fallback «напоминание номер N» (см. ниже).
_ORDINALS_NEUTER: dict[int, str] = {
    1: "первое",
    2: "второе",
    3: "третье",
    4: "четвёртое",
    5: "пятое",
    6: "шестое",
    7: "седьмое",
    8: "восьмое",
    9: "девятое",
    10: "десятое",
}

# Формы существительного «напоминание» в им. п.: 1 / 2-4 / 5+.
_REMINDER_FORMS = ("напоминание", "напоминания", "напоминаний")


def _count_in_neuter(n: int) -> str:
    """Числительное в форме среднего рода: «один» → «одно».

    Для составных числительных корректируем только последнее слово —
    «двадцать один» → «двадцать одно». Остальные числа в м. р. и ср. р.
    совпадают по форме.
    """
    words = _number_to_words(n)
    tokens = words.split()
    if tokens and tokens[-1] == "один":
        tokens[-1] = "одно"
    return " ".join(tokens)


def _ordinal_neuter(idx_one_based: int) -> str:
    """1 → «первое», 11 → «напоминание номер одиннадцать»."""
    if idx_one_based in _ORDINALS_NEUTER:
        return _ORDINALS_NEUTER[idx_one_based]
    return f"напоминание номер {_number_to_words(idx_one_based)}"


def format_remaining(seconds: float) -> str:
    """Остаток времени до срабатывания → «через пять минут» / «менее минуты».

    Возвращает уже готовый фрагмент с предлогом «через» (или без него для
    «менее минуты»), чтобы вызывающий код просто вставлял в шаблон.
    """
    if seconds < 60:
        return "менее минуты"
    if seconds < 3600:
        count = max(1, round(seconds / 60))
        try:
            return f"через {humanize_duration(count, 'minute')}"
        except ValueError:
            return f"через {count} минут"
    count = max(1, round(seconds / 3600))
    try:
        return f"через {humanize_duration(count, 'hour')}"
    except ValueError:
        return f"через {count} часов"


def _count_phrase(n: int) -> str:
    """«одно напоминание» / «три напоминания» / «пять напоминаний»."""
    word = _count_in_neuter(n)
    noun = plural_form(n, _REMINDER_FORMS)
    return f"{word} {noun}"


def format_reminders_list(
    reminders: Iterable[dict],
    *,
    now: float | None = None,
) -> str:
    """Собрать единую фразу для TTS из активных напоминаний.

    Ожидает уже отсортированный по ``fire_at`` итерируемый набор словарей
    ``{id, fire_at, text}``. Параметр ``now`` нужен для тестов — в проде
    подставляется ``time.time()``.
    """
    items = list(reminders)
    if not items:
        return "Активных напоминаний нет."

    if now is None:
        now = time.time()

    n = len(items)
    if n == 1:
        r = items[0]
        remaining = max(0.0, float(r["fire_at"]) - now)
        return f"Сейчас у вас {_count_phrase(1)}: {format_remaining(remaining)}, {r['text']}."

    parts: list[str] = [f"Сейчас у вас {_count_phrase(n)}."]
    for idx, r in enumerate(items, start=1):
        remaining = max(0.0, float(r["fire_at"]) - now)
        ordinal = _ordinal_neuter(idx)
        # Заглавная буква первого порядкового — фраза начинается после точки.
        ordinal_cap = ordinal[0].upper() + ordinal[1:]
        parts.append(f"{ordinal_cap} — {format_remaining(remaining)}, {r['text']}.")
    return " ".join(parts)
