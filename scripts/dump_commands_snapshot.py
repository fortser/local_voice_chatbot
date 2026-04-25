"""Сериализация CommandRegistry в JSON-снапшот.

Сохраняем (name, synonyms, command_type) каждой команды из
``build_default_registry()``. Используется тестом
``tests/test_commands_registry.py`` как baseline: рефакторинг UI не
должен ронять команды и переименовывать синонимы.

Запуск:
    python scripts/dump_commands_snapshot.py

Результат — ``tests/fixtures/commands_snapshot.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from commands.registry import build_default_registry  # noqa: E402


FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
OUTPUT_FILE = FIXTURES_DIR / "commands_snapshot.json"


def main() -> None:
    registry = build_default_registry()
    snapshot = []
    for cmd in registry:
        snapshot.append(
            {
                "name": cmd.name,
                "command_type": cmd.command_type.value,
                "synonyms": list(cmd.synonyms),
            }
        )
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(snapshot)} commands -> {OUTPUT_FILE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
