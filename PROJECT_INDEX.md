# PROJECT_INDEX — «Шурочка» (Voice AI Assistant v2)

## О проекте

**Шурочка** — локальный голосовой ассистент для Windows, работающий полностью оффлайн
на GPU-машине пользователя. Задача — принимать голосовые команды (управление плеером,
громкостью, заметки, скриншоты, напоминания, перевод видео, свободные вопросы к LLM)
без облачных сервисов и отправки звука наружу.

### Цели и предназначение
- **Приватность**: все модели (Whisper STT, Silero/XTTS TTS, LLM через Ollama/LM Studio) крутятся локально.
- **Голосовой контроль системы**: медиа-плееры, громкость, mute сторонних аудио-сессий, скриншоты, диктовка заметок, напоминания, перевод видео в Яндекс.Браузере.
- **Q&A через локальный LLM**: только по явным триггерам («ответь на вопрос», «подскажи», «нужна помощь»), чтобы шум Whisper'а не уходил в модель.
- **Дежурный режим**: постоянное прослушивание кодового слова «Шурочка» и активация по нему.

### Функционал и возможности
- Пайплайн `AudioStream → VAD → фильтр речи (Silero VAD) → STT (Whisper | GigaAM) → очистка галлюцинаций → CommandRouter → (Command | LLM) → TTS → AudioPlayer`.
- **Защита от галлюцинаций STT**: `core/speech_gate.py` не пропускает в распознавание фрагменты без речи; `core/transcript_filter.py` отбрасывает сегменты Whisper по `no_speech_prob` / `avg_logprob` / `compression_ratio`, вырезает фразы субтитров («Продолжение следует», «Спасибо за просмотр») и схлопывает повторы. Работает в командах, поиске кодового слова, диктовке и распознавании файлов.
- **Wake-word** активация («Шурочка») с ack-бипом и запасной глобальной hotkey (`Ctrl+Alt+S`).
- **Команды**: `запиши заметку`, `сделай скриншот`, `пауза/продолжи`, `выключи/включи звук`, `громче/тише`, `следующий/предыдущий трек`, `чуть вперёд/назад`, `переведи видео`, `поставь напоминание …`, `перечисли напоминания`, `закончи работу`, `ответь на вопрос …`.
- **Пользовательский overlay команд**: `config/voice_commands.toml` (TOML) умеет расширять/заменять синонимы, выключать команды и править метаданные wake-hint подсказки, не трогая Python-код (`commands/voice_config.py`).
- **Сессии**: заметки и скриншоты складываются в `~/Shura/` (по умолчанию помесячная раскладка `YYYY-MM`, переключается на `per_session` в настройках).
- **UI**: два бэкенда — легаси Tkinter-окно и новый PySide6-дашборд (`--ui pyside6`, фокус текущего редизайна) с уровнемером, health-индикаторами, панелью аудио-устройств + BT-батарея, overlay-статусом и системным треем.
- **IPC**: TCP line-JSON сервер (`127.0.0.1:9999`) с методами `health_check`, `generate_only`, `transcribe_and_respond`, `recalibrate`.
- **Взаимозаменяемые провайдеры**: Whisper или опциональный GigaAM-v3 (STT, `[stt] provider = "gigaam"`), Ollama/LM Studio (LLM), Silero/XTTS (TTS) — все реализуют ABC из `core/base.py`, переключение через настройки.
- **GPU VRAM swap**: если TTS == XTTS на CUDA, Whisper выгружается на время синтеза и перезагружается после — они не помещаются в VRAM одновременно.

### Конфигурация
Все тюнинги — в Pydantic-модели `config_model.Settings` (секции paths/audio/vad/speech_gate/
stt (+ stt.filter, stt.gigaam)/llm/tts/wake_word/commands/ui/…). Пользовательские правки кладутся в `settings.toml` в корне
(шаблон — `settings.toml.example`, в репозиторий не коммитится). `config.py` оставлен как
**shim**: импортирует singleton `settings` и пробрасывает 90 старых module-level констант
(`WHISPER_MODEL_SIZE`, `OLLAMA_TIMEOUT`, …) для 24 модулей-потребителей. Маппинг — в
`docs/config_migration_map.md`.

### Окружение
Python 3.10, Windows 10, CUDA 12.x. Зависимости: `requirements.txt`. LLM-бекенд запускается
отдельно (Ollama на `:11434` или LM Studio на `:1234`).

### Точки входа
- `python main.py` — новый модульный интерфейс `ui/modern/` (по умолчанию).
- `python -m ui.modern --preview` — предпросмотр без микрофона и моделей.
- `python main.py --ui tkinter` — прежний Tkinter UI.
- `python main.py --mode ui --ui pyside6` — новый PySide6-дашборд.
- `python main.py --mode console` — REPL + IPC.
- `python main.py --mode ipc` — headless IPC-сервер (`--no-ipc` подавляет сервер).
- `python -m utils.audio_devices` / `python -m utils.tts_speakers` / `python -m utils.bluetooth_battery` — диагностические CLI.
- `python -m scripts.dump_voice_commands` / `python -m scripts.command_stats` и др. — служебные скрипты (см. раздел `scripts/`).

---

## Структура файлов

### Самостоятельные речевые инструменты

