"""Ручная приёмка Этапа 2: рефакторинг config.py на Pydantic Settings + shim.

Проверяет три вещи:
1. shim ``config.py`` отдаёт те же значения, что и baseline-snapshot
   (косвенно — через 20 случайно выбранных констант).
2. ``settings.toml`` с пользовательскими правками корректно перекрывает
   дефолты (конструируем временный файл, перезагружаем модель).
3. Чистый запуск ``from config_model import load_settings`` и
   ``save_settings(diff_only=True)`` не писает ничего, если ничего не
   менялось.

Запуск:

    python check_stage_config_refactor.py

В конце — y/n-приёмка.
"""

from __future__ import annotations

import json
import random
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

SNAPSHOT = REPO_ROOT / "tests" / "fixtures" / "config_snapshot_baseline.json"


def _decode_value(encoded):
    if isinstance(encoded, dict):
        if "__path__" in encoded:
            return (REPO_ROOT / encoded["__path__"]).resolve()
        if "__path_abs__" in encoded:
            return Path(encoded["__path_abs__"])
    if isinstance(encoded, list):
        return [_decode_value(v) for v in encoded]
    return encoded


def step1_random_constants() -> bool:
    print("\n[1/3] Сверка 20 случайных констант shim vs baseline-snapshot")
    print("-" * 70)

    import config  # noqa: WPS433

    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    sample = random.sample(sorted(snapshot.keys()), 20)

    ok = True
    for name in sample:
        expected = _decode_value(snapshot[name]["value"])
        actual = getattr(config, name)
        if isinstance(expected, Path):
            matches = Path(actual).resolve() == expected
        else:
            matches = actual == expected
        marker = "OK" if matches else "FAIL"
        print(f"  [{marker}] {name}")
        if not matches:
            print(f"        expected: {expected!r}")
            print(f"        actual:   {actual!r}")
            ok = False
    return ok


def step2_toml_override() -> bool:
    print("\n[2/3] settings.toml перекрывает дефолт (OLLAMA_TIMEOUT)")
    print("-" * 70)

    from config_model import Settings, load_settings, save_settings

    with tempfile.TemporaryDirectory() as tmp:
        toml_path = Path(tmp) / "settings.toml"
        custom = Settings()
        custom.llm.timeout = 777
        save_settings(custom, path=toml_path, diff_only=True)

        content = toml_path.read_text(encoding="utf-8")
        print(f"  Файл settings.toml (diff-only):\n{content}")

        reloaded = load_settings(path=toml_path)
        actual = reloaded.llm.timeout
        print(f"  settings.llm.timeout после перезагрузки: {actual}")

        if actual != 777:
            print("  FAIL: значение не подтянулось")
            return False

        # Убедимся, что других полей в дифе нет.
        if "timeout" not in content or "whisper_model_size" in content:
            print("  FAIL: diff не минимальный (должно быть только timeout)")
            return False

    print("  OK: 777 подтянулось; diff содержит только изменённое поле")
    return True


def step3_empty_diff_when_clean() -> bool:
    print("\n[3/3] save_settings(diff_only=True) на дефолте пишет пустой TOML")
    print("-" * 70)

    from config_model import Settings, save_settings

    with tempfile.TemporaryDirectory() as tmp:
        toml_path = Path(tmp) / "settings.toml"
        save_settings(Settings(), path=toml_path, diff_only=True)
        content = toml_path.read_text(encoding="utf-8").strip()
        print(f"  Содержимое: {content!r}")
        if content:
            print("  FAIL: в диф-режиме без изменений файл должен быть пустой")
            return False

    print("  OK: пусто")
    return True


def main() -> int:
    print("=" * 70)
    print("Этап 2 — Рефакторинг config.py на Pydantic Settings + shim")
    print("=" * 70)

    results = [
        ("shim == baseline (20 случайных)", step1_random_constants()),
        ("settings.toml override", step2_toml_override()),
        ("diff_only пустой при отсутствии правок", step3_empty_diff_when_clean()),
    ]

    print("\nИтог проверок:")
    for name, passed in results:
        print(f"  [{'OK' if passed else 'FAIL'}] {name}")

    if not all(p for _, p in results):
        print("\nНекоторые проверки не прошли. Этап не принят.")
        return 1

    print("\nЧек-лист (ручная часть):")
    print("  [ ] pytest -q — зелёный")
    print("  [ ] python main.py --mode ipc — стартует")
    print("  [ ] голосовая turn-операция отрабатывает на shim")

    ans = input("\nПринимаем Этап 2? [y/N]: ").strip().lower()
    if ans == "y":
        print("Принято. Удалите check_stage_config_refactor.py после коммита.")
        return 0
    print("Не принято.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
