# PROJECT_INDEX — «Шурочка» (Voice AI Assistant v2)

## О проекте

**Шурочка** — локальный голосовой ассистент для Windows, работающий полностью оффлайн
на GPU-машине пользователя. Задача — принимать голосовые команды (управление плеером,
громкостью, заметки, скриншоты, свободные вопросы к LLM) без облачных сервисов и
отправки звука наружу.

### Цели и предназначение
- **Приватность**: все модели (Whisper STT, Silero/XTTS TTS, LLM через Ollama/LM Studio) крутятся локально.
- **Голосовой контроль системы**: медиа-плееры, громкость, mute сторонних аудио-сессий, скриншоты, диктовка заметок.
- **Q&A через локальный LLM**: только по явным триггерам («ответь на вопрос», «подскажи», «нужна помощь»), чтобы шум Whisper'а не уходил в модель.
- **Дежурный режим**: постоянное прослушивание кодового слова «Шурочка» и активация по нему.

### Функционал и возможности
- Пайплайн `AudioStream → VAD → STT (Whisper) → CommandRouter → (Command | LLM) → TTS → AudioPlayer`.
- **Wake-word** активация («Шурочка») с ack-бипом и запасной глобальной hotkey (`Ctrl+Alt+S`).
- **Команды** (M1–M8): `запиши заметку`, `сделай скриншот`, `пауза/продолжи`, `выключи/включи звук`, `громче/тише`, `следующий/предыдущий трек`, `стоп`, `ответь на вопрос …`.
- **Сессии**: все заметки и скриншоты складываются в `logs/sessions/YYYY-MM-DD_HH-MM/`.
- **UI**: Tkinter-окно с уровнем сигнала, индикаторами здоровья подсистем, overlay-виджетом статуса поверх всех окон и иконкой в системном трее.
- **IPC**: TCP line-JSON сервер (`127.0.0.1:9999`) с методами `health_check`, `generate_only`, `transcribe_and_respond`, `recalibrate` — другие процессы могут разговаривать с тем же инстансом pipeline.
- **Взаимозаменяемые провайдеры**: Whisper (STT), Ollama/LM Studio (LLM), Silero/XTTS (TTS) — все реализуют ABC из `core/base.py`, переключение через `config.py`.
- **GPU VRAM swap**: если TTS == XTTS на CUDA, Whisper выгружается на время синтеза и перезагружается после — они не помещаются в VRAM одновременно.

### Окружение
Python 3.10, Windows 10, CUDA 12.x. Зависимости: `requirements.txt`. LLM-бекенд запускается
отдельно (Ollama на `:11434` или LM Studio на `:1234`).

### Точки входа
- `python main.py` — Tkinter UI (по умолчанию).
- `python main.py --mode console` — REPL + IPC.
- `python main.py --mode ipc` — headless IPC-сервер.
- `python check_stage_<N>.py` — поэтапные ручные валидаторы (удаляются после приёмки).
- `python -m utils.audio_devices` / `python -m utils.tts_speakers` — диагностические CLI.

---

## Структура файлов

### Корень проекта