- `core/speech_runtime.py`, `core/dictation.py`: общие ленивые модели и аудиоресурсы, нейтральное распознавание, непрерывная запись с очередью, полный синтез длинного текста и атомарный экспорт.
- `ui/modern/speech_backend.py`, `ui/modern/speech_pages.py`: независимые фоновые операции, страницы STT/TTS и плавающая кнопка. `VoicePipeline` получает общий runtime через необязательный аргумент `speech_runtime`.
- `system/text_injector.py`: Unicode-вставка в активное приложение Windows без буфера обмена и Enter.
- `tests/test_speech_runtime.py`, `tests/test_speech_tools_ui.py`, `tests/test_text_injector.py`: проверки без моделей, микрофона и LLM. `scripts/preview_speech_tools.py` сохраняет снимки интерфейса без запуска ядра.

### Корень проекта

| Файл | Назначение | Ключевые точки входа / выхода |
|---|---|---|
| `main.py` | Главный оркестратор. Класс `VoicePipeline` владеет AudioStream, VAD, STT, LLM, TTS, AudioPlayer, SessionManager, MuteController, CommandRouter, WakeWordListener, ReminderScheduler. Один `threading.Lock` сериализует доступ к микрофону/моделям из REPL, IPC и wake-word listener. Реестр команд строится через `build_configured_registry()` (с учётом TOML-overlay). CLI-парсер: `--mode ui/console/ipc`, `--ui tkinter/pyside6`, `--no-ipc`. | Вход: `main()` / импортирует `VoicePipeline`. Выход: синтезированный WAV в динамики + файлы сессии. |
| `bootstrap.py` | Однократная инициализация для всех entry points: форсит UTF-8 stdout, поднимает `logging_config.setup_logging()`, печатает текущие Windows-дефолты аудио-устройств. | Функция `bootstrap(verbose=True) → BootstrapResult`. |
| `config.py` | **Shim** над `config_model.Settings`: импортирует singleton `settings = load_settings()` и пробрасывает все старые module-level константы по маппингу `docs/config_migration_map.md`. Read-only зеркало — правки значений идут через `settings.toml` или дефолты в `config_model.py`. | Экспортирует ~90 констант. |
| `config_model.py` | Pydantic-модель конфигурации с делением на секции (`PathsSettings`, `STTSettings`, `LLMSettings`, `WakeHintSettings`, …) + `load_settings()` (дефолты + overrides из `settings.toml`) и `save_settings(diff_only=True)` (пишет только отличия от дефолтов). `extra="forbid"` — опечатка в TOML падает на валидации. | `Settings`, `load_settings`, `save_settings`, `SETTINGS_TOML_PATH`. |
| `logging_config.py` | `setup_logging()` — идемпотентный конфиг: ротируемый файловый хендлер (`logs/voice_ai.log`) + консольный; отдельные logger'ы `unrecognized` → `logs/unrecognized.log` и распознанные команды → `logs/recognized.log`. | Функция `setup_logging()`. |
| `requirements-gigaam.txt` | Опциональные зависимости GigaAM-v3 (`hydra-core`, `omegaconf`, `sentencepiece`); пакет `gigaam` намеренно не ставится (требует numpy 2.x). | — |
| `requirements.txt` | pip-зависимости: `openai-whisper`, `silero-vad`, `silero`, `TTS` (Coqui XTTS), `pydantic`, `tomli`/`tomli_w`, `PySide6`, `sounddevice`, `soundfile`, `numpy`, `torch`, `pycaw`, `comtypes`, `mss`, `pillow`, `pystray`, `pynput`, `pyautogui` и пр. | — |
| `settings.toml.example` | Шаблон пользовательских настроек: закомментированные поля по секциям. Копируется в `settings.toml` (не коммитится). | — |
| `CLAUDE.md` | Инструкции для Claude Code по проекту. | — |
| `CHANGELOG.md` | Хронология изменений (Keep-a-Changelog), активная секция `[Unreleased]`. | — |
| `README.md` | GitHub-витрина, обновляется вручную перед push. | — |
| `soft-sniffing-allen.md` | План редизайна UI (этапы 1–8 миграции config + PySide6-дашборд). | — |
| `LLM_report.md` | Сгенерированный отчёт по LLM. | — |
| `claude_start.bat` / `go.bat` / `gitpush.bat` / `ЯMake_llm_report.bat` | Локальные BAT-лаунчеры. | — |
| `install_and_test.bat` | Установка и проверка окружения: CUDA-сборка PyTorch (закрепляется constraints-файлом, чтобы pip её не заменил), `requirements.txt`, опционально GigaAM-v3 (`requirements-gigaam.txt` + torchaudio под версию torch, по желанию — скачивание весов), `scripts/check_environment.py`, `pytest -m "not slow and not gpu"`, по желанию — ручная проверка фильтров с микрофоном. | `install_and_test.bat [--yes] [--no-gigaam] [--no-tests]`. |
| `Полный список голосовых команд.txt`, `новые фичи.txt`, `список пожеланий.txt`, `гитхаб.txt` | Заметки/TODO пользователя. | — |

