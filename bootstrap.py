"""One-shot startup for every entry point (check scripts, main.py).

Things every runnable must do before touching audio/GPU:

  * force UTF-8 on stdout so Cyrillic device names / logs render on Windows
  * set up structured logging (file + console)
  * **show** the current Windows-default audio input/output so the user can
    immediately verify — and re-pick in Windows Sound Settings if wrong

The app does NOT programmatically pin devices: the user picks what they want
in Windows, we just report it. Keeps behaviour predictable.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from logging_config import setup_logging
from utils.audio_devices import DeviceInfo, get_current_devices


def _force_utf8_stdout() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


@dataclass(frozen=True)
class BootstrapResult:
    input_device: DeviceInfo | None
    output_device: DeviceInfo | None


def bootstrap(verbose: bool = True) -> BootstrapResult:
    _force_utf8_stdout()
    setup_logging()

    in_info, out_info = get_current_devices()

    if verbose:
        print("--- Аудио-устройства (текущие системные дефолты Windows) ---")
        if in_info:
            print(f"  Вход:  #{in_info.index} {in_info.name} [{in_info.hostapi}]")
        else:
            print("  Вход:  (не определён)")
        if out_info:
            print(f"  Выход: #{out_info.index} {out_info.name} [{out_info.hostapi}]")
        else:
            print("  Выход: (не определён)")
        print(
            "  Если устройство не то — смените его в Windows\n"
            "  (Параметры → Система → Звук → Ввод / Вывод) и перезапустите скрипт.\n"
            "  Список всех устройств: python -m utils.audio_devices"
        )

    return BootstrapResult(input_device=in_info, output_device=out_info)
