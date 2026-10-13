"""Render the sidebar logo without models or audio: python -m scripts.preview_logo.

Saves window snapshots for a normal and a minimal window, idle and listening,
to build/logo-preview/, plus one lap of the listening animation as frames in
build/logo-preview/frames/ (50 ms apart, as in the running app).
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from ui.modern.backend import AssistantBackend
from ui.modern.window import ModernWindow


def main():
    output = Path("build/logo-preview")
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    # The offscreen Qt plugin does not always enumerate Windows fonts.
    for filename in ("segoeui.ttf", "segoeuib.ttf", "segoeuisl.ttf"):
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    window = ModernWindow(AssistantBackend(with_ipc=False), preview=True,
                          settings=QSettings(str(output / "preview.ini"), QSettings.IniFormat))
    window.show()
    window.logo.set_animated(False)  # steady glow for a still picture
    for width, height in ((1180, 850), (1180, 720), (940, 680)):
        window.resize(width, height)
        for state in ("idle", "listening"):
            window.set_state(state)
            app.processEvents()
            target = output / f"window-{width}x{height}-{state}.png"
            if not window.grab().save(str(target)):
                raise RuntimeError(f"Cannot save {target}")
            print(f"{target}  (логотип {window.logo.width()}x{window.logo.height()})")
    window.resize(1180, 850)
    window.set_state("listening")
    window.logo.set_animated(True)
    app.processEvents()
    frames = output / "frames"
    frames.mkdir(exist_ok=True)
    for index in range(60):  # one full lap of the running light
        window.logo.grab().save(str(frames / f"frame_{index:02d}.png"))
        window.logo._tick()
    print(f"{frames}  (60 кадров анимации)")
    window.close()
    app.processEvents()


if __name__ == "__main__":
    main()