> **Примечание:** `check_stage_<N>.py` (этапы 5–8, M4/M6/M8) удалены после ручной приёмки — стейджи приняты. Дорожная карта и спецификация переехали в `docs/` (`docs/MIGRATION_PLAN.md`, `docs/VOICE_AI_PROJECT_SPECIFICATION.md`).

### `core/` — подсистемы пайплайна

| Файл | Назначение | Ключевые символы / библиотеки |
|---|---|---|
| `core/__init__.py` | Фабрики провайдеров: `create_stt_provider()`, `create_llm_provider()`, `create_tts_provider()` читают `config` и выбирают нужный класс. | Экспорт: 3 фабрики + ABC из `core.base`. |
| `core/base.py` | ABC для инверсии управления: `STTProvider`, `LLMProvider`, `TTSProvider`. | `abc.ABC`, `abstractmethod`. |
| `core/audio_stream.py` | `AudioStream` — фоновый микрофонный reader на `sounddevice`. Считает per-chunk RMS (int16), держит скользящий `noise_floor`, выдаёт `(rms, percent)` в bounded queue для UI; `chunk_queue` питает VAD. | `sounddevice.InputStream`, `queue.Queue`, `numpy`. |
| `core/vad.py` | `VoiceActivityDetector` — `calibrate()`, `record_until_silence()`. Адаптивный drift порога к шуму. | `numpy`, `wave`. |
| `core/stt.py` | `WhisperSTT` — `load_model()` / `transcribe(path, profile)` / `unload_model()`. Текст чистится `clean_transcript()` по оценкам сегментов Whisper и настройкам `[stt.filter]`. После unload — `gc.collect()` + `torch.cuda.empty_cache()`. | `openai-whisper`, `torch`, `core.transcript_filter`. |
| `core/gigaam_stt.py` | Опциональный `GigaAMSTT(STTProvider)` — GigaAM-v3 через `transformers` (`trust_remote_code`), `[stt.gigaam]`. Звук передаётся из памяти (ffmpeg не нужен), длинный звук режется по паузам `split_audio()` на куски ≤ 22 с. | `transformers`, `torch`, `core.transcript_filter`. |
| `core/speech_gate.py` | `SpeechGate` — Silero VAD перед STT: `filter_file()` → `GateResult` (нет речи → `path=None`; есть — обрезка тишины по краям во временный `*.speech.wav`). Без `silero-vad` пропускает звук. Общий экземпляр `get_speech_gate()`; настройки `[speech_gate]` читаются при каждом вызове. | `silero-vad`, `torch`, `soundfile`. |
| `core/transcript_filter.py` | `clean_transcript()` — очистка текста STT: `filter_segments()` по оценкам Whisper, `deloop()`, `strip_hallucinations()` (сильные фразы субтитров — всегда; слабые «Спасибо», «Пока» — в командах или при сомнении модели). Без зависимостей от моделей. | `re`. |
| `core/llm.py` | `OllamaLLM(LLMProvider)` — авто-детект thinking-моделей (3× токенов), `generate()` чистит результат через `clean_llm_response()`. | `core.ollama_client`, `core.prompt_manager`. |
| `core/llm_errors.py` | Таксономия `LLMErrorKind` для Ollama + LM Studio. `classify_http_error()`. | `enum.Enum`, `requests.exceptions`. |
| `core/ollama_client.py` | HTTP-клиент Ollama: `generate()`, `list_models()`, `is_running()`. Retry с backoff. | `requests`, `core.llm_errors`. |
| `core/lmstudio_client.py` | Backend LM Studio (OpenAI-compatible REST). `LMStudioLLM` симметричен `OllamaLLM`. | `requests`, `core.llm_errors`, `core.prompt_manager`. |
| `core/tts.py` | `XTTSProvider(TTSProvider)` — Coqui XTTS-v2 zero-shot voice clone. | `TTS.api.TTS`, `torch`, `core.tts_utils`. |
| `core/silero_tts.py` | `SileroTTS(TTSProvider)` — русская модель Silero через `torch.hub.load`. CPU-friendly. | `torch`, `torch.hub`, `soundfile`. |
| `core/tts_utils.py` | Хелперы TTS: резолвинг пути к speaker-WAV, генерация уникального имени выходного WAV. | `pathlib.Path`, `datetime`. |
| `core/audio_output.py` | `AudioPlayer` — проигрывание WAV / numpy-массива через `sounddevice`, блокирующе до конца. | `sounddevice.play`, `soundfile.read`. |
| `core/audio_beep.py` | `generate_beep()` — синусоидальный beep с fade-in/out. Для wake-word / dictate-стартера. | `numpy`. |
| `core/wake_word.py` | `WakeWordListener` — daemon-поток: окна по 2–4 сек через Whisper (окна без речи отсекает `SpeechGate`, `[speech_gate] wake_scan`), match против `WAKE_WORD` + алиасов, на срабатывание — beep + ack + callback. `contains_wake_word()`, `_normalize()` — чистые функции, покрыты тестами. | `threading`, `WhisperSTT`, `core.audio_stream`. |
| `core/preprocessing.py` | `compute_rms_file()` — файловый RMS для калибровок (int16 domain). | `numpy`, `soundfile`. |
| `core/prompt_manager.py` | `clean_llm_response()` — снимает `<think>`, harmony-каналы, `Thinking Process:`. `detect_thinking_markers()`. | `re`. |

