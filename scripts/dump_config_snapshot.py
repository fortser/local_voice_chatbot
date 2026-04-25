"""Сериализация всех верхнеуровневых констант ``config.py`` в JSON-снапшот.

Используется как baseline для Этапов 1-2 редизайна UI: автотест
``tests/test_config_contract.py`` потом сверяется с этим файлом, чтобы
рефакторинг ``config.py`` на Pydantic Settings не сломал значения или типы.

Запуск:
    python scripts/dump_config_snapshot.py

Результат пишется в ``tests/fixtures/config_snapshot_baseline.json``.
Абсолютные пути (Path с частью BASE_DIR) сериализуются как относительные
к корню репозитория — иначе snapshot будет привязан к конкретной машине.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import config  # noqa: E402


FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
OUTPUT_FILE = FIXTURES_DIR / "config_snapshot_baseline.json"


def _encode(value: object) -> object:
    """Привести значение к JSON-совместимому виду.

    ``Path`` превращаем в POSIX-строку относительно ``REPO_ROOT`` —
    так snapshot не зависит от машины. Абсолютные пути вне репозитория
    (например, пользовательский ``~/Shura`` раскрыт) сохраняем как есть.
    """
    if isinstance(value, Path):
        try:
            rel = value.resolve().relative_to(REPO_ROOT)
            return {"__path__": rel.as_posix()}
        except ValueError:
            return {"__path_abs__": value.as_posix()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    return value


def collect_constants() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for name in dir(config):
        if not name.isupper() or name.startswith("_"):
            continue
        value = getattr(config, name)
        if callable(value):
            continue
        result[name] = {
            "type": type(value).__name__,
            "value": _encode(value),
        }
    return result


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    constants = collect_constants()
    OUTPUT_FILE.write_text(
        json.dumps(constants, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Wrote {len(constants)} constants -> {OUTPUT_FILE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
