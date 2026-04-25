"""Общие фикстуры и хуки для автотестов.

Здесь собраны моки провайдеров ``STT/LLM/TTS`` и зависимостей
``VoicePipeline`` (``AudioStream``, ``AudioPlayer``, ``VAD``, менеджеры
сессий и mute). Используются ``test_pipeline_smoke.py``.

Репозиторий ставится в ``sys.path`` на случай, если ``pytest`` запустили
не из корня.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def mock_providers(mocker):
    """Подменяет фабрики провайдеров в ``main`` на заглушки.

    Возвращает dict с инстансами-моками — чтобы тест мог проверить,
    что ``load_model()`` / ``is_healthy()`` были вызваны.
    """
    stt = MagicMock(name="STTProvider")
    stt.load_model = MagicMock()
    stt.unload_model = MagicMock()

    llm = MagicMock(name="LLMProvider")
    llm.is_healthy = MagicMock(return_value=True)
    llm.model = "mock-model"

    tts = MagicMock(name="TTSProvider")
    tts.load_model = MagicMock()
    tts.unload_model = MagicMock()

    mocker.patch("main.create_stt_provider", return_value=stt)
    mocker.patch("main.create_llm_provider", return_value=llm)
    mocker.patch("main.create_tts_provider", return_value=tts)
    return {"stt": stt, "llm": llm, "tts": tts}


@pytest.fixture
def mock_audio(mocker):
    """Моки для аудио-подсистем, чтобы pipeline.__init__ и start() не трогали железо."""
    stream = MagicMock(name="AudioStream")
    stream.start = MagicMock()
    stream.stop = MagicMock()
    mocker.patch("main.AudioStream", return_value=stream)

    player = MagicMock(name="AudioPlayer")
    mocker.patch("main.AudioPlayer", return_value=player)

    vad = MagicMock(name="VAD")
    vad.calibrate = MagicMock(return_value=(100.0, 180.0))
    mocker.patch("main.VoiceActivityDetector", return_value=vad)

    # generate_beep возвращает numpy-массив в проде; для __init__'а достаточно заглушки.
    mocker.patch("main.generate_beep", return_value=b"")

    mute = MagicMock(name="MuteController")
    mocker.patch("main.MuteController", return_value=mute)

    session = MagicMock(name="SessionManager")
    mocker.patch("main.SessionManager", return_value=session)

    reminders_storage = MagicMock(name="ReminderStorage")
    mocker.patch("main.ReminderStorage", return_value=reminders_storage)

    reminders_scheduler = MagicMock(name="ReminderScheduler")
    reminders_scheduler.load_and_restore = MagicMock(return_value=(0, 0))
    reminders_scheduler.shutdown = MagicMock()
    mocker.patch("main.ReminderScheduler", return_value=reminders_scheduler)

    return {
        "stream": stream,
        "player": player,
        "vad": vad,
        "scheduler": reminders_scheduler,
    }
