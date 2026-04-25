"""Контракт ``config.py`` против зафиксированного baseline-snapshot.

Эти тесты — safety-net для Этапа 2 редизайна UI: когда ``config.py``
перепишется на shim над Pydantic ``Settings``, старые module-level
атрибуты обязаны сохранить имена, значения и типы. Любое расхождение
с ``tests/fixtures/config_snapshot_baseline.json`` ломает тесты.

Если вы ОСОЗНАННО меняете значение какой-то константы — обновите
baseline через ``python scripts/dump_config_snapshot.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import config

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO_ROOT / "tests" / "fixtures" / "config_snapshot_baseline.json"

# Пути в snapshot сериализованы как {"__path__": "relative/to/repo"} или
# {"__path_abs__": "..."}. При сравнении воссоздаём Path и сверяем с config.X.
PATH_SENTINELS = ("__path__", "__path_abs__")


def _load_snapshot() -> dict[str, dict[str, object]]:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def _decode_path(entry: dict) -> Path:
    if "__path__" in entry:
        return (REPO_ROOT / entry["__path__"]).resolve()
    return Path(entry["__path_abs__"])


def _decode_value(encoded: object) -> object:
    if isinstance(encoded, dict) and any(k in encoded for k in PATH_SENTINELS):
        return _decode_path(encoded)
    if isinstance(encoded, list):
        return [_decode_value(v) for v in encoded]
    return encoded


SNAPSHOT = _load_snapshot()


def test_all_known_constants_present() -> None:
    """Каждое имя из baseline-snapshot всё ещё существует в config."""
    missing = [name for name in SNAPSHOT if not hasattr(config, name)]
    assert not missing, f"Отсутствуют константы: {missing}"


def test_no_unexpected_removals() -> None:
    """Текущий config содержит все baseline-имена (добавления разрешены)."""
    current = {n for n in dir(config) if n.isupper() and not n.startswith("_")
               and not callable(getattr(config, n))}
    removed = set(SNAPSHOT.keys()) - current
    assert not removed, f"Удалены константы: {removed}"


@pytest.mark.parametrize("name", sorted(SNAPSHOT.keys()))
def test_default_values_unchanged(name: str) -> None:
    """Для каждой константы значение совпадает с baseline."""
    entry = SNAPSHOT[name]
    expected = _decode_value(entry["value"])
    actual = getattr(config, name)

    if isinstance(expected, Path):
        # Пути сравниваем как resolved — сеттеры могут отдавать Path,
        # а baseline хранит relative-фрагмент.
        assert Path(actual).resolve() == expected, (
            f"{name}: {actual!r} != {expected!r}"
        )
    else:
        assert actual == expected, f"{name}: {actual!r} != {expected!r}"


@pytest.mark.parametrize("name", sorted(SNAPSHOT.keys()))
def test_types_unchanged(name: str) -> None:
    """Тип значения совпадает с baseline (str не стал int и т. п.)."""
    entry = SNAPSHOT[name]
    expected_type_name = entry["type"]
    actual = getattr(config, name)
    assert type(actual).__name__ == expected_type_name, (
        f"{name}: тип {type(actual).__name__} != {expected_type_name}"
    )
