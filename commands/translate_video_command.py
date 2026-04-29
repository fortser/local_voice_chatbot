"""TranslateVideoCommand — «переведи видео» (Этап YouTube/Яндекс).

INSTANT-команда: эмулирует клик по кнопке «Перевести и озвучить» в
панели Яндекс.Браузера поверх плеера YouTube.

Сценарий:

1. Запоминаем текущую позицию курсора.
2. «Шевелим» курсором в верхнюю треть экрана — в полноэкранном плеере
   YouTube панель Яндекса появляется только при движении мыши и
   прячется через ~2 сек.
3. ``pyautogui.locateOnScreen`` ищет шаблон ``assets/yandex_translate_icon.png``
   с допуском (``confidence``); ищем на основном дисплее.
4. Если иконка найдена — клик по её центру, ack «включаю перевод».
5. Если не найдена — ack «не получилось включить перевод», лог.
6. В любом случае возвращаем курсор в исходную точку, чтобы не
   мешать пользователю.

Окно Яндекс.Браузера НЕ активируем (``SetForegroundWindow``) —
осознанно: пользователь обычно уже смотрит видео в фуллскрине,
а воровать фокус у Шурочки/других окон не хочется. Если YouTube
не на переднем плане, поиск шаблона провалится → команда честно
скажет «не получилось».

Зависимости: ``pyautogui`` (экранный клик), ``Pillow`` (PIL —
бэкенд скриншотов), ``opencv-python`` (cv2 — нужен для параметра
``confidence`` в ``locateOnScreen``).
"""

from __future__ import annotations

import logging
import time

from commands.base import BaseCommand, CommandContext, CommandType
from config import (
    BASE_DIR,
    WAKE_HINT_FADE_IN_MS,
    WAKE_HINT_FADE_OUT_MS,
    WAKE_HINT_HOLD_MS,
)

logger = logging.getLogger(__name__)


# Путь к шаблону кнопки. Скриншот сделан из полноэкранного режима
# YouTube — в оконном режиме фон/тени отличаются, шаблон не совпадёт.
_ICON_PATH = BASE_DIR / "assets" / "yandex_translate_icon.png"

# confidence=0.8 — компромисс между допуском к субпиксельным
# различиям рендера и риском ложных срабатываний на других
# UI-элементах. При смене иконки Яндексом снизим/обновим шаблон.
_MATCH_CONFIDENCE = 0.8

# Сколько ждать после движения мыши до того, как панель Яндекса
# успеет появиться. Эмпирически 300–500 мс достаточно.
_PANEL_SETTLE_SEC = 0.4

# Retry-параметры. После wake-word'а UI рисует WakeHintOverlay поверх
# всего экрана с полупрозрачной подложкой; пока оверлей не исчезнет,
# скриншот подкрашен и ``locateOnScreen`` промахивается. Поэтому если
# первая попытка не нашла иконку — спим и пробуем ещё.
#
# Бюджет считаем от текущего конфига: полный жизненный цикл оверлея
# (fade-in + hold + fade-out) с запасом 1.5×, чтобы покрыть случаи,
# когда оверлей не успели погасить через ``hide_now()``. Так при смене
# ``WAKE_HINT_HOLD_MS`` в settings.toml retry-логика подстраивается
# автоматически — ничего не нужно править здесь.
_OVERLAY_LIFETIME_SEC = (
    WAKE_HINT_FADE_IN_MS + WAKE_HINT_HOLD_MS + WAKE_HINT_FADE_OUT_MS
) / 1000.0
_LOCATE_RETRY_DELAY_SEC = 0.5
_LOCATE_RETRIES = max(
    4, int(_OVERLAY_LIFETIME_SEC * 1.5 / _LOCATE_RETRY_DELAY_SEC) + 1,
)

# Куда «парковать» курсор, чтобы спровоцировать показ панели.
# По X — центр экрана; по Y — 20% сверху, в зоне панели Яндекса.
# Не используем углы — в углах активируется PyAutoGUI failsafe.
_PARK_X_RATIO = 0.5
_PARK_Y_RATIO = 0.2


