"""Системные мультимедиа-клавиши Windows (M4).

Тонкий враппер над `keybd_event` (user32). Шлём виртуальные коды:

* `VK_MEDIA_PLAY_PAUSE` (0xB3) — пауза/продолжить. Работает для всех
  плееров с поддержкой Media Key API: Яндекс.Браузер (YouTube, Twitch,
  любая вкладка с аудио), VLC, MPC-HC, Spotify и т.д. Никакого фокуса
  окон, никакого HTTP API, никакой настройки пользователем.
* `VK_VOLUME_UP` (0xAF) / `VK_VOLUME_DOWN` (0xAE) — мастер-громкость
  системы (с привычным OSD-индикатором Windows).

Шаги громкости — одно нажатие = +/-2% мастер-громкости. Чтобы дать
заметное изменение, шлём пачку (`VOLUME_STEP_PRESSES`).

Pause/Resume в системе — это **toggle**, одна и та же клавиша. Команда
«поставь паузу» и «продолжи воспроизведение» физически делают одно и
то же; мы рассчитываем, что пользователь говорит правильную команду
для текущего состояния плеера. Это сознательное упрощение M4 —
альтернатива (HTTP API VLC + window-focus YouTube) описана в M4-плане
и переусложняет первую итерацию.
"""

from __future__ import annotations

import ctypes
import logging
import time

logger = logging.getLogger(__name__)

# Win32 virtual key codes (winuser.h).
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1

# Media-keys требуют флаг EXTENDEDKEY — иначе Chromium-браузеры
# (Яндекс.Браузер, Chrome, Edge) фильтруют синтетические нажатия и
# YouTube не переключает ролик. Громкость и Play/Pause тоже шлём
# как extended — это ближе к поведению физической клавиатуры.
_EXTENDED_VKS = {
    VK_VOLUME_MUTE,
    VK_VOLUME_DOWN,
    VK_VOLUME_UP,
    VK_MEDIA_NEXT_TRACK,
    VK_MEDIA_PREV_TRACK,
    VK_MEDIA_PLAY_PAUSE,
}

# Сколько раз быстро нажать VK_VOLUME_UP/DOWN на одну команду «громче/тише».
# Одно нажатие = ~2% мастер-громкости; 5 даёт ощутимый шаг.
VOLUME_STEP_PRESSES = 5
# Маленькая пауза между нажатиями, чтобы Windows точно зарегистрировал
# каждое (некоторые драйверы пропускают слишком быстрые подряд).
INTER_PRESS_DELAY_MS = 30


# --- SendInput structures (winuser.h) ---------------------------------------

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", _KEYBDINPUT),
        ("mi", _MOUSEINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("u", _INPUT_UNION),
    ]


def _send_key_event(vk: int, key_up: bool) -> None:
    flags = 0
    if vk in _EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    if key_up:
        flags |= KEYEVENTF_KEYUP
    inp = _INPUT(type=INPUT_KEYBOARD)
    inp.ki = _KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
    sent = ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
    if sent != 1:
        err = ctypes.windll.kernel32.GetLastError()
        logger.warning("SendInput не прошёл для vk=0x%02X (sent=%d, err=%d)", vk, sent, err)


def _press_key(vk: int) -> None:
    """Эмулировать одно нажатие+отпускание клавиши через SendInput.

    Для media- и volume-keys автоматически выставляет KEYEVENTF_EXTENDEDKEY —
    без этого флага Chromium-браузеры игнорируют синтетические нажатия.
    """
    _send_key_event(vk, key_up=False)
    _send_key_event(vk, key_up=True)


def play_pause() -> None:
    """Toggle Play/Pause — работает для любого плеера с media-key handler."""
    logger.info("Media key: PLAY_PAUSE")
    _press_key(VK_MEDIA_PLAY_PAUSE)


def next_track() -> None:
    """Следующий трек / следующее видео в плейлисте YouTube."""
    logger.info("Media key: NEXT_TRACK")
    _press_key(VK_MEDIA_NEXT_TRACK)


def prev_track() -> None:
    logger.info("Media key: PREV_TRACK")
    _press_key(VK_MEDIA_PREV_TRACK)


def volume_up(presses: int = VOLUME_STEP_PRESSES) -> None:
    """Поднять мастер-громкость на ``presses`` шагов (~2% каждый)."""
    logger.info("Media key: VOLUME_UP x%d", presses)
    for _ in range(presses):
        _press_key(VK_VOLUME_UP)
        time.sleep(INTER_PRESS_DELAY_MS / 1000)


def volume_down(presses: int = VOLUME_STEP_PRESSES) -> None:
    logger.info("Media key: VOLUME_DOWN x%d", presses)
    for _ in range(presses):
        _press_key(VK_VOLUME_DOWN)
        time.sleep(INTER_PRESS_DELAY_MS / 1000)
