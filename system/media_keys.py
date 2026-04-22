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

KEYEVENTF_KEYUP = 0x0002

# Сколько раз быстро нажать VK_VOLUME_UP/DOWN на одну команду «громче/тише».
# Одно нажатие = ~2% мастер-громкости; 5 даёт ощутимый шаг.
VOLUME_STEP_PRESSES = 5
# Маленькая пауза между нажатиями, чтобы Windows точно зарегистрировал
# каждое (некоторые драйверы пропускают слишком быстрые подряд).
INTER_PRESS_DELAY_MS = 30


def _press_key(vk: int) -> None:
    """Эмулировать одно нажатие+отпускание клавиши через keybd_event."""
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


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
