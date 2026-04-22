"""Pre-render ack-phrases for commands as WAV files in ``assets/ack/``.

Запускается **один раз** (или при добавлении новых команд). Для каждой
команды и фазы (`before` / `after`) проверяет, есть ли уже WAV в
``assets/ack/<command_name>_<phase>.wav``; если файла нет — синтезирует
фразу через текущий Silero-провайдер и сохраняет.

Что делает скрипт безопасным для повторного запуска:

* Существующие файлы **не перезаписываются** (поведение по умолчанию).
* Чтобы регенерировать что-то — удалите соответствующий WAV или папку
  целиком: ``rm -rf assets/ack/`` и снова запустите скрипт.
* Флаг ``--overwrite`` форсирует регенерацию всех файлов.

Голос по умолчанию — тот же Silero-спикер, что в `config.SILERO_SPEAKER`.
Если в будущем захочется отдельный «голос ack» — можно добавить параметр
сюда; рантайм ничего об этом знать не будет, он просто проигрывает WAV.

Usage:
    python -m utils.generate_ack_phrases
    python -m utils.generate_ack_phrases --overwrite
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from bootstrap import bootstrap
from config import BASE_DIR
from core.silero_tts import SileroTTS
from utils.errors import TTSError

logger = logging.getLogger(__name__)

# Каталог-приёмник; коммитится в репозиторий, чтобы фразы ехали с кодом.
ACK_DIR = BASE_DIR / "assets" / "ack"

# Источник истины: какие фазы у каких команд. При добавлении новой команды
# (после M3+) — добавь сюда нужные фразы и прогони скрипт ещё раз.
#
# `before` играется ПЕРЕД диктовкой (только CONTENT-команды: note, question).
# `after` играется ПОСЛЕ выполнения (INSTANT/GLOBAL).
ACK_PHRASES: dict[str, dict[str, str]] = {
    # CONTENT
    "note":          {"before": "готова записать заметку, диктуйте",
                      "after":  "добавила в заметки"},
    "question":      {"before": "готова ответить на вопрос, спрашивай"},
    # INSTANT — плеер
    "pause":         {"after":  "поставила на паузу"},
    "resume":        {"after":  "продолжаю воспроизведение"},
    "seek_forward":  {"after":  "перемотала вперёд"},
    "seek_backward": {"after":  "перемотала назад"},
    # INSTANT — громкость
    "volume_up":     {"after":  "прибавила громкости"},
    "volume_down":   {"after":  "убавила громкости"},
    "mute":          {"after":  "выключила звук"},
    "unmute":        {"after":  "включила звук"},
    # INSTANT — скриншот
    "screenshot":    {"after":  "сделала скриншот"},
    # GLOBAL
    "stop":          {"after":  "остановилась"},
    "cancel":        {"after":  "отменила"},
}


def ack_filename(command_name: str, phase: str) -> str:
    """Канонические имена файлов: ``<command>_<phase>.wav``."""
    return f"{command_name}_{phase}.wav"


def _enumerate_targets() -> list[tuple[str, str, str]]:
    """Возвращает плоский список ``(command, phase, text)``."""
    out: list[tuple[str, str, str]] = []
    for cmd, phases in ACK_PHRASES.items():
        for phase, text in phases.items():
            if phase not in ("before", "after"):
                raise ValueError(
                    f"Unknown phase {phase!r} for command {cmd!r}; "
                    "expected 'before' or 'after'"
                )
            out.append((cmd, phase, text))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ack-phrase WAVs")
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Force regenerate even if WAV already exists.",
    )
    args = parser.parse_args()

    bootstrap()
    logging.getLogger().setLevel(logging.INFO)

    ACK_DIR.mkdir(parents=True, exist_ok=True)
    targets = _enumerate_targets()
    print(f"Целевых фраз: {len(targets)}")
    print(f"Папка-приёмник: {ACK_DIR}")

    pending: list[tuple[str, str, str, Path]] = []
    skipped = 0
    for cmd, phase, text in targets:
        dst = ACK_DIR / ack_filename(cmd, phase)
        if dst.exists() and not args.overwrite:
            skipped += 1
            continue
        pending.append((cmd, phase, text, dst))

    print(f"Уже существует: {skipped}; будет сгенерировано: {len(pending)}")

    if not pending:
        print("Нечего делать. Удалите файлы или передайте --overwrite для регенерации.")
        return 0

    tts = SileroTTS()
    print("Загружаю Silero…")
    tts.load_model()
    print("Готов; синтезирую…")

    failures: list[str] = []
    for cmd, phase, text, dst in pending:
        try:
            tmp_wav = tts.synthesize(text)
        except TTSError as exc:
            logger.exception("Synth failed for %s_%s", cmd, phase)
            failures.append(f"{cmd}_{phase}: {exc}")
            continue
        # synthesize() кидает результат в logs/tts_out/; переносим в assets/ack/.
        shutil.move(tmp_wav, dst)
        size = dst.stat().st_size
        print(f"  ✓ {dst.name:30s} ({size // 1024} КБ)  «{text}»")

    tts.unload_model()
    print()
    if failures:
        print(f"❌ Ошибки на {len(failures)} фразах:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"✅ Готово. Файлы лежат в {ACK_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
