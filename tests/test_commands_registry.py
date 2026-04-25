"""Контракт ``CommandRegistry`` против baseline-snapshot + инвариант «≥2 слов».

Snapshot в ``tests/fixtures/commands_snapshot.json`` фиксирует набор
команд и их синонимы. Изменения (добавление команды, переименование
синонима) требуют явного пересбора snapshot'а через
``python scripts/dump_commands_snapshot.py``.

Второй тест повторяет инвариант из ``CommandRegistry.register`` —
все синонимы должны быть минимум 2 слова. Дублирование намеренное:
если кто-то ослабит `register` (например, уберёт проверку), тест
поймает регрессию.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from commands.registry import build_default_registry

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO_ROOT / "tests" / "fixtures" / "commands_snapshot.json"


def _load_snapshot() -> list[dict]:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def test_default_registry_matches_snapshot() -> None:
    snapshot = _load_snapshot()
    registry = build_default_registry()

    actual = [
        {
            "name": cmd.name,
            "command_type": cmd.command_type.value,
            "synonyms": list(cmd.synonyms),
        }
        for cmd in registry
    ]
    # Порядок регистрации важен (роутер проверяет команды в том же порядке
    # для разрешения конфликтов), поэтому сверяем списки как есть.
    assert actual == snapshot


def test_all_synonyms_two_words_or_more() -> None:
    registry = build_default_registry()
    offenders: list[tuple[str, str]] = []
    for cmd in registry:
        for syn in cmd.synonyms:
            if len(syn.split()) < 2:
                offenders.append((cmd.name, syn))
    assert not offenders, (
        f"Однословные синонимы (ловят шум Whisper): {offenders}"
    )


def test_registry_rejects_one_word_synonym() -> None:
    """CommandRegistry.register сам обязан отклонить однословный синоним."""
    from commands.base import BaseCommand, CommandContext, CommandType
    from commands.registry import CommandRegistry

    class BadCommand(BaseCommand):
        name = "bad"
        synonyms = ("стоп",)
        command_type = CommandType.INSTANT

        def execute(self, ctx: CommandContext) -> bool:  # pragma: no cover
            return True

    with pytest.raises(ValueError, match="at least 2 words"):
        CommandRegistry([BadCommand()])