### `core/reminders/` — подсистема напоминаний (M10)

| Файл | Назначение | Ключевые символы |
|---|---|---|
| `core/reminders/__init__.py` | Публичный фасад: реэкспорт `parse_reminder_tail`, `ReminderScheduler`, `ReminderStorage`. | — |
| `core/reminders/parser.py` | Regex-парсер хвоста «напомни через N минут/часов …». Возвращает `(count, unit, text)`. | `re`, `commands.router.normalize`. |
| `core/reminders/storage.py` | JSON-персистентность напоминаний: атомарная запись tmp → `os.replace`. Поле `fire_at` — POSIX timestamp. | `json`, `pathlib`. |
| `core/reminders/scheduler.py` | `ReminderScheduler` — `threading.Timer` на каждое активное напоминание, `fire_callback(text)` под pipeline-lock'ом. Просроченные при старте проигрываются по возрастанию `fire_at`. `list_active() -> list[dict]`. | `threading.Timer`, `uuid`. |
| `core/reminders/listing.py` | Форматирование списка напоминаний в одну русскую фразу для TTS (склонения, порядковые, остаток времени). Используется `ListRemindersCommand`. | `core.reminders.num_to_words*`. |
| `core/reminders/num_to_words.py` | Фабрика конвертера чисел в слова: `"manual"` или `"num2words"` по `config.NUM_TO_WORDS_BACKEND`. | — |
| `core/reminders/num_to_words_manual.py` | Ручной конвертер 1–999 в русские слова + `plural_form()`. Без зависимостей. | `_number_to_words()`, `plural_form()`. |
| `core/reminders/num_to_words_external.py` | Обёртка над `num2words` для расширенного диапазона. | `num2words`. |

### `commands/` — голосовые команды

| Файл | Назначение | Ключевые символы |
|---|---|---|
| `commands/__init__.py` | Публичный фасад: `BaseCommand`, `CommandType`, `CommandContext`, `TurnStats`, `CommandRouter`, `CommandRegistry`, `build_default_registry()`, `build_configured_registry()`. | Реэкспорт. |
| `commands/base.py` | `BaseCommand` ABC (`name`, `synonyms`, `command_type`, `ack_before`/`ack_after`, `execute(ctx)`). `CommandType` enum: **GLOBAL** (Stop/Cancel, проверяется первым), **INSTANT** (fire-and-forget), **CONTENT** (нужно тело после триггера — Note/Question/Reminder), **COMPOSITE**. `CommandContext` — DTO. `TurnStats` — накопитель метрик хода (STT/LLM/TTS ms, токены) для UI. | `abc.ABC`, `dataclass`, `Enum`. |
| `commands/router.py` | `CommandRouter.match(text)` — нормализация (`normalize()`: lower, `ё→е`, пунктуация, whitespace) + сопоставление по синонимам по убыванию длины. | Чистый текстовый матчер. |
| `commands/registry.py` | `CommandRegistry` (name→instance, инвариант «≥2 слов»). `build_default_registry()` — встроенные команды. `build_configured_registry(config_path, strict, allow_disable_global)` — применяет TOML-overlay через `commands.voice_config`; при невалидном конфиге и `strict=False` откатывается на дефолты. | Iterable protocol. |
| `commands/voice_config.py` | Загрузка/применение пользовательского TOML-overlay (`config/voice_commands.toml`). Pydantic-схемы `VoiceCommandsConfig`/`CommandOverride` (`extra="forbid"`). `apply_voice_commands_config()` — merge синонимов (`extend`/`replace`, инвариант «≥2 слов», запрет дублей внутри и между командами), disable (GLOBAL — только при `allow_disable_global`), инъекция hint-метаданных (`_hint_label`/`_hint_show`/`_hint_order`). Ошибки → `VoiceCommandConfigError`. | `tomllib`/`tomli`, `pydantic`. |
| `commands/hint_provider.py` | Источник списка для wake-hint оверлея. Базис — авто-генерация из `CommandRegistry` (первый синоним каждой команды); перекрывается легаси `config/wake_hints.json` (label/show/order) и затем — приоритетно — метаданными из `voice_commands.toml`. `load_hint_lines()` сортирует по order и обрезает по `max_items`. | `json`, `CommandRegistry`. |
| `commands/note_command.py` | `NoteCommand` — «запиши заметку …» (CONTENT). Fast path (≥N слов после триггера) или dictation. Пишет TXT; при `notes.html_with_screenshot` снимает экран до диктовки и дополняет месячный HTML-журнал. | `CommandType.CONTENT`, `SessionManager`. |
| `commands/screenshot_command.py` | `ScreenshotCommand` — «сделай скриншот» (INSTANT). `system.screenshot.take_screenshot()` + `session_manager.save_screenshot()`. | `CommandType.INSTANT`. |
| `commands/question_command.py` | `QuestionCommand` — единственный легитимный путь к LLM (CONTENT). Триггеры: «ответь на вопрос», «подскажи», «нужна помощь». | `CommandType.CONTENT`. |
| `commands/player_commands.py` | `PauseCommand`, `ResumeCommand` (обе шлют `VK_MEDIA_PLAY_PAUSE` — toggle), `VolumeUpCommand`, `VolumeDownCommand` (мастер-громкость Windows), `MuteCommand`/`UnmuteCommand` (селективный per-session mute через `MuteController`, кроме своей сессии). | `system.media_keys`, pycaw. |
| `commands/stubs.py` | `StopCommand` (GLOBAL — выключает wake listener, не выход из процесса), `SeekForward/BackwardCommand` (`VK_MEDIA_NEXT/PREV_TRACK` — трек/видео), `SkipForward/BackwardCommand` (`arrow_right/left` в активное окно — ±5 сек на YouTube). Cancel — клавишный (Esc в UI), не голосовой. | `system.media_keys`. |
| `commands/reminder_command.py` | `ReminderCommand` — «поставь напоминание …» (CONTENT). ack-WAV `reminder_before` → `pipeline.dictate()` → regex-парсер `core.reminders.parser` → `Scheduler.add()` (абсолютный fire_at в JSON + Timer). При неудаче парсинга — голосовая подсказка, LLM не трогается. | `CommandType.CONTENT`; `core.reminders`. |
| `commands/list_reminders_command.py` | `ListRemindersCommand` — «перечисли напоминания» (INSTANT). Читает активные таймеры из `ReminderScheduler.list_active()`, произносит одну русскую фразу через `core.reminders.listing` без LLM. | `CommandType.INSTANT`. |
| `commands/translate_video_command.py` | `TranslateVideoCommand` — «переведи видео» (INSTANT): кликает по кнопке «Перевести и озвучить» панели Яндекс.Браузера поверх YouTube. Ищет шаблон `assets/yandex_translate_icon.png` через `pyautogui.locateOnScreen`. ack вручную через `pipeline._play_ack()` — отдельные WAV для успеха и неудачи. | `CommandType.INSTANT`; `pyautogui` (lazy). WAV: `translate_video_after.wav`, `translate_video_fail.wav`. |

