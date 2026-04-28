"""Подсчёт статистики использования команд из logs/recognized.log.

Формат строки в логе:
    <timestamp>\t<command>\t<matched_synonym>\t<full_text>

Запуск:
    python -m scripts.command_stats
    python -m scripts.command_stats --by synonym
    python -m scripts.command_stats --since 2026-04-01
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import RECOGNIZED_LOG_FILE  # noqa: E402


def _parse_line(line: str) -> tuple[datetime, str, str, str] | None:
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 4:
        return None
    try:
        ts = datetime.strptime(parts[0], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return ts, parts[1], parts[2], parts[3]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--by", choices=("command", "synonym", "pair"), default="command",
        help="что считать: команды, синонимы, или пары command+synonym",
    )
    p.add_argument("--since", help="фильтр по дате (YYYY-MM-DD)")
    p.add_argument("--top", type=int, default=20, help="сколько строк показать")
    p.add_argument(
        "--file", type=Path, default=RECOGNIZED_LOG_FILE,
        help="путь к лог-файлу",
    )
    args = p.parse_args()

    if not args.file.exists():
        print(f"Лог не найден: {args.file}", file=sys.stderr)
        return 1

    since = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d")

    counter: Counter[str] = Counter()
    total = 0
    with args.file.open("r", encoding="utf-8") as f:
        for line in f:
            parsed = _parse_line(line)
            if parsed is None:
                continue
            ts, cmd, syn, _full = parsed
            if since and ts < since:
                continue
            if args.by == "command":
                key = cmd
            elif args.by == "synonym":
                key = syn
            else:
                key = f"{cmd}  <-  {syn}"
            counter[key] += 1
            total += 1

    if total == 0:
        print("Нет записей для выбранного фильтра.")
        return 0

    width = max(len(k) for k, _ in counter.most_common(args.top))
    print(f"Всего распознано: {total}\n")
    print(f"{'count':>6}  {'%':>5}  {args.by}")
    print("-" * (width + 16))
    for key, n in counter.most_common(args.top):
        pct = 100.0 * n / total
        print(f"{n:>6}  {pct:>4.1f}%  {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
