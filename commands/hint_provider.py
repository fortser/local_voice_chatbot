"""Источник списка команд для wake-hint оверлея.

Список читается из ``config/wake_hints.json`` (формат см. ниже). Если файла
нет или JSON битый — fallback к авто-генерации из ``CommandRegistry``: для
каждой команды берётся первый синоним.

Формат файла::

    {
      "version": 1,
      "items": [
        {"command": "note", "label": "запиши заметку", "show": true, "order": 1},
        ...
      ]
    }

* ``command`` — стабильный ``BaseCommand.name``; команды, которых больше нет
  в реестре, молча отбрасываются.
* ``label`` — то, что показывается на экране (можно править вручную или
  обновлять через ``scripts/suggest_wake_hints.py`` по статистике).
* ``show`` (опционально, default ``True``) — скрыть строку, не удаляя.
* ``order`` (опционально) — целое число для сортировки; команды без
  ``order`` идут после, в порядке регистра.

Команды из реестра, которых нет в JSON, **добавляются автоматически** в
конец с дефолтным синонимом — чтобы новые фичи не «терялись» из подсказки.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from commands.registry import CommandRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HintLine:
    command: str
    label: str
    order: int  # меньше — выше


def _auto_label(synonyms: Iterable[str]) -> str:
    """Берём первый синоним как дефолтный label."""
    for syn in synonyms:
        if syn:
            return syn
    return "?"


def _registry_defaults(registry: CommandRegistry) -> dict[str, HintLine]:
    """Авто-генерация: command.name → HintLine с первым синонимом."""
    out: dict[str, HintLine] = {}
    for idx, cmd in enumerate(registry):
        out[cmd.name] = HintLine(
            command=cmd.name,
            label=_auto_label(cmd.synonyms),
            order=10_000 + idx,  # сильно после ручных order'ов
        )
    return out


def _parse_json(path: Path) -> list[dict]:
    """Возвращает items[] из JSON-файла или [] при любой ошибке."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("wake_hints: не смог прочитать %s (%s) — fallback к авто", path, exc)
        return []
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        logger.warning("wake_hints: %s — нет массива 'items', fallback к авто", path)
        return []
    return items


def load_hint_lines(
    registry: CommandRegistry,
    *,
    hints_file: Path | str,
    max_items: int = 10,
) -> list[str]:
    """Собирает финальный список строк для отрисовки.

    1. Базис — авто-генерация из ``registry`` (для каждой команды первый синоним).
    2. JSON перекрывает базис: задаёт label, order, может скрыть через ``show=false``.
    3. Команды из JSON, которых нет в реестре, отбрасываются с warning'ом.
    4. Сортировка по ``order``, обрезка по ``max_items``.

    Возвращает плоский ``list[str]`` — готов к подаче в виджет.
    """
    path = Path(hints_file)
    by_name = _registry_defaults(registry)
    known_names = set(by_name)

    json_items = _parse_json(path)
    seen_in_json: set[str] = set()
    for raw in json_items:
        if not isinstance(raw, dict):
            continue
        name = raw.get("command")
        if not isinstance(name, str) or not name:
            continue
        if name not in known_names:
            logger.warning(
                "wake_hints: команда %r из %s не найдена в реестре — пропускаю",
                name, path,
            )
            continue
        if raw.get("show", True) is False:
            by_name.pop(name, None)
            seen_in_json.add(name)
            continue
        label = raw.get("label")
        if not isinstance(label, str) or not label.strip():
            label = by_name[name].label  # оставляем авто-label
        order = raw.get("order")
        if not isinstance(order, int):
            order = by_name[name].order  # сохраняем дефолтный порядок
        by_name[name] = HintLine(command=name, label=label.strip(), order=order)
        seen_in_json.add(name)

    missing = known_names - seen_in_json
    if json_items and missing:
        logger.info(
            "wake_hints: %d команд нет в %s, добавлены авто-дефолтами: %s",
            len(missing), path, sorted(missing),
        )

    ordered = sorted(by_name.values(), key=lambda h: (h.order, h.label))
    if max_items > 0:
        ordered = ordered[:max_items]
    return [h.label for h in ordered]


__all__ = ["HintLine", "load_hint_lines"]