Голосовая подписка: `commands/subscribe_channel_command.py` — команда
`subscribe_channel` («подпишись на канал», INSTANT). `system/youtube_subscription.py`
проверяет активный Яндекс.Браузер, ищет кнопки на основном мониторе и
проверяет изменение состояния. Шаблоны — `assets/youtube_subscription/`,
ответы — `assets/ack/subscribe_channel_*.wav`. Обслуживание и ограничения:
`docs/subscribe_channel_command.md`; автотесты — `tests/test_subscribe_channel.py`.

### `ipc/` — inter-process API

| Файл | Назначение | Ключевые символы |
|---|---|---|
| `ipc/__init__.py` | Публичный фасад: `VoiceAIServer`, `VoiceAIClient`, `ErrorCode`. | — |
| `ipc/protocol.py` | Фрейминг: один JSON / строку `\n`. `MAX_LINE_BYTES = 1 MiB`. `ErrorCode` enum. | `json`, `enum`. |
| `ipc/schemas.py` | Pydantic-схемы запросов/ответов. Envelope `{id, method, params}` / `{id, status, result|error}`. | `pydantic.BaseModel`. |
| `ipc/server.py` | `VoiceAIServer(ThreadingTCPServer)` — один поток на соединение, обработчики берут `pipeline.lock`. Методы: `health_check`, `generate_only`, `transcribe_and_respond`, `recalibrate`. | `socketserver.ThreadingTCPServer`. |
| `ipc/client.py` | `VoiceAIClient` — blocking sync TCP-клиент, connection-per-call. `IPCError` с `code`. | `socket`. |

### `ui/` — пользовательские интерфейсы

| Файл | Назначение | Ключевые символы |
|---|---|---|
| `ui/__init__.py` | Пустой. | — |
| `ui/tkinter_ui.py` | `VoiceAIApp` — легаси Tkinter-окно (Этап 7). Владеет `VoicePipeline` на worker thread, UI в main thread. Кнопки, уровнемер RMS, health pills, лог-вьюер. `run_ui()` — entry point. | `tkinter`, `tkinter.ttk`, `threading`. |
| `ui/overlay.py` | `Overlay` — полупрозрачный `tk.Toplevel` поверх всех окон (статусы pipeline). Click-through на Windows (ctypes user32). Используется Tkinter-бэкендом. | `tkinter.Toplevel`, `ctypes`. |
| `ui/tray.py` | `SystemTrayIcon` — `pystray`-иконка в трее (daemon thread). | `pystray`, `PIL.Image`. |
| `ui/hotkey.py` | `HotkeyListener` — глобальная hotkey (`WAKE_HOTKEY`, Ctrl+Alt+S) через `pynput.keyboard.GlobalHotKeys`; включает wake-listener обратно. | `pynput.keyboard`. |

### `ui/modern/` — новый модульный интерфейс (по умолчанию)

