"""Unicode insertion into the foreground Windows application, without clipboard changes."""

from __future__ import annotations

import ctypes
import os


class _Mouse(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_int32), ("dy", ctypes.c_int32),
                ("mouseData", ctypes.c_uint32), ("dwFlags", ctypes.c_uint32),
                ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.c_size_t)]


class _Keyboard(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_uint16), ("wScan", ctypes.c_uint16),
                ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32),
                ("dwExtraInfo", ctypes.c_size_t)]


class _Payload(ctypes.Union):
    _fields_ = [("mi", _Mouse), ("ki", _Keyboard)]


class _Input(ctypes.Structure):
    _anonymous_ = ("payload",)
    _fields_ = [("type", ctypes.c_uint32), ("payload", _Payload)]


def unicode_inputs(text: str):
    # Dictation never submits a form/chat. Explicit line separators become spaces.
    data = text.replace("\r", " ").replace("\n", " ").replace("\t", " ").encode("utf-16-le")
    units = [int.from_bytes(data[index:index + 2], "little") for index in range(0, len(data), 2)]
    inputs = (_Input * (len(units) * 2))()
    for index, unit in enumerate(units):
        for offset, flags in ((0, 0x0004), (1, 0x0004 | 0x0002)):
            inputs[index * 2 + offset].type = 1
            inputs[index * 2 + offset].ki = _Keyboard(0, unit, flags, 0, 0)
    return inputs


def inject_text(text: str) -> bool:
    """Return False for our own window. Fail visibly on blocked/partial input.

    SendInput cannot acknowledge application-side acceptance. Never retry a
    partial send: doing so could duplicate text already received by the target.
    """
    if os.name != "nt":
        raise RuntimeError("Вставка в активное окно доступна только в Windows")
    api = ctypes.WinDLL("user32", use_last_error=True)
    api.GetForegroundWindow.restype = ctypes.c_void_p
    api.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    api.GetWindowThreadProcessId.restype = ctypes.c_uint32
    api.GetAsyncKeyState.argtypes = [ctypes.c_int]
    api.GetAsyncKeyState.restype = ctypes.c_int16
    api.SendInput.argtypes = [ctypes.c_uint32, ctypes.POINTER(_Input), ctypes.c_int]
    api.SendInput.restype = ctypes.c_uint32
    window = api.GetForegroundWindow()
    if not window:
        raise RuntimeError("Нет активного окна. Текст сохранён в разделе распознавания.")
    process = ctypes.c_uint32()
    if not api.GetWindowThreadProcessId(window, ctypes.byref(process)):
        raise RuntimeError("Не удалось определить активное окно")
    if process.value == os.getpid():
        return False
    if any(api.GetAsyncKeyState(key) & 0x8000 for key in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
        raise RuntimeError("Вставка пропущена: удерживается клавиша-модификатор. Текст доступен в разделе распознавания.")
    inputs = unicode_inputs(text)
    if not inputs:
        return True
    if api.GetForegroundWindow() != window:
        raise RuntimeError("Окно изменилось перед вставкой. Текст доступен в разделе распознавания.")
    count = api.SendInput(len(inputs), inputs, ctypes.sizeof(_Input))
    if count != len(inputs):
        raise RuntimeError("Windows не подтвердила полную вставку. Проверьте активное окно; текст сохранён в разделе распознавания.")
    return True
