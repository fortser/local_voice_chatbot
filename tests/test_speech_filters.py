"""Фильтр речи (Silero VAD) и очистка галлюцинаций — без моделей, torch и микрофона."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import soundfile as sf

from config_model import Settings, STTFilterSettings, load_settings, save_settings
from core.speech_gate import GateResult, SpeechGate, discard
from core.speech_runtime import SpeechRuntime
from core.stt import WhisperSTT
from core.transcript_filter import SegmentInfo, clean_transcript, deloop, strip_hallucinations
from tests.test_speech_runtime import FakeSTT, FakeTTS

SR = 16000


def gate_settings(**overrides):
    values = dict(enabled=True, wake_scan=True, threshold=0.5, min_speech_ms=250,
                  speech_pad_ms=200, min_silence_ms=300)
    values.update(overrides)
    return SimpleNamespace(**values)


def write_wav(path, seconds=2.0, rate=SR):
    sf.write(path, np.full(int(seconds * rate), 0.01, dtype=np.float32), rate, subtype="PCM_16")
    return str(path)


# --------------------------------------------------------------------------- #
# SpeechGate
# --------------------------------------------------------------------------- #


def test_gate_skips_audio_without_speech(tmp_path):
    detector = Mock(return_value=[])
    gate = SpeechGate(gate_settings(), detector=detector)
    result = gate.filter_file(write_wav(tmp_path / "silence.wav"))
    assert result == GateResult(None, "no_speech", 0.0, 2000.0)
    assert not result.has_speech
    detector.assert_called_once()
    audio, threshold, min_speech, min_silence, pad = detector.call_args.args
    assert audio.dtype == np.float32 and len(audio) == 2 * SR
    assert (threshold, min_speech, min_silence, pad) == (0.5, 250, 300, 200)


def test_gate_rejects_too_little_speech(tmp_path):
    gate = SpeechGate(gate_settings(min_speech_ms=300), detector=lambda *a: [(1000, 1000 + SR // 10)])
    result = gate.filter_file(write_wav(tmp_path / "click.wav"))
    assert result.path is None and result.reason == "too_short"
    assert result.speech_ms == pytest.approx(100)


def test_gate_trims_edges_and_discard_removes_copy(tmp_path):
    source = write_wav(tmp_path / "phrase.wav", seconds=3.0)
    gate = SpeechGate(gate_settings(), detector=lambda *a: [(SR // 2, SR), (int(1.5 * SR), 2 * SR)])
    result = gate.filter_file(source)
    assert result.has_speech and result.trimmed and result.reason == "speech"
    assert result.speech_ms == pytest.approx(1000)
    data, rate = sf.read(result.path)
    assert rate == SR and len(data) == int(1.5 * SR)
    discard(result)
    assert not (tmp_path / "phrase.speech.wav").exists()
    assert (tmp_path / "phrase.wav").exists()


def test_gate_keeps_file_when_speech_fills_it(tmp_path):
    source = write_wav(tmp_path / "full.wav", seconds=1.0)
    gate = SpeechGate(gate_settings(), detector=lambda *a: [(0, SR)])
    result = gate.filter_file(source)
    assert result.path == source and not result.trimmed


def test_gate_resamples_for_detector_and_maps_back(tmp_path):
    source = write_wav(tmp_path / "low.wav", seconds=2.0, rate=8000)
    seen = {}

    def detector(audio, *args):
        seen["length"] = len(audio)
        return [(SR // 2, SR)]  # 0.5–1.0 с в отсчётах 16 кГц

    result = SpeechGate(gate_settings(min_speech_ms=100), detector=detector).filter_file(source)
    assert seen["length"] == 2 * SR
    data, rate = sf.read(result.path)
    assert rate == 8000 and len(data) == 4000


def test_gate_disabled_and_unavailable_pass_through(tmp_path):
    source = write_wav(tmp_path / "a.wav")
    detector = Mock()
    disabled = SpeechGate(gate_settings(enabled=False), detector=detector)
    assert disabled.filter_file(source) == GateResult(source, "disabled")
    detector.assert_not_called()
    factory = Mock(side_effect=ImportError("No module named 'silero_vad'"))
    broken = SpeechGate(gate_settings(), detector_factory=factory)
    assert broken.filter_file(source).reason == "unavailable"
    assert broken.filter_file(source) == GateResult(source, "unavailable")
    assert factory.call_count == 1  # без повторных попыток загрузки
    assert not broken.available and "silero_vad" in broken.unavailable_reason
    assert not broken.preload()


def test_gate_unreadable_file_is_left_to_stt(tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not audio")
    detector = Mock()
    result = SpeechGate(gate_settings(), detector=detector).filter_file(bad)
    assert result.path == str(bad) and result.reason == "error"
    detector.assert_not_called()


def test_gate_detector_crash_does_not_block_recognition(tmp_path):
    source = write_wav(tmp_path / "a.wav")
    gate = SpeechGate(gate_settings(), detector=Mock(side_effect=RuntimeError("boom")))
    assert gate.filter_file(source).path == source


def test_gate_reads_settings_live(tmp_path):
    source = write_wav(tmp_path / "a.wav")
    cfg = gate_settings()
    gate = SpeechGate(cfg, detector=lambda *a: [])
    assert gate.filter_file(source).path is None
    cfg.enabled = False
    assert gate.filter_file(source).path == source


# --------------------------------------------------------------------------- #
# SpeechRuntime: диктовка и файлы
# --------------------------------------------------------------------------- #


def test_runtime_skips_stt_without_speech_and_cleans_trimmed_copy(tmp_path):
    stt = FakeSTT()
    source = write_wav(tmp_path / "segment.wav", seconds=3.0)
    gate = SpeechGate(gate_settings(), detector=Mock(return_value=[]))
    runtime = SpeechRuntime(stt_factory=lambda: stt, tts_factory=lambda: FakeTTS(tmp_path),
                            gpu_swap=False, speech_gate=gate)
    try:
        assert runtime.transcribe(source, threading.Event()) == ""
        assert stt.calls == []
        gate._detector = Mock(return_value=[(SR, 2 * SR)])
        assert runtime.transcribe(source, threading.Event()) == "Спасибо"
        path, profile = stt.calls[-1]
        assert path.endswith("segment.speech.wav") and profile == "dictation"
        assert not (tmp_path / "segment.speech.wav").exists()
    finally:
        runtime.close()


# --------------------------------------------------------------------------- #
# Очистка текста
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text, profile, expected", [
    ("Продолжение следует...", "dictation", ""),
    ("Купить хлеб и молоко. Продолжение следует...", "dictation", "Купить хлеб и молоко."),
    ("Купить хлеб, спасибо за просмотр.", "dictation", "Купить хлеб"),
    ("Субтитры сделал DimaTorzok", "dictation", ""),
    ("Редактор субтитров А.Синецкая Корректор А.Егорова", "dictation", ""),
    ("[Музыка] Привет всем.", "dictation", "Привет всем."),
    ("Шурочка, поставь паузу. Продолжение следует.", "command", "Шурочка, поставь паузу."),
    ("Спасибо.", "command", ""),
    ("Спасибо.", "dictation", "Спасибо."),
    ("Спасибо за внимание", "command", ""),
    ("Я написал продолжение следует в конце письма.", "dictation",
     "Я написал продолжение следует в конце письма."),
    ("Корректор текста нужен завтра.", "dictation", "Корректор текста нужен завтра."),
    ("Включи субтитры на английском.", "dictation", "Включи субтитры на английском."),
])
def test_strip_hallucinations(text, profile, expected):
    assert clean_transcript(text, profile=profile).text == expected


def test_weak_phrase_in_dictation_removed_only_when_model_doubts_speech():
    cfg = STTFilterSettings()
    confident = [SegmentInfo(" Спасибо.", no_speech_prob=0.05, avg_logprob=-0.2, compression_ratio=0.8)]
    doubtful = [SegmentInfo(" Спасибо.", no_speech_prob=0.45, avg_logprob=-0.2, compression_ratio=0.8)]
    assert clean_transcript("Спасибо.", segments=confident, profile="dictation", cfg=cfg).text == "Спасибо."
    assert clean_transcript("Спасибо.", segments=doubtful, profile="dictation", cfg=cfg).text == ""


def test_segment_scores_drop_hallucinated_segments():
    segments = [
        SegmentInfo(" Привет, это проверка.", 0.02, -0.25, 1.2),
        SegmentInfo(" Ну что ж.", 0.7, -0.8, 1.0),              # нет речи + низкая уверенность
        SegmentInfo(" Ага.", 0.95, -0.1, 1.0),                  # модель уверена, что речи нет
        SegmentInfo(" ла ла ла ла ла ла ла ла", 0.1, -0.3, 3.1),  # зацикленный повтор
        SegmentInfo(" Конец.", 0.65, -0.2, 1.1),                # уверенный текст сохраняется
    ]
    outcome = clean_transcript("ignored", segments=segments, profile="dictation", cfg=STTFilterSettings())
    assert outcome.text == "Привет, это проверка. Конец."
    assert len(outcome.removed) == 3


def test_deloop_and_extra_phrases_and_disable():
    assert deloop("да да да") == "да да да"
    assert deloop("раз два раз два раз два раз два раз два конец") == "раз два конец"
    cfg = STTFilterSettings(extra_phrases=["Всем добра"])
    assert clean_transcript("Готово. Всем добра!", profile="dictation", cfg=cfg).text == "Готово."
    off = STTFilterSettings(enabled=False)
    assert clean_transcript("Продолжение следует", profile="command", cfg=off).text == "Продолжение следует"
    text, removed = strip_hallucinations("Обычная фраза.", profile="dictation")
    assert text == "Обычная фраза." and removed == []


def test_whisper_uses_segment_scores_and_settings(tmp_path):
    path = write_wav(tmp_path / "a.wav", seconds=1.0)
    provider = WhisperSTT(device="cpu", download_root=tmp_path, filter_settings=STTFilterSettings())
    provider._model = Mock()
    provider._model.transcribe.return_value = {
        "text": " Запиши молоко. Продолжение следует.",
        "segments": [
            {"text": " Запиши молоко.", "no_speech_prob": 0.01, "avg_logprob": -0.2, "compression_ratio": 1.0},
            {"text": " Продолжение следует.", "no_speech_prob": 0.8, "avg_logprob": -0.9, "compression_ratio": 1.0},
        ],
    }
    assert provider.transcribe(path, profile="dictation") == "Запиши молоко."
    provider._filter_settings = STTFilterSettings(enabled=False)
    assert provider.transcribe(path, profile="dictation") == "Запиши молоко. Продолжение следует."


# --------------------------------------------------------------------------- #
# Настройки
# --------------------------------------------------------------------------- #


def test_speech_settings_defaults_and_round_trip(tmp_path):
    settings = Settings()
    assert settings.speech_gate.enabled and settings.stt.filter.enabled
    assert settings.stt.provider == "whisper" and settings.stt.gigaam.revision == "e2e_rnnt"
    settings.stt.provider = "gigaam"
    settings.speech_gate.enabled = False
    settings.stt.filter.extra_phrases = ["всем добра"]
    path = tmp_path / "settings.toml"
    save_settings(settings, path)
    loaded = load_settings(path)
    assert loaded.stt.provider == "gigaam" and not loaded.speech_gate.enabled
    assert loaded.stt.filter.extra_phrases == ["всем добра"]
    with pytest.raises(Exception):
        Settings.model_validate({"speech_gate": {"threshold": 2.0}})
    with pytest.raises(Exception):
        Settings.model_validate({"stt": {"filter": {"unknown": 1}}})


def test_example_settings_file_is_valid():
    from pathlib import Path

    example = Path(__file__).resolve().parent.parent / "settings.toml.example"
    loaded = load_settings(example)
    assert loaded.speech_gate.enabled and loaded.stt.provider == "whisper"


# --------------------------------------------------------------------------- #
# Ассистент: поиск кодового слова и основной ход
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("regions, wake_scan, expected", [
    ([], True, None),                       # тишина — Whisper не вызывается
    ([], False, "scan.wav"),               # фильтр для сканирования выключен
    ([(SR // 2, SR)], True, "scan.speech.wav"),
])
def test_wake_scan_uses_speech_gate(tmp_path, regions, wake_scan, expected):
    from core.wake_word import WakeWordListener

    scan = write_wav(tmp_path / "scan.wav", seconds=2.0)
    pipeline = Mock()
    pipeline.lock = threading.RLock()
    pipeline.speech_gate = SpeechGate(gate_settings(wake_scan=wake_scan, min_speech_ms=100),
                                      detector=lambda *a: regions)
    pipeline.vad.record_until_silence.return_value = scan
    pipeline.stt.transcribe.return_value = "обычная речь"
    listener = WakeWordListener(pipeline)
    listener.enable()
    listener._iterate()
    if expected is None:
        pipeline.stt.transcribe.assert_not_called()
    else:
        assert pipeline.stt.transcribe.call_args.args[0].endswith(expected)
    assert not (tmp_path / "scan.speech.wav").exists()
    pipeline._process_voice_input_locked.assert_not_called()


def test_pipeline_turn_skips_whisper_without_speech(mock_providers, mock_audio, tmp_path):
    from main import VoicePipeline

    stt = mock_providers["stt"]
    stt.transcribe.return_value = "  поставь паузу "
    pipeline = VoicePipeline()
    recording = write_wav(tmp_path / "utterance.wav", seconds=2.0)
    pipeline._speech_gate = SpeechGate(gate_settings(), detector=lambda *a: [])
    assert pipeline._transcribe_recording(recording) == ""
    stt.transcribe.assert_not_called()
    pipeline._speech_gate = SpeechGate(gate_settings(), detector=lambda *a: [(SR // 4, SR)])
    assert pipeline._transcribe_recording(recording) == "поставь паузу"
    assert stt.transcribe.call_args.args[0].endswith("utterance.speech.wav")
    assert not (tmp_path / "utterance.speech.wav").exists()