| Файл | Назначение |
|---|---|
| `app.py`, `__main__.py` | Запуск нового интерфейса и предпросмотр без ядра. |
| `window.py` | Оболочка, навигация и расширяемый реестр `PageSpec`. |
| `pages.py` | Обзор, история с поиском/экспортом, каталог команд, настройки (включая карточку «Распознавание речи»: выбор Whisper/GigaAM, переключатели фильтра речи и очистки галлюцинаций). |
| `components.py`, `theme.py` | Переиспользуемые компоненты, индикаторы, палитра и QSS. |
| `backend.py` | Фоновая интеграция с `VoicePipeline`, IPC и wake-word; Qt-сигналы для страниц. |
| `docs/modern_ui.md` | Архитектура, запуск и пример добавления страницы. |
| `tests/test_modern_ui.py` | Автоматические проверки UI без микрофона, GPU и LLM. |

### `ui/pyside6/` — прежний дашборд

| Файл | Назначение | Ключевые символы |
|---|---|---|
| `ui/pyside6/__init__.py` | Пакет PySide6-UI. | — |
| `ui/pyside6/app.py` | `run_ui_pyside6()` — создаёт `QApplication`, грузит QSS, поднимает `PipelineBridge`, показывает `DashboardWindow`, запускает Qt event loop. | `PySide6.QtWidgets.QApplication`. |
| `ui/pyside6/bridge.py` | `PipelineBridge(QObject)` — мост между `main.VoicePipeline` и Qt-UI. UI зовёт слоты (`start_pipeline`, `request_turn`, `request_recalibrate`, `request_set_model`, `request_toggle_standby`, `request_cancel`, `shutdown`), бридж эмитит сигналы (`state_changed`, `turn_result`, `level_update`, `health_update`, `models_list`, …). Тяжёлая работа — в выделенном `QThread`; уровень/health — на `QTimer`. | `QObject`, `QThread`, `QTimer`, `Signal`, `Slot`. |
| `ui/pyside6/dashboard.py` | `DashboardWindow(QMainWindow)` — двухколоночный layout 960×640: слева оперативная панель (статус, LevelMeter, последний оборот, тайминги, выбор LLM-модели, 4 кнопки), справа `DevicesPanel`; внизу status bar с тремя точками STT/LLM/TTS. Кнопка ⚙ — заглушка Settings. | `QMainWindow`, виджеты. |
| `ui/pyside6/styles/solarized.qss` | Qt-стили (тема Solarized) для дашборда. | QSS. |
| `ui/pyside6/widgets/__init__.py` | Пакет виджетов. | — |
| `ui/pyside6/widgets/devices_panel.py` | `DevicesPanel` — текущие аудио-устройства Windows (`utils.audio_devices`) + заряд BT (`utils.bluetooth_battery`, поллинг в фоновом `QThread`). Только отображение. | `QThread`, `QTimer`. |
| `ui/pyside6/widgets/level_meter.py` | `LevelMeter` — RMS-индикатор на `QPainter` с маркерами шума и порога VAD; подписан на `level_update`. | `QPainter`, `QPen`. |
| `ui/pyside6/widgets/status_indicator.py` | `StatusIndicator` — иконка + текст статуса pipeline. `STATE_LABELS` — единый источник правды по именам состояний (совпадают с `VoicePipeline.on_stage` / `WakeWordListener.on_state`). | `QLabel`. |
| `ui/pyside6/widgets/screenshot_flash.py` | `ScreenshotFlashOverlay` — frameless on-top click-through копия кадра после скриншота: hold + zoom-in fade-out, затем `deleteLater`. Крепится к `primaryScreen()`. | `QPropertyAnimation`, `QPixmap`. |
| `ui/pyside6/widgets/wake_hint_overlay.py` | `WakeHintOverlay` — полноэкранный полупрозрачный список команд при пробуждении (источник — `commands.hint_provider`). Frameless / on-top / click-through; один переиспользуемый экземпляр (`show_lines()`/`hide_now()`). | `QGraphicsDropShadowEffect`, `QPropertyAnimation`. |

### `system/` — интеграция с Windows

| Файл | Назначение | Ключевые символы |
|---|---|---|
| `system/__init__.py` | Package placeholder. | — |
| `system/session_manager.py` | `SessionManager` — папка сессии в `~/Shura/` (помесячная `YYYY-MM` или `per_session` по `SESSION_LAYOUT`). Потокобезопасен. `save_note(text)`, `save_screenshot(png_bytes)`, `save_note_with_screenshot(text, png_data)` возвращает пути и предупреждения. HTML-журнал всегда помесячный. | `pathlib`, `threading`, `system.note_journal`. |
| `system/screenshot.py` | `take_screenshot(monitor=None) → png_bytes` через `mss`. По умолчанию — основной монитор. | `mss`, `PIL.Image`. |
| `system/note_journal.py` | Месячный офлайн HTML-журнал заметок: миниатюры, просмотр оригинала и атомарное добавление записей. Включается через `notes.html_with_screenshot` в Modern UI. | `PIL.Image`, `utils.file_io`. |
| `system/media_keys.py` | Враппер над Win32 `SendInput`: `play_pause()`, `volume_up/down()`, `next_track()`/`prev_track()`, `arrow_left/right()`. Media-key нажатия с `KEYEVENTF_EXTENDEDKEY` (иначе Chromium фильтрует синтетику). Экспортирует `_send_mouse_event`, `MOUSEEVENTF_*` для `system.keep_awake`. | `ctypes.windll.user32.SendInput`. |
| `system/keep_awake.py` | Anti-screensaver: `SetThreadExecutionState(ES_CONTINUOUS \| ES_DISPLAY_REQUIRED)` на время диалога. `acquire(hold_seconds, *, reason="")` + `threading.Timer` на отложенный релиз, `release()`. Интегрирован в `VoicePipeline` и `core.wake_word`. | `acquire()`, `release()`, `is_active()`. |
| `system/audio_session_mute.py` | `MuteController` через `pycaw`: per-session mute всех Windows audio sessions, **кроме своей**. COM init per-call (`comtypes.CoInitialize()` — STA). | `pycaw`, `comtypes`. |