| Файл | Назначение | Ключевые точки входа / выхода |
|---|---|---|
| `main.py` | Главный оркестратор. Класс `VoicePipeline` владеет AudioStream, VAD, STT, LLM, TTS, AudioPlayer, SessionManager, MuteController, CommandRouter, WakeWordListener. Один `threading.Lock` сериализует доступ к микрофону/моделям из REPL, IPC и wake-word listener. Содержит CLI-парсер (`--mode console/ipc/ui`, `--no-ipc`) и fallback-фразы. Использует: `argparse`, `threading`, `bootstrap.bootstrap`, `commands.*`, `core.*`, `ipc.*`, `system.*`. | Вход: `main()` / импортирует `VoicePipeline`. Выход: синтезированный WAV в динамики + файлы в `logs/sessions/`. |
| `bootstrap.py` | Однократная инициализация для всех entry points: форсит UTF-8 stdout, поднимает `logging_config.setup_logging()`, печатает текущие Windows-дефолты аудио-устройств. Использует `utils.audio_devices.get_current_devices`, `logging_config.setup_logging`. | Функция `bootstrap(verbose=True) → BootstrapResult`. |
| `config.py` | Централизованные настройки: пути, sample-rate, VAD-пороги, `WHISPER_MODEL_SIZE`, `LLM_PROVIDER`, `TTS_PROVIDER`, системный промпт, wake-word + алиасы, таймауты диктовки/дежурки, параметры бипов, ACK-фразы команд, overlay/tray-hotkey. Только константы, импортов кода нет. | Экспортирует константы. |
| `logging_config.py` | `setup_logging()` — идемпотентный конфиг: ротируемый файловый хендлер (`logs/voice_ai.log`, 5 МБ × 3) + консольный; отдельный logger `unrecognized` → `logs/unrecognized.log`. Использует `logging`, `logging.handlers.RotatingFileHandler`. | Функция `setup_logging()`. |
| `requirements.txt` | Список pip-зависимостей: `openai-whisper`, `silero`, `TTS` (Coqui XTTS), `pydantic`, `sounddevice`, `soundfile`, `numpy`, `torch`, `pycaw`, `comtypes`, `mss`, `pillow`, `pystray`, `pynput` и пр. | — |
| `CLAUDE.md` | Инструкции для Claude Code по проекту. | — |
| `MIGRATION_PLAN.md` | План миграции M1–M8 (команды, wake-word, UI overlay). | — |
| `VOICE_AI_PROJECT_SPECIFICATION.md` | Исходная спецификация этапов 0–8. | — |
| `check_stage_5.py` | Ручная приёмка Этапа 5 (pipeline STT→LLM→TTS в консоли). | CLI-скрипт. |
| `check_stage_6.py` | Ручная приёмка Этапа 6 (IPC-сервер + 4 метода API + негативные кейсы). | CLI-скрипт. |
| `check_stage_7.py` | Ручная приёмка Этапа 7 (Tkinter UI с диагностикой). | CLI-скрипт. |
| `check_stage_8.py` | Ручная приёмка Этапа 8 (wake-word «Шурочка» + дежурный режим). | CLI-скрипт. |
| `check_stage_m4.py` | Приёмка M4: pause/resume (media keys), mute/unmute (pycaw per-session), volume up/down. | CLI-скрипт. |
| `check_stage_m6.py` | Приёмка M6: Stop (голос), Seek next/prev track, Cancel (Esc). | CLI-скрипт. |
| `check_stage_m8.py` | Приёмка M8: overlay-виджет, systray, глобальная hotkey возврата в дежурку. | CLI-скрипт. |
| `claude_start.bat` / `go.bat` / `gitpush.bat` / `ЯMake_llm_report.bat` | Локальные BAT-лаунчеры. | — |
| `Полный список голосовых команд.txt`, `новые фичи.txt`, `список пожеланий.txt`, `гитхаб.txt` | Заметки/TODO пользователя. | — |

### `core/` — подсистемы пайплайна

