"""Render speech pages without models or audio: python -m scripts.preview_speech_tools."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from ui.modern.backend import AssistantBackend
from ui.modern.speech_pages import DictationControl
from ui.modern.window import ModernWindow


def main():
    output = Path("build/speech-preview")
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
    microphone = {"id": "preview-input", "name": "Микрофон (USB Audio Device)"}
    window.backend.audio_devices_update.emit({
        "input": {"devices": [microphone], "default_id": microphone["id"]},
        "active": {"input": microphone}, "stream_running": False, "standalone": True,
    })
    for width, height in ((1180, 850), (940, 680)):
        window.resize(width, height)
        for page in ("stt", "tts"):
            window.navigate(page)
            app.processEvents()
            target = output / f"{page}-{width}.png"
            if not window.grab().save(str(target)):
                raise RuntimeError(f"Cannot save {target}")
            print(target)
    floating = DictationControl(window.pages["stt"])
    floating.show()
    app.processEvents()
    floating.grab().save(str(output / "dictation-control.png"))
    floating.close()
    window.close()
    app.processEvents()


if __name__ == "__main__":
    main()
