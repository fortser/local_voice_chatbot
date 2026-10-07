"""Screen-based YouTube controls. Imports desktop dependencies only on use."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import sys
import time


class ScreenControlError(RuntimeError):
    """The target is absent, ambiguous, or changed while operating."""


@dataclass(frozen=True)
class Box:
    left: int
    top: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return self.left + self.width // 2, self.top + self.height // 2


@dataclass(frozen=True)
class BrowserWindow:
    hwnd: int
    pid: int
    title: str
    executable: str
    bounds: Box


def foreground_window() -> BrowserWindow | None:
    """Read foreground identity using pointer-sized Win32 signatures."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    title = ctypes.create_unicode_buffer(4096)
    rect = wintypes.RECT()
    if not user32.GetWindowTextW(hwnd, title, len(title)) or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    process = kernel32.OpenProcess(0x1000, False, pid.value)
    if not process:
        return None
    try:
        path = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(path))
        if not kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(length)):
            return None
    finally:
        kernel32.CloseHandle(process)
    return BrowserWindow(int(hwnd), pid.value, title.value, path.value,
                         Box(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top))


def is_yandex_youtube(window: BrowserWindow | None) -> bool:
    if window is None:
        return False
    path = window.executable.replace("/", "\\").lower()
    return (path.endswith("\\browser.exe") and "\\yandex\\" in path
            and "youtube" in window.title.lower())


def match_templates(image, templates: list[Path], *, glyph: bool = False) -> list[Box]:
    """Match actual controls at common DPI scales; merge overlapping hits.

    Player glyphs use a white-pixel mask because video beneath them changes.
    Subscription buttons use colour matching including their pill background.
    """
    import cv2
    import numpy as np

    scene = np.asarray(image.convert("RGB"))
    if glyph:
        scene = (scene.min(axis=2) >= 220).astype(np.uint8) * 255
    found: list[Box] = []
    for path in templates:
        raw = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if raw is None:
            raise ScreenControlError(f"Unreadable template: {path.name}")
        raw = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
        if glyph:
            raw = (raw.min(axis=2) >= 220).astype(np.uint8) * 255
        for scale in (0.8, 1.0, 1.25, 1.5, 1.75, 2.0):
            sample = cv2.resize(raw, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST if glyph else cv2.INTER_LINEAR)
            h, w = sample.shape[:2]
            if h > scene.shape[0] or w > scene.shape[1] or sample.std() < 1:
                continue
            scores = cv2.matchTemplate(scene, sample, cv2.TM_CCOEFF_NORMED)
            # Suppress each neighbourhood to avoid thousands of almost equal hits.
            for _ in range(32):
                _, score, _, location = cv2.minMaxLoc(scores)
                if score < (0.90 if glyph else 0.94):
                    break
                x, y = location
                candidate = Box(x, y, w, h)
                if not any(abs(candidate.center[0] - b.center[0]) < max(w, b.width) / 2
                           and abs(candidate.center[1] - b.center[1]) < max(h, b.height) / 2 for b in found):
                    found.append(candidate)
                scores[max(0, y-h//2):y+h//2+1, max(0, x-w//2):x+w//2+1] = -1
    return found


class YouTubeScreen:
    def __init__(self, asset_dir: Path):
        import pyautogui
        self.gui = pyautogui
        self.asset_dir = asset_dir
        self.window = foreground_window()
        if not is_yandex_youtube(self.window):
            raise ScreenControlError("Foreground window is not Yandex YouTube")
        self.origin = tuple(self.gui.position())
        self._set_region(self.window.bounds)
        self.templates = {name: sorted(asset_dir.glob(f"{name}_*.png"))
                          for name in ("subscribe", "subscribed", "enter", "exit")}
        if not all(self.templates.values()):
            raise ScreenControlError("YouTube button templates are missing")

    def _set_region(self, b: Box) -> None:
        width, height = self.gui.size()
        # Maximized windows can include an invisible 8px border.
        if b.left < -16 or b.top < -16 or b.left + b.width > width + 16 or b.top + b.height > height + 16:
            raise ScreenControlError("Browser must be on the primary monitor")
        self.region = Box(max(0, b.left), max(0, b.top),
                          min(width, b.left+b.width)-max(0, b.left),
                          min(height, b.top+b.height)-max(0, b.top))

    def refresh_geometry(self) -> None:
        """Allow geometry change only after our fullscreen action."""
        current = foreground_window()
        if (current is None or self.window is None or current.hwnd != self.window.hwnd
                or current.pid != self.window.pid or current.title != self.window.title
                or current.executable != self.window.executable):
            raise ScreenControlError("Browser focus or tab changed")
        self._set_region(current.bounds)
        self.window = replace(self.window, bounds=current.bounds)

    def check_target(self) -> None:
        current = foreground_window()
        if (current is None or self.window is None or current.hwnd != self.window.hwnd
                or current.pid != self.window.pid or current.title != self.window.title
                or current.bounds != self.window.bounds or current.executable != self.window.executable):
            raise ScreenControlError("Browser focus, tab or geometry changed")

    def move_over_player(self) -> None:
        self.check_target()
        b = self.region
        self.gui.moveTo(b.left + b.width // 2, b.top + b.height // 3, duration=0.05)

    def _image(self):
        # Wake overlays can outlive the player's controls. Reveal controls on
        # every retry rather than letting them fade while waiting for overlay.
        self.move_over_player()
        time.sleep(0.12)
        b = self.region
        image = self.gui.screenshot(region=(b.left, b.top, b.width, b.height))
        self.check_target()
        return image

    def player_control(self) -> tuple[str, Box] | None:
        image = self._image()
        candidates = []
        for name in ("enter", "exit"):
            for box in match_templates(image, self.templates[name], glyph=True):
                # Fullscreen control is in the right half of the player.
                if box.left > image.width * 0.45 and box.top > image.height * 0.25:
                    if name == "exit" and (box.left < image.width * 0.85 or box.top < image.height * 0.85):
                        continue
                    candidates.append((name, self._absolute(box)))
        if len(candidates) > 1:
            raise ScreenControlError("Ambiguous player control")
        return candidates[0] if candidates else None

    def subscription(self, control: Box) -> tuple[str, Box] | None:
        image = self._image()
        # Only the author strip BELOW the identified player, excluding suggestions.
        y = control.top + control.height - self.region.top + 12
        right = min(image.width, control.left + control.width - self.region.left + 30)
        height = min(image.height - y, max(180, control.height * 10))
        if height <= 0:
            return None
        strip = image.crop((0, y, right, y + height))
        candidates = []
        for name in ("subscribe", "subscribed"):
            for box in match_templates(strip, self.templates[name]):
                candidates.append((name, self._absolute(Box(box.left, box.top+y, box.width, box.height))))
        if len(candidates) > 1:
            raise ScreenControlError("Ambiguous subscription button")
        return candidates[0] if candidates else None

    def click(self, box: Box) -> None:
        self.check_target()
        self.gui.click(*box.center)

    def exit_fullscreen(self) -> None:
        """Send Escape only after the caller has observed fullscreen state."""
        self.check_target()
        self.gui.press("esc")

    def _absolute(self, box: Box) -> Box:
        return Box(box.left + self.region.left, box.top + self.region.top, box.width, box.height)

    def restore_cursor(self) -> None:
        self.gui.moveTo(*self.origin, duration=0.05)