| Файл | Назначение | Ключевые символы / библиотеки |
|---|---|---|
| `core/__init__.py` | Фабрики провайдеров: `create_stt_provider()`, `create_llm_provider()`, `create_tts_provider()` читают `config` и выбирают нужный класс из `_STT_FACTORIES / _LLM_FACTORIES / _TTS_FACTORIES`. | Экспорт: 3 фабрики + ABC из `core.base`. |
| `core/base.py` | ABC для инверсии управления: `STTProvider`, `LLMProvider`, `TTSProvider`. | `abc.ABC`, `abstractmethod`. |
| `core/audio_stream.py` | `AudioStream` — фоновый микрофонный reader на `sounddevice`. Считает per-chunk RMS (int16), держит скользящий `noise_floor`, выдаёт `(rms, percent)` в bounded queue для UI и в callback; `chunk_queue` питает VAD. | `sounddevice.InputStream`, `queue.Queue`, `threading.Thread`, `numpy`. |
| `core/vad.py` | `VoiceActivityDetector` — `calibrate()` (макс RMS × 1.8, пол `MIN_ENERGY_THRESHOLD`), `record_until_silence()` (пишет WAV до паузы `PAUSE_THRESHOLD`). Адаптивный drift порога к шуму. | `numpy`, `wave`; потребляет `AudioStream.chunk_queue`. |
| `core/stt.py` | `WhisperSTT` — `load_model()` / `transcribe(path)` / `unload_model()`. Язык зашит в `config.WHISPER_LANGUAGE`. После unload — `gc.collect()` + `torch.cuda.empty_cache()`. | `openai-whisper`, `torch`. |
| `core/llm.py` | `OllamaLLM(LLMProvider)` — обёртка над `OllamaClient`: авто-детект thinking-моделей (3× токенов, расширенный timeout), `generate()` пропускает результат через `clean_llm_response()` (снимает `<think>` / harmony-теги). | `core.ollama_client`, `core.prompt_manager`. |
| `core/llm_errors.py` | Единая таксономия `LLMErrorKind` для Ollama + LM Studio. `classify_http_error()` решает что ретраить (`TIMEOUT`, `RATE_LIMIT`). | `enum.Enum`, `requests.exceptions`. |
| `core/ollama_client.py` | HTTP-клиент Ollama: `generate()`, `list_models()`, `is_running()`. Retry с backoff `delay*(attempt+2)`. | `requests`, `core.llm_errors`. |
| `core/lmstudio_client.py` | Backend LM Studio (OpenAI-compatible REST). `LMStudioLLM` симметричен `OllamaLLM`. | `requests`, `core.llm_errors`, `core.prompt_manager`. |
| `core/tts.py` | `XTTSProvider(TTSProvider)` — Coqui XTTS-v2 zero-shot voice clone. Lazy-import `TTS.api`, `COQUI_TOS_AGREED=1`. | `TTS.api.TTS`, `torch`, `core.tts_utils`. |
| `core/silero_tts.py` | `SileroTTS(TTSProvider)` — русская модель Silero v4_ru/v5 через `torch.hub.load`. CPU-friendly, освобождает GPU для Whisper. | `torch`, `torch.hub`, `soundfile`. |
| `core/tts_utils.py` | Хелперы TTS: резолвинг пути к speaker-WAV (с fail-fast), генерация уникального timestamp-имени выходного WAV. | `pathlib.Path`, `datetime`. |
| `core/audio_output.py` | `AudioPlayer` — проигрывание WAV / numpy-массива через `sounddevice`, блокирующе до конца. Используется для TTS-ответов и ack-бипов. | `sounddevice.play`, `soundfile.read`, `numpy`. |
| `core/audio_beep.py` | `generate_beep(freq, duration_ms, sample_rate)` — синусоидальный beep с fade-in/out, float32 [-1,1]. Для wake-word активации / dictate-стартера. | `numpy`. |
| `core/wake_word.py` | `WakeWordListener` — daemon-поток: окна по 2–3 сек через Whisper, match против `WAKE_WORD` + алиасов, на срабатывание — beep + ack + callback в pipeline. `contains_wake_word()`, `_normalize()` — чистые функции, покрыты тестами. | `threading`, `WhisperSTT`, `core.audio_stream`. |
| `core/preprocessing.py` | `compute_rms_file()` — файловый RMS для калибровок (int16 domain, совместим с voice_converter.py). Normalisation, resampling — стабы. | `numpy`, `soundfile`. |
| `core/prompt_manager.py` | `clean_llm_response()` — снимает `<think>…</think>`, harmony-каналы `<|channel|>analysis/final`, freeform `Thinking Process:`. `detect_thinking_markers()` — авто-распознавание thinking-моделей. | `re`. |

### `core/reminders/` — подсистема напоминаний (M10)

