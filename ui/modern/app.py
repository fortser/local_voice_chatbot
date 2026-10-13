"""New UI entry point, with a hardware-free design preview."""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .backend import AssistantBackend
from .components import app_icon
from .window import ModernWindow


def _set_windows_app_id() -> None:
    """Group the taskbar button under Shura, not python.exe, so it shows Shura's icon."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Shura.VoiceAssistant.ModernUI")
    except (AttributeError, OSError):
        pass


def run_ui_modern(*, with_ipc: bool = True, ipc_host: str = "127.0.0.1",
                  ipc_port: int = 9999, preview: bool = False) -> int:
    _set_windows_app_id()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    backend = AssistantBackend(with_ipc=with_ipc, ipc_host=ipc_host, ipc_port=ipc_port)
    window = ModernWindow(backend, preview=preview)
    window.show()
    if preview:
        window.set_state("idle")
        window.overview.status.setText("Режим предпросмотра · ядро не запущено")
    return app.exec()
