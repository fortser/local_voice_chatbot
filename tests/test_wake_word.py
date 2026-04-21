"""Unit tests for wake-word text matching.

These tests cover the pure-function layer of ``core.wake_word`` — the bit
that decides whether a chunk of transcribed text contains the activation
word. No mic, no Whisper, no pipeline.
"""

from __future__ import annotations

import pytest

from core.wake_word import _normalize, contains_wake_word


class TestNormalize:
    def test_lowercases(self) -> None:
        assert _normalize("ШУРОЧКА") == ["шурочка"]

    def test_strips_punctuation(self) -> None:
        assert _normalize("Шурочка, привет!") == ["шурочка", "привет"]

    def test_multiple_spaces_ok(self) -> None:
        assert _normalize("  шурочка    привет  ") == ["шурочка", "привет"]

    def test_empty(self) -> None:
        assert _normalize("") == []
        assert _normalize("   ") == []

    def test_cyrillic_stays(self) -> None:
        # ё treated as a regular letter.
        assert _normalize("Шурочка, ёлка") == ["шурочка", "ёлка"]

    def test_digits_kept(self) -> None:
        assert _normalize("шурочка 2") == ["шурочка", "2"]


class TestContainsWakeWord:
    WAKE = "шурочка"
    ALIASES = ["шура"]

    def test_exact_match(self) -> None:
        assert contains_wake_word("Шурочка", self.WAKE, self.ALIASES)

    def test_with_punctuation(self) -> None:
        assert contains_wake_word("Шурочка, как дела?", self.WAKE, self.ALIASES)

    def test_alias_match(self) -> None:
        assert contains_wake_word("Шура, привет", self.WAKE, self.ALIASES)

    def test_does_not_match_substring(self) -> None:
        # Key invariant: "шурочкин" must not trigger on "шурочка". Token
        # equality, not substring.
        assert not contains_wake_word("шурочкин пёс", self.WAKE, self.ALIASES)
        assert not contains_wake_word("пришурочкать", self.WAKE, self.ALIASES)

    def test_case_insensitive(self) -> None:
        assert contains_wake_word("шУрОчКа", self.WAKE, self.ALIASES)

    def test_empty_text(self) -> None:
        assert not contains_wake_word("", self.WAKE, self.ALIASES)
        assert not contains_wake_word("   ", self.WAKE, self.ALIASES)

    def test_no_aliases(self) -> None:
        assert contains_wake_word("Шурочка", self.WAKE)
        # "Шура" is the alias — without aliases it shouldn't match.
        assert not contains_wake_word("Шура", self.WAKE)

    def test_word_in_middle_of_phrase(self) -> None:
        assert contains_wake_word(
            "Привет шурочка, как ты?", self.WAKE, self.ALIASES
        )

    @pytest.mark.parametrize(
        "text",
        [
            "привет мир",
            "шурик",
            "архитектура",
            "аршура",  # substring "шура" inside but must be rejected
        ],
    )
    def test_negatives(self, text: str) -> None:
        assert not contains_wake_word(text, self.WAKE, self.ALIASES)