| Файл | Назначение | Ключевые символы |
|---|---|---|
| `core/reminders/__init__.py` | Публичный фасад пакета: реэкспортирует `parse_reminder_tail`, `ReminderScheduler`, `ReminderStorage`. | — |
| `core/reminders/parser.py` | Regex-парсер хвоста команды «напомни через N минут/часов …». Возвращает `(count, unit, text)`. Не-regex формы («через полчаса», «в 15:30») осознанно не поддерживаются. | `re`, `commands.router.normalize`. |
| `core/reminders/storage.py` | JSON-персистентность списка напоминаний: атомарная запись через tmp-файл + `os.replace`. Поле `fire_at` — абсолютный POSIX timestamp. Метод `list_active()` возвращает все записи из файла. | `json`, `pathlib`. |
| `core/reminders/scheduler.py` | `ReminderScheduler` — `threading.Timer` на каждое активное напоминание. При срабатывании вызывает `fire_callback(text)` под pipeline-lock'ом (блокируется, если идёт другой турн). Просроченные напоминания при старте проигрываются по возрастанию `fire_at`. Метод `list_active() -> list[dict]` — отсортированный по `fire_at` срез живых таймеров. | `threading.Timer`, `uuid`, `core.reminders.storage`. |
| `core/reminders/listing.py` | Форматирование списка активных напоминаний в одну русскую фразу для TTS. Счётчик в нужном падеже, порядковые числительные среднего рода 1–10 + fallback, выбор единицы остатка («менее минуты» / минуты / часы). Используется `ListRemindersCommand`. | `core.reminders.num_to_words`, `core.reminders.num_to_words_manual`. |
| `core/reminders/num_to_words.py` | Фабрика конвертера чисел в слова: переключается через `config.NUM_TO_WORDS_BACKEND` между ручным словарём (`"manual"`) и библиотекой `num2words` (`"num2words"`). | `config.NUM_TO_WORDS_BACKEND`. |
| `core/reminders/num_to_words_manual.py` | Ручной конвертер 1–999 в русские слова + функция `plural_form()` для склонения единиц (минута/час/секунда). Без внешних зависимостей. | `_number_to_words()`, `plural_form()`. |
| `core/reminders/num_to_words_external.py` | Обёртка над библиотекой `num2words` — альтернатива `num_to_words_manual` для расширенного диапазона. Активируется при `NUM_TO_WORDS_BACKEND="num2words"`. | `num2words`. |

### `commands/` — голосовые команды (M1–M6)

