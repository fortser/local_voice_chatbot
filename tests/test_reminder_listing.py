"""Тесты форматирования списка напоминаний для голосового ответа."""

from __future__ import annotations

import pytest

from core.reminders.listing import (
    _count_in_neuter,
    _count_phrase,
    _ordinal_neuter,
    format_remaining,
    format_reminders_list,
)


class TestCountInNeuter:
    def test_one_becomes_neuter(self) -> None:
        assert _count_in_neuter(1) == "одно"

    def test_compound_one_becomes_neuter(self) -> None:
        assert _count_in_neuter(21) == "двадцать одно"

    def test_two_unchanged(self) -> None:
        assert _count_in_neuter(2) == "два"

    def test_five_unchanged(self) -> None:
        assert _count_in_neuter(5) == "пять"


class TestCountPhrase:
    @pytest.mark.parametrize(
        "n,expected",
        [
            (1, "одно напоминание"),
            (2, "два напоминания"),
            (3, "три напоминания"),
            (4, "четыре напоминания"),
            (5, "пять напоминаний"),
            (11, "одиннадцать напоминаний"),
            (21, "двадцать одно напоминание"),
            (22, "двадцать два напоминания"),
        ],
    )
    def test_agreement(self, n: int, expected: str) -> None:
        assert _count_phrase(n) == expected


class TestOrdinalNeuter:
    def test_first_to_tenth(self) -> None:
        assert _ordinal_neuter(1) == "первое"
        assert _ordinal_neuter(2) == "второе"
        assert _ordinal_neuter(10) == "десятое"

    def test_beyond_ten_fallback(self) -> None:
        assert _ordinal_neuter(11) == "напоминание номер одиннадцать"


class TestFormatRemaining:
    def test_under_minute(self) -> None:
        assert format_remaining(30) == "менее минуты"
        assert format_remaining(59) == "менее минуты"

    def test_minutes(self) -> None:
        # 5 min exactly
        assert format_remaining(300) == "через пять минут"

    def test_minutes_round_to_nearest(self) -> None:
        # 89 s → 1 min (round)
        assert format_remaining(89) == "через одну минуту"
        # 90 s → 2 min (banker's rounding in Python: round(1.5) = 2)
        assert format_remaining(90) == "через две минуты"

    def test_hours(self) -> None:
        assert format_remaining(3600) == "через один час"
        assert format_remaining(7200) == "через два часа"
        assert format_remaining(18000) == "через пять часов"

    def test_hours_round(self) -> None:
        # 1h 20min → 1 hour
        assert format_remaining(4800) == "через один час"
        # 1h 40min → 2 hours
        assert format_remaining(6000) == "через два часа"


class TestFormatRemindersList:
    def test_empty(self) -> None:
        assert format_reminders_list([]) == "Активных напоминаний нет."

    def test_single(self) -> None:
        items = [{"id": "a", "fire_at": 1000.0, "text": "проверить кашу"}]
        out = format_reminders_list(items, now=700.0)
        assert out == (
            "Сейчас у вас одно напоминание: через пять минут, проверить кашу."
        )

    def test_multiple(self) -> None:
        items = [
            {"id": "a", "fire_at": 1000.0 + 300, "text": "проверить кашу"},
            {"id": "b", "fire_at": 1000.0 + 7200, "text": "позвонить маме"},
            {"id": "c", "fire_at": 1000.0 + 30, "text": "тест"},
        ]
        # Не сортируем здесь — listing ожидает отсортированный вход.
        items.sort(key=lambda r: r["fire_at"])
        out = format_reminders_list(items, now=1000.0)
        assert out == (
            "Сейчас у вас три напоминания. "
            "Первое — менее минуты, тест. "
            "Второе — через пять минут, проверить кашу. "
            "Третье — через два часа, позвонить маме."
        )

    def test_negative_remaining_clamped(self) -> None:
        # fire_at в прошлом не должен валить форматтер: clamp до 0 → «менее минуты».
        items = [{"id": "x", "fire_at": 100.0, "text": "опоздавшее"}]
        out = format_reminders_list(items, now=200.0)
        assert "менее минуты" in out

    def test_eleventh_uses_fallback_ordinal(self) -> None:
        items = [
            {"id": str(i), "fire_at": 1000.0 + i * 60, "text": f"дело {i}"}
            for i in range(1, 12)
        ]
        out = format_reminders_list(items, now=1000.0)
        assert "одиннадцать напоминаний" in out
        # Каждый порядковый в списке капитализируется в начале фразы;
        # для fallback-формы это «Напоминание номер одиннадцать».
        assert "Напоминание номер одиннадцать" in out
