"""Smoke-импорты всех модулей, которые читают из ``config``.

Параметризованно ``importlib.import_module(<mod>)`` на каждого потребителя.
Тест проваливается, если импорт ронят ошибку — это главная защита от
того, что рефакторинг ``config.py`` на Pydantic-shim случайно
переименует имя, которое читается где-то внутри проекта.

Тяжёлые объекты (Whisper-модель, XTTS, DeepFilterNet) НЕ инстанцируются —
их конструирование живёт в функциях-фабриках, не на module level.

Список собран из `grep -l 'from config import' .` на момент написания
теста. Если добавляете нового потребителя — добавляйте и сюда.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

CONSUMERS = [
    "main",
    "logging_config",
    "core",
    "core.stt",
    "core.llm",
    "core.tts",
    "core.tts_utils",
    "core.silero_tts",
    "core.audio_stream",
    "core.vad",
    "core.wake_word",
    "core.preprocessing",
    "core.lmstudio_client",
    "core.ollama_client",
    "core.reminders.num_to_words",
    "commands.note_command",
    "commands.question_command",
    "ipc.client",
    "ipc.server",
    "ui.tkinter_ui",
    "ui.overlay",
    "utils.generate_ack_phrases",
]

# Stage-scripts (временные, удаляются после приёмки) добавляются условно:
# если файла нет — пропуск, тест остаётся зелёным.
STAGE_SCRIPTS = ["check_stage_6", "check_stage_9"]


@pytest.mark.parametrize("module_name", CONSUMERS)
def test_smoke_import_all_consumers(module_name: str) -> None:
    """Импорт не должен падать. Тяжёлые модели загружаются лениво."""
    importlib.import_module(module_name)


@pytest.mark.parametrize("module_name", STAGE_SCRIPTS)
def test_smoke_import_stage_scripts(module_name: str) -> None:
    """Stage-скрипты — опциональны (удаляются после приёмки этапа)."""
    script_path = REPO_ROOT / f"{module_name}.py"
    if not script_path.exists():
        pytest.skip(f"{module_name}.py удалён (этап принят)")
    importlib.import_module(module_name)