| Файл | Назначение | Ключевые символы |
|---|---|---|
| `commands/__init__.py` | Публичный фасад: `BaseCommand`, `CommandType`, `CommandContext`, `CommandRouter`, `CommandRegistry`, `build_default_registry()`. | Реэкспорт. |
| `commands/base.py` | `BaseCommand` ABC (`name`, `synonyms`, `type`, `execute(ctx, tail)`). `CommandType` enum (INSTANT / DICTATE / LLM). `CommandContext` — DTO с ссылками на pipeline, session_manager, mute_controller и т.д. | `abc.ABC`, `dataclass`. |
| `commands/router.py` | `CommandRouter.match(text)` — нормализация (lower, `ё→е`, пунктуация, whitespace), сопоставление по синонимам по убыванию длины, exact или `prefix + " "`. | Чистый текстовый матчер. |
| `commands/registry.py` | `CommandRegistry` (name→instance) + `build_default_registry(ctx_factory)` — собирает все команды; single words отфильтровываются (anti-false-positive защита). | Iterable protocol. |
| `commands/note_command.py` | `NoteCommand` — «запиши заметку …». Fast path (≥N слов после триггера) или dictation через `pipeline.dictate()`. Пишет в `session_manager.save_note()`. | `CommandType.DICTATE`. |
| `commands/screenshot_command.py` | `ScreenshotCommand` — «сделай скриншот». INSTANT. Зовёт `system.screenshot.take_screenshot()` + `session_manager.save_screenshot()`. | `CommandType.INSTANT`. |
| `commands/question_command.py` | `QuestionCommand` — единственный легитимный путь к LLM. Триггеры: «ответь на вопрос», «подскажи», «нужна помощь». Fast path или dictation. | `CommandType.LLM`. |
| `commands/player_commands.py` | `PlayPauseCommand`, `MuteCommand`, `UnmuteCommand`, `VolumeUpCommand`, `VolumeDownCommand` — обёртки над `system.media_keys` и `system.audio_session_mute.MuteController`. | `VK_MEDIA_*`, pycaw. |
| `commands/stubs.py` | `CancelCommand` (Esc через hotkey, не голосом — защита от ложных срабатываний), `StopCommand` (выключает wake listener), `SeekForward/Backward` (VK_MEDIA_NEXT/PREV_TRACK). | `system.media_keys`. |
| `commands/list_reminders_command.py` | `ListRemindersCommand` — INSTANT-команда «перечисли напоминания». Читает активные таймеры из `ReminderScheduler.list_active()`, собирает одну русскую фразу через `core.reminders.listing.format_reminders_list()` и произносит её одним TTS-проходом без LLM. Синонимы: «перечисли напоминания/уведомления», «какие напоминания/уведомления», «список напоминаний/уведомлений». | `CommandType.INSTANT`; `core.reminders.listing`, `core.reminders.scheduler`. |
| `commands/translate_video_command.py` | `TranslateVideoCommand` — INSTANT-команда «переведи видео»: эмулирует клик по кнопке «Перевести и озвучить» в панели Яндекс.Браузера поверх YouTube-плеера. Алгоритм: паркует курсор в верхнюю треть экрана, ждёт появления панели (400 мс), ищет шаблон `assets/yandex_translate_icon.png` через `pyautogui.locateOnScreen` (`confidence=0.8`), кликает и возвращает курсор. Окно браузера не активирует. Retry-бюджет динамически считается от конфига `WakeHintOverlay` (минимум 4, при hold=3500 мс — 12 попыток). `ack_after = None`; ack проигрывается вручную через `pipeline._play_ack()` — отдельные WAV для успеха и неудачи. Синонимы: «переведи видео», «переводи видео», «переведи на русский», «включи перевод», «русский перевод». | `CommandType.INSTANT`; `pyautogui` (lazy-import), `config.WAKE_HINT_*_MS`, `BASE_DIR`. WAV-ключи: `translate_video_after.wav`, `translate_video_fail.wav`. |

### `ipc/` — inter-process API

| Файл | Назначение | Ключевые символы |
|---|---|---|
| `ipc/__init__.py` | Публичный фасад: `VoiceAIServer`, `VoiceAIClient`, `ErrorCode`. | — |
| `ipc/protocol.py` | Фрейминг: один JSON / строку `\n`. `MAX_LINE_BYTES = 1 MiB`. `ErrorCode` enum (UNKNOWN_METHOD, INVALID_PARAMS, INTERNAL_ERROR, PIPELINE_BUSY …). | `json`, `enum`. |
| `ipc/schemas.py` | Pydantic-схемы запросов/ответов. Envelope: `{id, method, params}` / `{id, status, result|error}`. Per-method param-классы (`GenerateOnlyParams`, `TranscribeAndRespondParams`, …). | `pydantic.BaseModel`. |
| `ipc/server.py` | `VoiceAIServer(ThreadingTCPServer)` — один поток на соединение, обработчики берут `pipeline.lock`, один request / соединение. 4 метода: `health_check`, `generate_only`, `transcribe_and_respond`, `recalibrate`. | `socketserver.ThreadingTCPServer`. |
| `ipc/client.py` | `VoiceAIClient` — blocking sync TCP-клиент, connection-per-call. `IPCError` с `code` от сервера. | `socket`. |

### `ui/` — Tkinter-интерфейс

