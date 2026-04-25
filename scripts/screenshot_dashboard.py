"""Сделать PNG-скриншот DashboardWindow без реального pipeline.

Использует offscreen-платформу Qt и заглушечный bridge — стиль/расположение
видно полностью, но Whisper/TTS не грузятся.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# На Windows offscreen-platform не грузит fallback-шрифты для кириллицы/emoji.
# Используем родную windows-platform: окно физически создаётся, но мы его
# не show()-им — grab() и так работает.
os.environ.pop("QT_QPA_PLATFORM", None)
# Превью без BT-поллинга (PowerShell медленный, для скриншота не нужен).
os.environ.setdefault("SHURA_DISABLE_BT_POLL", "1")

from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.pyside6.app import _load_qss  # noqa: E402
from ui.pyside6.bridge import PipelineBridge  # noqa: E402
from ui.pyside6.dashboard import DashboardWindow  # noqa: E402


@dataclass
class _FakeTurn:
    user_text: str = "сколько времени"
    llm_text: str = "Сейчас пятнадцать тридцать две."
    stt_ms: float = 312.0
    llm_ms: float = 815.0
    tts_ms: float = 410.0
    total_s: float = 1.6
    error: object = None
    wav_in: object = None
    wav_out: object = None
    llm_prompt_tokens: object = None
    llm_completion_tokens: object = None


def main() -> int:
    out = REPO_ROOT / "docs" / "dashboard_preview.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    app.setFont(QFont("Segoe UI", 9))
    qss = _load_qss()
    if qss:
        app.setStyleSheet(qss)

    bridge = PipelineBridge(with_ipc=False)
    win = DashboardWindow(bridge=bridge)

    # Наполним демо-данными.
    bridge.models_list.emit(
        ["llama3.1:8b-instruct-q4_K_M", "qwen2.5:14b", "gemma2:9b"],
        "qwen2.5:14b",
    )
    bridge.ready.emit()
    bridge.state_changed.emit("idle", None)
    bridge.level_update.emit(2200.0, 24)
    # Прокинем VAD-маркеры на LevelMeter напрямую.
    win._level.set_vad(noise_rms=600.0, threshold=1800.0)
    bridge.turn_result.emit(_FakeTurn())
    bridge.health_update.emit(
        {
            "stt": {"loaded": True},
            "llm": {"healthy": True, "provider": "ollama"},
            "tts": {"loaded": True, "provider": "silero"},
            "audio": {"noise_rms": 600.0, "threshold": 1800.0},
        }
    )

    # Демо-данные для DevicesPanel (BT-поллинг отключён, пушим сами).
    from utils.bluetooth_battery import BluetoothBattery  # noqa: E402

    win._devices_panel._on_bt_levels(  # type: ignore[attr-defined]
        [
            BluetoothBattery(name="WH-1000XM4", percent=78),
            BluetoothBattery(name="BT KeyBoard", percent=22),
            BluetoothBattery(name="LYWSD03MMC", percent=99),
        ]
    )

    # Принудительный layout без show().
    win.ensurePolished()
    win.adjustSize()
    win.repaint()
    app.processEvents()

    pixmap = win.grab()
    pixmap.save(str(out), "PNG")
    print(f"Saved: {out}  ({pixmap.width()}x{pixmap.height()})")

    win.close()
    bridge.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
