"""Bootstrap PySide6-приложения.

``run_ui_pyside6()`` создаёт ``QApplication``, поднимает :class:`PipelineBridge`
(который владеет VoicePipeline в своём worker-потоке), показывает
:class:`DashboardWindow` и запускает Qt event loop.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from bootstrap import bootstrap
from config import IPC_HOST, IPC_PORT

from .bridge import PipelineBridge
from .dashboard import DashboardWindow

_QSS_PATH = Path(__file__).resolve().parent / "styles" / "solarized.qss"


def _load_qss() -> str:
    try:
        return _QSS_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def run_ui_pyside6(
    *,
    with_ipc: bool = True,
    ipc_host: str = IPC_HOST,
    ipc_port: int = IPC_PORT,
) -> int:
    """Запустить PySide6-UI с реальным VoicePipeline."""
    bootstrap()

    app = QApplication.instance() or QApplication(sys.argv)
    qss = _load_qss()
    if qss:
        app.setStyleSheet(qss)

    bridge = PipelineBridge(
        with_ipc=with_ipc,
        ipc_host=ipc_host,
        ipc_port=ipc_port,
    )
    window = DashboardWindow(bridge=bridge)
    window.show()

    # Запускаем инициализацию pipeline в фоне — окно к этому моменту уже
    # отрисовано, пользователь видит «Инициализация…» пока грузится Whisper.
    bridge.start_pipeline()

    return app.exec()