| Файл | Назначение | Ключевые символы |
|---|---|---|
| `ui/__init__.py` | Пустой. | — |
| `ui/tkinter_ui.py` | `VoiceAIApp` — главное окно (Этап 7). Владеет `VoicePipeline` на worker thread, UI в main thread. Кнопки «🎤 Слушай», «🔄 Перекалибровать», «🛌 Дежурный», уровнемер RMS с маркерами шума/порога, health pills (Whisper/LLM/TTS), лог-вьюер. `run_ui()` — entry point. | `tkinter`, `tkinter.ttk`, `threading`. |
| `ui/overlay.py` | `Overlay` — полупрозрачный `tk.Toplevel` поверх всех окон (статус Пассивен / Слышу / Говорите / Обрабатываю / Отвечаю). Click-through на Windows через `WS_EX_TRANSPARENT | WS_EX_LAYERED` (ctypes user32). | `tkinter.Toplevel`, `ctypes`. |
| `ui/tray.py` | `SystemTrayIcon` — `pystray`-иконка в трее (daemon thread). Меню: Включить ассистента / Открыть папку сессии / Выйти. Иконка генерируется `PIL`. | `pystray`, `PIL.Image`. |
| `ui/hotkey.py` | `HotkeyListener` — глобальная hotkey (`WAKE_HOTKEY`, по умолчанию Ctrl+Alt+S) через `pynput.keyboard.GlobalHotKeys`; включает wake-listener обратно (страховка от голосового StopCommand). | `pynput.keyboard`. |

### `system/` — интеграция с Windows

| Файл | Назначение | Ключевые символы |
|---|---|---|
| `system/__init__.py` | Package placeholder. | — |
| `system/session_manager.py` | `SessionManager` — ленивая папка `logs/sessions/YYYY-MM-DD_HH-MM/` (+ суффикс при коллизии). Потокобезопасен (`threading.Lock`). `save_note(text)`, `save_screenshot(png_bytes)`. | `pathlib`, `threading`. |
| `system/screenshot.py` | `take_screenshot(monitor=None) → png_bytes` через `mss`. По умолчанию — основной монитор. | `mss`, `PIL.Image`. |
| `system/media_keys.py` | Тонкий враппер над Win32 `SendInput` (user32): `VK_MEDIA_PLAY_PAUSE` (0xB3), `VK_VOLUME_UP/DOWN` (0xAF/0xAE), `VK_MEDIA_NEXT/PREV_TRACK`, `VK_LEFT/RIGHT`. Все media-key нажатия идут с флагом `KEYEVENTF_EXTENDEDKEY` (иначе Chromium-браузеры фильтруют синтетику). Экспортирует `_send_mouse_event`, `MOUSEEVENTF_MOVE`, `MOUSEEVENTF_MOVE_NOCOALESCE` для `system.keep_awake`. Защита от screensaver'а вынесена в `system/keep_awake.py` — dismiss активного стороннего screensaver'а через SendInput невозможен (другой desktop). | `ctypes.windll.user32.SendInput`. |
| `system/keep_awake.py` | Anti-screensaver: удерживает дисплей активным на время диалога через Win32 `SetThreadExecutionState(ES_CONTINUOUS \| ES_DISPLAY_REQUIRED)` — тот же механизм, что VLC/Chromium при fullscreen-видео. `acquire(hold_seconds, *, reason="")` ставит флаг и (пере)запускает `threading.Timer` на отложенный релиз; повторный вызов идемпотентен и продлевает таймер. `release()` снимает флаг досрочно. При краше флаг убирает ОС автоматически. Импортирует `_send_mouse_event` из `system.media_keys` для nudge'а `LASTINPUTINFO`. Интегрирован в `main.VoicePipeline` и `core.wake_word`. | API: `acquire()`, `release()`, `is_active()`. Константа `KEEP_AWAKE_AFTER_TURN_S` из `config.py`. |
| `system/audio_session_mute.py` | `MuteController` через `pycaw`: per-session mute всех Windows audio sessions, **кроме своей**. COM init per-call (`comtypes.CoInitialize()` — STA, иначе RPC_E_CHANGED_MODE c pycaw). | `pycaw`, `comtypes`. |

### `utils/` — вспомогательное

