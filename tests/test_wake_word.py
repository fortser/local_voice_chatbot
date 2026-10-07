"""Unit tests for wake-word text matching.

These tests cover the pure-function layer of ``core.wake_word`` — the bit
that decides whether a chunk of transcribed text contains the activation
word. No mic, no Whisper, no pipeline.
"""

from __future__ import annotations

import pytest
import threading
from unittest.mock import Mock

from core.wake_word import WakeWordListener, _normalize, contains_wake_word
from utils.errors import AudioError, CancelledError


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


@pytest.fixture
def listener_pipeline():
    pipeline = Mock()
    pipeline.lock = threading.RLock()
    return pipeline


@pytest.mark.parametrize("phase", ["recording", "transcribing"])
@pytest.mark.parametrize("resume", [False, True])
def test_pause_during_scan_prevents_activation(listener_pipeline, phase, resume):
    pipeline = listener_pipeline
    listener = WakeWordListener(pipeline)
    listener.enable()

    def record(**kwargs):
        if phase == "recording":
            listener.disable()
            if resume:
                listener.enable()
        return "scan.wav"

    def transcribe(path):
        listener.disable()
        if resume:
            listener.enable()
        return "Шурочка"

    pipeline.vad.record_until_silence.side_effect = record
    pipeline.stt.transcribe.side_effect = transcribe
    listener._iterate()
    assert listener.is_enabled == resume
    pipeline.player.play_array.assert_not_called()
    pipeline._process_voice_input_locked.assert_not_called()
    assert pipeline.vad.record_until_silence.call_count == 1
    if phase == "recording":
        pipeline.stt.transcribe.assert_not_called()


def test_pause_interrupts_scan_and_resume_reuses_pipeline(listener_pipeline):
    pipeline = listener_pipeline
    entered = threading.Event()
    listener = WakeWordListener(pipeline)
    listener.enable()

    def record(*, cancel_event, **kwargs):
        entered.set()
        if cancel_event.wait(1):
            raise CancelledError("paused")
        raise AssertionError("Scan was not cancelled")

    pipeline.vad.record_until_silence.side_effect = record
    worker = threading.Thread(target=listener._iterate)
    worker.start()
    try:
        assert entered.wait(1)
        listener.disable()
    finally:
        listener.disable()
        worker.join(2)
    assert not worker.is_alive()
    pipeline.stt.transcribe.assert_not_called()
    pipeline.vad.record_until_silence.side_effect = None
    pipeline.vad.record_until_silence.return_value = "new-scan.wav"
    pipeline.stt.transcribe.return_value = "обычная речь"
    listener.enable()
    listener._iterate()
    assert listener.is_enabled
    pipeline.stt.transcribe.assert_called_once_with("new-scan.wav")
    pipeline.start.assert_not_called()
    pipeline.stop.assert_not_called()
    pipeline.stt.load_model.assert_not_called()
    pipeline.stt.unload_model.assert_not_called()


@pytest.mark.parametrize("silent", [False, True])
def test_pause_during_active_turn_finishes_in_disabled_state(listener_pipeline, monkeypatch, silent):
    pipeline = listener_pipeline
    states = []
    listener = WakeWordListener(pipeline, on_state=lambda name, payload: states.append(name))
    monkeypatch.setattr("core.wake_word.keep_awake.acquire", Mock())
    monkeypatch.setattr("core.wake_word.time.sleep", lambda seconds: None)
    pipeline.stt.transcribe.return_value = "Шурочка"

    def record(**kwargs):
        if "cancel_event" in kwargs:
            return "scan.wav"
        listener.disable()
        if silent:
            raise AudioError("silent")
        return "question.wav"

    pipeline.vad.record_until_silence.side_effect = record
    listener.enable()
    listener._iterate()
    assert states[-1] == "idle"
    assert not listener.is_enabled
    pipeline.stop.assert_not_called()
