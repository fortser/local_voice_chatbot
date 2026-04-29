# Changelog

Все заметные изменения проекта «Шурочка» (shura v2) документируются в этом файле.
Формат основан на [Keep a Changelog](https://keepachangelog.com/).

Категории: `Added` / `Changed` / `Fixed` / `Removed` / `Deprecated` / `Security`.

Раздел `[Unreleased]` накапливает изменения до момента, когда они получат версию
или будут перенесены в новый релизный заголовок вручную.

## [Unreleased] — 2026-04-29 21:01

### Added
- `commands/translate_video_command.py` — INSTANT-команда «переведи видео»: эмулирует клик по кнопке «Перевести и озвучить» в панели Яндекс.Браузера поверх YouTube-плеера. Алгоритм: запоминает курсор → паркует мышь в верхнюю треть (50% × 20%) → ждёт 400 мс → `pyautogui.locateOnScreen` с `confidence=0.8` ищет шаблон `assets/yandex_translate_icon.png` → клик по центру → возвращает курсор. Окно браузера не активируется. Retry-бюджет считается динамически от `WAKE_HINT_FADE_IN_MS + WAKE_HINT_HOLD_MS + WAKE_HINT_FADE_OUT_MS` × 1.5 / 0.5 (минимум 4; при конфиге hold=3500 мс — 12 попыток), чтобы покрыть время, пока `WakeHintOverlay` держит полупрозрачную подложку над экраном и ломает шаблон-матчинг. Синонимы: «переведи видео», «переводи видео», «переведи на русский», «включи перевод», «русский перевод». `ack_after = None`; ack проигрывается вручную — отдельные WAV для успеха (`translate_video_after.wav`) и неудачи (`translate_video_fail.wav`).
- `assets/yandex_translate_icon.png` — шаблон кнопки «Перевести и озвучить» для `pyautogui.locateOnScreen`; сделан в полноэкранном режиме YouTube (в оконном режиме шаблон может не совпасть из-за другого фона).

### Changed
- `commands/registry.py` — зарегистрирована `TranslateVideoCommand` (после `ScreenshotCommand` в секции INSTANT).
- `utils/generate_ack_phrases.py` — добавлена поддержка фазы `fail` (ранее валидировались только `before`/`after`): используется для случаев, когда команда не смогла выполниться и нужна отдельная фраза неудачи. Добавлены ack-фразы для `translate_video`: `after` = «включаю перевод», `fail` = «не получилось включить перевод».
- `requirements.txt` — добавлены зависимости `pyautogui>=0.9.54,<1` и `opencv-python>=4.8,<5` (cv2 нужен для параметра `confidence` в `locateOnScreen`).

## [Unreleased] — 2026-04-29 14:33

### Added
- `commands/list_reminders_command.py` — INSTANT-команда «перечисли напоминания»: читает активные напоминания из `ReminderScheduler.list_active()`, собирает одну русскую фразу через `core.reminders.listing.format_reminders_list()` и передаёт в `pipeline._speak_safely()` одним TTS-проходом. LLM не вовлекается. Синонимы: «перечисли напоминания», «перечисли уведомления», «какие напоминания», «какие уведомления», «список напоминаний», «список уведомлений».
- `core/reminders/listing.py` — форматирование списка активных напоминаний для голосового ответа: счётчик в правильном падеже («одно/два/пять напоминаний»), порядковые числительные среднего рода 1–10 + fallback «напоминание номер N», выбор единицы остатка («менее минуты» / минуты / часы с округлением). Один TTS-проход вместо N — экономия VRAM-свопа Whisper↔XTTS. WAV напоминаний намеренно не кэшируем: динамический префикс/остаток, разовое озвучивание, проблемы при смене голоса.
- `tests/test_reminder_listing.py` — 24 теста на склонения, порядковые числительные, форматирование остатка времени и сборку итоговой фразы.

### Changed
- `core/reminders/scheduler.py` — добавлен метод `list_active() -> list[dict]`: отсортированный по `fire_at` срез живых таймеров с фильтрацией через storage. Используется `ListRemindersCommand`.
- `commands/registry.py` — зарегистрирована `ListRemindersCommand` (после `ReminderCommand`).
- `commands/reminder_command.py` — добавлены два синонима: «поставь уведомление», «добавь уведомления».
- `tests/fixtures/commands_snapshot.json` — пересобран через `scripts/dump_commands_snapshot.py`; подтянулись pre-existing расхождения для `pause`/`resume`/`volume_up`/`volume_down`/`seek_forward`/`note`/`question` — снапшот теперь соответствует фактическому реестру.

## [Unreleased] — 2026-04-29 14:15

### Added
- `.claude/agents/docs-keeper.md` — субагент автообновления `CHANGELOG.md` и `PROJECT_INDEX.md` (`/update-docs`); модель `claude-sonnet-4-6` для качественного аудита и описаний новых файлов.
- `.claude/skills/docs-keeper/SKILL.md` — скилл-триггер для агента.
- `.claude/hooks/track_changes.py` — `PostToolUse`-хук, накапливает список изменённых `.py`/`.md` в `%TEMP%`.
- `.claude/hooks/changelog_reminder.py` — `Stop`-хук, в конце сессии напоминает про незафиксированные изменения.
- `CHANGELOG.md` — этот файл, инициализирован.
- `system/keep_awake.py` — anti-screensaver модуль: удерживает дисплей активным во время диалога через канонический Win32 API `SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED)` — тот же механизм, что VLC/Chromium при fullscreen-видео. API: `acquire(hold_seconds, *, reason="")`, `release()`, `is_active()`. Внутри: `threading.Timer` на отложенный релиз, идемпотентность через `_lock`, nudge `LASTINPUTINFO` через mouse-event при каждом `acquire`. Каждый новый вызов перезапускает таймер, что автоматически продлевает удержание на цепочке turn'ов. На крах процесса флаг снимается ОС.
- `KeepAwakeSettings` — новая секция в `config_model.py` с полем `hold_after_turn_s: float = 120.0`.
- `KEEP_AWAKE_AFTER_TURN_S` — константа-shim в `config.py` для совместимости с прямым импортом.

### Changed
- `CLAUDE.md` — добавлена секция «Documentation map» с указателями на `PROJECT_INDEX.md`, `CHANGELOG.md`, `README.md`, `MIGRATION_PLAN.md` и описанием агента `docs-keeper`.
- `system/media_keys.py` — удалён весь dead-code попыток dismiss'а активного screensaver'а синтетическим вводом (F24 keystroke, mouse-move/click, `SPI_GETSCREENSAVERRUNNING`, `_is_screensaver_running()`, `wake_display()`, вызовы `wake_display()` в `play_pause/next_track/prev_track/arrow_*/volume_*`, константы `VK_F24`, `MOUSEEVENTF_LEFTDOWN/LEFTUP`, `WAKE_DISPLAY_DELAY_MS`). Причина: сторонние screensaver'ы (3Planesoft) запускаются на отдельном Windows desktop'е, `SendInput` не может пересечь его границу. Оставлены `_send_mouse_event`, `MOUSEEVENTF_MOVE`, `MOUSEEVENTF_MOVE_NOCOALESCE` — их теперь импортирует `keep_awake.py` для nudge'а `LASTINPUTINFO`. Обновлён module docstring. Архитектурный сдвиг: «снять активный screensaver» → «не дать ему активироваться» через `system/keep_awake.py`.
- `main.py` — `VoicePipeline._process_voice_input_locked` обёрнут в try/finally: `keep_awake.acquire(KEEP_AWAKE_AFTER_TURN_S, reason="turn_start/turn_end")` на входе и выходе turn'а; в `VoicePipeline.stop()` добавлен `keep_awake.release()`.
- `core/wake_word.py` — после распознавания wake-слова (до бипа активации) вызывается `keep_awake.acquire(KEEP_AWAKE_AFTER_TURN_S, reason="wake_word")`, чтобы закрыть окно «услышали → запись вопроса», которое `_process_voice_input_locked` ещё не защищает.

### Removed
- Весь код попыток dismiss'ить активный сторонний screensaver через `SendInput` — см. `system/media_keys.py` в разделе Changed.