### `utils/` — вспомогательное

| Файл | Назначение | Ключевые символы |
|---|---|---|
| `utils/__init__.py` | Пустой. | — |
| `utils/file_io.py` | Атомарная запись байтов через уникальный временный файл на том же диске; используется для настроек и HTML-журнала. | `tempfile`, `os.fsync`, `Path.replace`. |
| `utils/audio_devices.py` | `get_current_devices() → (DeviceInfo|None, DeviceInfo|None)` — текущие Windows-дефолты. CLI `python -m utils.audio_devices`. | `sounddevice.query_devices`. |
| `utils/bluetooth_battery.py` | Чтение заряда BT-устройств через PowerShell PnP-property (DEVPKEY `{104EA319…} 2`, как «Параметры → Bluetooth»). Эвристика `bt_matches_audio` фильтрует только аудио-периферию. Без сторонних зависимостей. CLI `python -m utils.bluetooth_battery`. | `subprocess`, PowerShell `Get-PnpDevice*`. |
| `utils/errors.py` | Таксономия исключений: `VoiceAIError` (root), `AudioError`, `STTError`, `LLMError`, `TTSError`, `ConfigError`, `CancelledError`. | `Exception` subclasses. |
| `utils/helpers.py` | `save_state_atomic()` — tmp-file → `os.replace` для crash-safe записи JSON. | `json`, `os.replace`. |
| `utils/startup_timing.py` | Отдельный JSONL-журнал длительности запуска; прогноз индикатора по последним пяти успешным загрузкам (первоначально 25 с). | `StartupTimings`, `logs/model_startup.jsonl`. |
| `utils/generate_ack_phrases.py` | Одноразовая генерация ack-WAV'ов в `assets/ack/` через Silero. Таблица `ACK_PHRASES` — источник истины (фазы `before`/`after`/`fail`). | `core.silero_tts`. |
| `utils/tts_speakers.py` | CLI `python -m utils.tts_speakers` — список встроенных XTTS-v2 спикеров. | `TTS.api.TTS`. |

### `scripts/` — служебные скрипты

| Файл | Назначение | Запуск |
|---|---|---|
| `scripts/check_environment.py` | Проверка окружения: версия Python, ключевые пакеты, numpy 1.x, CUDA-сборка PyTorch против устройств из `settings.toml`, Silero VAD на настоящей модели (шум отсекается, ваша запись речи `logs/stage9/take1_raw.wav` проходит). Код выхода 1 при ошибках. | `python scripts/check_environment.py [--gigaam]`. |
| `scripts/command_stats.py` | Статистика использования команд из `logs/recognized.log` (по команде/синониму, с фильтром по дате). | `python -m scripts.command_stats [--by synonym] [--since DATE]`. |
| `scripts/dump_commands_snapshot.py` | Сериализация `CommandRegistry` (name, synonyms, command_type) в `tests/fixtures/commands_snapshot.json` — baseline для `test_commands_registry.py`. | `python scripts/dump_commands_snapshot.py`. |
| `scripts/dump_config_snapshot.py` | Сериализация всех констант `config.py` в `tests/fixtures/config_snapshot_baseline.json` — baseline для `test_config_contract.py` (Path сериализуются относительно корня). | `python scripts/dump_config_snapshot.py`. |
| `scripts/dump_voice_commands.py` | Печать эффективного реестра команд **после** применения TOML-overlay (`build_configured_registry()`). | `python -m scripts.dump_voice_commands`. |
| `scripts/validate_voice_commands_config.py` | Валидация `config/voice_commands.toml` без запуска ассистента. | `python -m scripts.validate_voice_commands_config`. |
| `scripts/screenshot_dashboard.py` | PNG-скриншот `DashboardWindow` через offscreen Qt + заглушечный bridge (без загрузки Whisper/TTS). | `python scripts/screenshot_dashboard.py`. |

### `config/` — пользовательские конфиги (overlay)

| Файл | Назначение |
|---|---|
| `config/voice_commands.example.toml` | Шаблон TOML-overlay команд (`enabled`/`mode`/`synonyms`/`hint`/`show_in_hints`/`order`). Копируется в `config/voice_commands.toml`. Загружается `commands/voice_config.py`. |
| `config/wake_hints.example.json` | Легаси-список для полноэкранной шпаргалки (`command`/`label`/`show`/`order`). Копируется в `config/wake_hints.json`. Перекрывается метаданными `voice_commands.toml`. Загружается `commands/hint_provider.py`. |
| `config/voice_commands.toml`, `config/wake_hints.json` | Реальные пользовательские файлы (не коммитятся). |

### `tests/` — pytest

