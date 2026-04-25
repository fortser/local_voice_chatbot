"""Smoke-инициализация ``VoicePipeline`` с полностью подменёнными зависимостями.

Цель: убедиться, что ``VoicePipeline()`` конструируется и ``start()``
зовёт ``on_stage`` с ожидаемыми именами. Ни микрофон, ни модели не
трогаются — всё подменено на ``MagicMock`` через conftest-фикстуры.

Тяжёлые интеграционные прогоны (реальный STT→LLM→TTS-оборот) — в
ручных ``check_stage_<N>.py``; здесь только быстрая проверка, что
оркестровка не падает на этапе конструирования.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def pipeline(mock_providers, mock_audio):
    """VoicePipeline с полностью замоканными подсистемами."""
    from main import VoicePipeline

    return VoicePipeline()


def test_voice_pipeline_init_without_audio(pipeline, mock_providers) -> None:
    """__init__ отрабатывает без железа: все провайдеры — моки."""
    assert pipeline is not None
    # Роутер и реестр команд построены реально — они тестируются отдельно,
    # но должны быть на месте в pipeline.
    assert pipeline.router is not None
    assert len(list(pipeline._registry)) > 0


def test_start_emits_expected_stages(pipeline, mock_providers) -> None:
    """pipeline.start() должен вызвать on_stage с 'calibrating' и 'loading_stt'."""
    seen: list[tuple[str, object]] = []

    def on_stage(name: str, payload: object) -> None:
        seen.append((name, payload))

    pipeline.start(on_stage=on_stage)

    stage_names = [name for name, _ in seen]
    assert "calibrating" in stage_names
    assert "loading_stt" in stage_names
    # loading_tts зовётся только если НЕ идёт GPU-swap (Silero CPU — дефолт).
    # В дефолтном config'е TTS_PROVIDER=silero → swap выключен → должен прозвучать.
    assert "loading_tts" in stage_names

    mock_providers["stt"].load_model.assert_called_once()
    mock_providers["tts"].load_model.assert_called_once()


def test_start_stop_cycle(pipeline) -> None:
    """start() → stop() не должны падать, stop идемпотентен."""
    pipeline.start()
    pipeline.stop()
    pipeline.stop()  # повторный stop безопасен