class TranslateVideoCommand(BaseCommand):
    name = "translate_video"
    command_type = CommandType.INSTANT
    # ack играем вручную: успех и неудача требуют разных фраз, а
    # ``ack_after`` в пайплайне один. См. паттерн ListRemindersCommand.
    ack_after = None
    synonyms = (
        "переведи видео",
        "переводи видео",
        "переведи на русский",
        "включи перевод",
        "русский перевод",
    )

    # Имена pre-rendered ack-WAV в assets/ack/. Генерация —
    # ``python -m utils.generate_ack_phrases``.
    _ACK_OK = "translate_video_after.wav"
    _ACK_FAIL = "translate_video_fail.wav"

    def execute(self, ctx: CommandContext) -> bool:
        # Импортируем pyautogui лениво: на CI / в headless-тестах
        # модуль может упасть при импорте (нет дисплея). Команда нужна
        # только в Windows-десктопе с активным сеансом.
        try:
            import pyautogui
        except Exception:
            logger.exception("TranslateVideoCommand: pyautogui import failed")
            self._play_fail_ack(ctx)
            return True

        if not _ICON_PATH.is_file():
            logger.error(
                "TranslateVideoCommand: шаблон не найден: %s", _ICON_PATH,
            )
            self._play_fail_ack(ctx)
            return True

        # Запоминаем курсор, чтобы вернуть после клика.
        try:
            origin = pyautogui.position()
        except Exception:
            logger.exception("TranslateVideoCommand: position() failed")
            self._play_fail_ack(ctx)
            return True

        screen_w, screen_h = pyautogui.size()
        park_xy = (int(screen_w * _PARK_X_RATIO), int(screen_h * _PARK_Y_RATIO))

        box = None
        try:
            # Движение → панель Яндекса всплывает над плеером.
            pyautogui.moveTo(park_xy[0], park_xy[1], duration=0.05)
            time.sleep(_PANEL_SETTLE_SEC)

            for attempt in range(1, _LOCATE_RETRIES + 1):
                box = pyautogui.locateOnScreen(
                    str(_ICON_PATH), confidence=_MATCH_CONFIDENCE,
                )
                if box is not None:
                    if attempt > 1:
                        logger.info(
                            "TranslateVideoCommand: иконка найдена с %d-й попытки",
                            attempt,
                        )
                    break
                if attempt < _LOCATE_RETRIES:
                    # Скорее всего, поверх экрана ещё держится WakeHintOverlay
                    # (полупрозрачная подложка сдвигает цвета иконки). Ждём,
                    # пока он отыграет fade-out, и пробуем заново.
                    time.sleep(_LOCATE_RETRY_DELAY_SEC)
        except Exception:
            # locateOnScreen без cv2 кидает NotImplementedError на
            # confidence; mss/PIL могут падать на multi-DPI.
            logger.exception("TranslateVideoCommand: поиск иконки упал")
            box = None

        if box is None:
            logger.info(
                "TranslateVideoCommand: иконка не найдена "
                "(confidence>=%.2f)", _MATCH_CONFIDENCE,
            )
            print("🌐 Иконка перевода не найдена на экране.")
            self._restore_cursor(pyautogui, origin)
            self._play_fail_ack(ctx)
            return True

        cx, cy = pyautogui.center(box)
        logger.info(
            "TranslateVideoCommand: иконка найдена в (%d,%d), кликаю", cx, cy,
        )
        try:
            pyautogui.click(cx, cy)
        except Exception:
            logger.exception("TranslateVideoCommand: click() failed")
            self._restore_cursor(pyautogui, origin)
            self._play_fail_ack(ctx)
            return True

        self._restore_cursor(pyautogui, origin)
        print("🌐 Включаю перевод видео.")
        self._play_ok_ack(ctx)
        return True

    @staticmethod
    def _restore_cursor(pyautogui_mod, origin) -> None:
        try:
            pyautogui_mod.moveTo(origin[0], origin[1], duration=0.05)
        except Exception:
            logger.debug("TranslateVideoCommand: restore cursor failed",
                         exc_info=True)

    def _play_ok_ack(self, ctx: CommandContext) -> None:
        pipeline = ctx.pipeline
        play_ack = getattr(pipeline, "_play_ack", None)
        if play_ack is not None:
            play_ack(self._ACK_OK)

    def _play_fail_ack(self, ctx: CommandContext) -> None:
        pipeline = ctx.pipeline
        play_ack = getattr(pipeline, "_play_ack", None)
        if play_ack is not None:
            play_ack(self._ACK_FAIL)