| Файл | Назначение | Ключевые символы |
|---|---|---|
| `utils/__init__.py` | Пустой. | — |
| `utils/audio_devices.py` | `get_current_devices() → (DeviceInfo|None, DeviceInfo|None)` — текущие Windows-дефолты. CLI `python -m utils.audio_devices` — список всех устройств. | `sounddevice.query_devices`. |
| `utils/errors.py` | Таксономия исключений: `VoiceAIError` (root), `AudioError`, `STTError`, `LLMError`, `TTSError`, `ConfigError`, `CancelledError`. | `Exception` subclasses. |
| `utils/helpers.py` | `save_state_atomic()` — tmp-file → `os.replace` для crash-safe записи JSON-стейта. | `json`, `os.replace`. |
| `utils/generate_ack_phrases.py` | Одноразовая генерация ack-WAV'ов в `assets/ack/` через Silero. Не перезаписывает существующее (`--overwrite` для форсирования). Поддерживает три фазы: `before` (перед диктовкой), `after` (успешное завершение), `fail` (команда не смогла выполниться — играется альтернативная фраза). Таблица `ACK_PHRASES` — источник истины для всех команд и фаз. | `core.silero_tts`. |
| `utils/tts_speakers.py` | CLI `python -m utils.tts_speakers` — список встроенных XTTS-v2 спикеров. | `TTS.api.TTS`. |

### `players/` — медиа-адаптеры

| Файл | Назначение |
|---|---|
| `players/__init__.py` | Заготовка пакета (изначально для VLC/MPC-HC/YouTube адаптеров, в итоге заменено на media-key подход в `system/media_keys.py`). |

### `tests/` — pytest

| Файл | Назначение |
|---|---|
| `tests/__init__.py` | — |
| `tests/test_wake_word.py` | Юнит-тесты `core.wake_word._normalize` / `contains_wake_word` (чистые функции, без мик/модели). |
| `tests/test_reminder_listing.py` | 24 теста на `core.reminders.listing`: склонения счётчика (`_count_phrase`), порядковые числительные (`_ordinal_neuter`), форматирование остатка времени (`format_remaining`) и сборку итоговой фразы (`format_reminders_list`) — включая граничные случаи (0 напоминаний, clamp отрицательного остатка, fallback для 11+). |
| `tests/fixtures/sample.wav` | WAV-фикстура. |

### `assets/` — пререндеры

| Путь | Назначение |
|---|---|
| `assets/ack/*.wav` | Предварительно сгенерированные Silero ack-фразы для каждой команды/фазы: `note_before/after`, `screenshot_after`, `pause_after`, `mute_after/unmute_after`, `volume_up/down_after`, `seek_forward/backward_after`, `stop_after`, `cancel_after`, `question_before`, `resume_after`, `translate_video_after`, `translate_video_fail`. Проигрываются через `AudioPlayer` мгновенно, без повторного синтеза. |
| `assets/yandex_translate_icon.png` | Шаблон кнопки «Перевести и озвучить» Яндекс.Браузера для `pyautogui.locateOnScreen`. Скриншот сделан в полноэкранном режиме YouTube — в оконном режиме фон отличается и шаблон может не совпасть. |

### `models/` — веса Whisper

| Файл | Назначение |
|---|---|
| `models/large-v3-turbo.pt` | Текущая Whisper-модель (по умолчанию в `config.WHISPER_MODEL_SIZE`). Быстрее large-v3 (~2×), WER сравнимый. |
| `models/large-v3.pt` | Запасная Whisper-модель для отката. |

### `logs/` — runtime-артефакты

| Путь | Назначение |
|---|---|
| `logs/voice_ai.log` | Ротируемый лог всех подсистем (5 МБ × 3). |
| `logs/unrecognized.log` | Отдельный журнал фраз, на которые `CommandRouter` не нашёл команду — для сбора синонимов. |
| `logs/tts_out/` | Выходные WAV-файлы TTS (timestamped). |
| `logs/sessions/YYYY-MM-DD_HH-MM/` | Лениво создаваемая папка сессии с заметками (`note_*.txt`) и скриншотами (`screenshot_*.png`). |