| Файл | Назначение |
|---|---|
| `tests/__init__.py` | — |
| `tests/conftest.py` | Общие фикстуры/хуки: моки провайдеров STT/LLM/TTS и зависимостей `VoicePipeline` (AudioStream, AudioPlayer, VAD, менеджеры). Используются `test_pipeline_smoke.py`. Autouse-фикстура `disabled_speech_gate` выключает общий Silero VAD, чтобы тесты не грузили модель. |
| `tests/test_speech_filters.py` | `SpeechGate` с поддельным детектором (тишина, короткий звук, обрезка, ресемплинг, отказоустойчивость), очистка текста, оценки сегментов Whisper, интеграция с `SpeechRuntime`, поиском кодового слова и `VoicePipeline`, настройки. |
| `tests/test_gigaam_stt.py` | `GigaAMSTT` на поддельных `torch`/`transformers`: загрузка с `revision`, обход ffmpeg, нарезка длинного звука, фильтр, ошибки зависимостей и CUDA. |
| `tests/test_wake_word.py` | Юнит-тесты `core.wake_word._normalize` / `contains_wake_word`. |
| `tests/test_reminder_listing.py` | Тесты `core.reminders.listing`: склонения, порядковые, остаток времени, сборка фразы. |
| `tests/test_commands_registry.py` | Контракт `CommandRegistry` против snapshot'а + инвариант «≥2 слов». |
| `tests/test_voice_commands_config.py` | Тесты TOML-overlay (`commands.voice_config`): merge синонимов, disable, валидация, hint-метаданные. |
| `tests/test_config_contract.py` | Контракт `config.py` против baseline-snapshot (имена/значения/типы констант не меняются при shim-рефакторинге). |
| `tests/test_config_importers.py` | Smoke-импорты всех модулей-потребителей `config` (защита от поломки shim'а). |
| `tests/test_pipeline_smoke.py` | Smoke-инициализация `VoicePipeline` с полностью подменёнными зависимостями; проверка имён `on_stage`. |
| `tests/test_bluetooth_matcher.py` | Тесты эвристики `bt_matches_audio` (`utils.bluetooth_battery`). |
| `tests/fixtures/commands_snapshot.json` | Baseline-снапшот команд для `test_commands_registry.py`. |
| `tests/fixtures/config_snapshot_baseline.json` | Baseline-снапшот констант config для `test_config_contract.py`. |
| `tests/fixtures/sample.wav` | WAV-фикстура (также дефолтный XTTS speaker). |

### `assets/` — пререндеры

| Путь | Назначение |
|---|---|
| `assets/ack/*.wav` | Pre-rendered Silero ack-фразы по командам/фазам: `note_before/after`, `screenshot_after`, `pause_after`, `resume_after`, `mute/unmute_after`, `volume_up/down_after`, `seek_forward/backward_after`, `stop_after`, `cancel_after`, `question_before`, `reminder_before`, `translate_video_after/fail`. Проигрываются через `AudioPlayer` мгновенно. |
| `assets/yandex_translate_icon.png` | Шаблон кнопки «Перевести и озвучить» Яндекс.Браузера для `pyautogui.locateOnScreen` (скриншот в полноэкранном YouTube). |

### `docs/` — документация и тикеты

| Путь | Назначение |
|---|---|
| `docs/MIGRATION_PLAN.md` | Дорожная карта стейджей M1–M8 (команды, wake-word, overlay). Это план, не журнал. |
| `docs/VOICE_AI_PROJECT_SPECIFICATION.md` | Исходная спецификация этапов 0–8. |
| `docs/config_migration_map.md` | Маппинг старых констант `config.py` → секции `config_model.Settings` (база для shim'а и тестов контракта). |
| `docs/voice_commands_config_discussion.md` | Обсуждение дизайна TOML-overlay голосовых команд. |
| `docs/translate_video_command.md` | Заметка по команде перевода видео. |
| `docs/wake_hint_overlay.md` | Заметка по wake-hint оверлею. |
| `docs/tickets/pause_single_youtube_video.md` | Тикет по паузе одиночного YouTube-видео. |
| `docs/dashboard_preview.png` | Превью PySide6-дашборда. |

### `players/` — медиа-адаптеры

| Файл | Назначение |
|---|---|
| `players/__init__.py` | Заготовка пакета (заменено на media-key подход в `system/media_keys.py`). |

### `models/` — веса Whisper

| Файл | Назначение |
|---|---|
| `models/large-v3-turbo.pt` | Текущая Whisper-модель (по умолчанию). Быстрее large-v3 (~2×), WER сравнимый. |
| `models/large-v3.pt` | Запасная Whisper-модель для отката. |

### `logs/` — runtime-артефакты

| Путь | Назначение |
|---|---|
| `logs/voice_ai.log` | Ротируемый лог всех подсистем. |
| `logs/unrecognized.log` | Фразы, на которые `CommandRouter` не нашёл команду — для сбора синонимов. |
| `logs/recognized.log` | Журнал распознанных команд (`<ts>\t<command>\t<synonym>\t<full_text>`) — источник для `scripts/command_stats.py`. |
| `logs/tts_out/` | Выходные WAV-файлы TTS (timestamped). |
| `logs/reminders.json` | Персистентность активных напоминаний. |
</content>
