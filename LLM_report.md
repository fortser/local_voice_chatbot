# СИСТЕМНЫЙ ПРОМПТ: Эксперт-ассистент по Python кодовой базе

## РОЛЬ И ИДЕНТИЧНОСТЬ

Ты — эксперт по архитектуре программного обеспечения и анализу кода на Python. Ты обладаешь глубокими знаниями в следующих областях:
- Современный Python (3.8+) и его особенности
- Type hints и статическая типизация (PEP 484, PEP 585)
- Паттерны проектирования и архитектурные принципы (SOLID, DRY, KISS)
- Асинхронное программирование (asyncio, async/await)
- Популярные фреймворки (Django, FastAPI, Flask, SQLAlchemy, Pydantic)
- Инструменты экосистемы (pip, poetry, pytest, mypy, ruff)

Твоя задача — помогать пользователю понимать, анализировать, модифицировать и улучшать его Python кодовую базу.

---

## ФОРМАТ КОНТЕКСТА

Пользователь предоставит тебе отчёты о проекте в следующем формате:

### overview.md
Общая сводка проекта: количество файлов, пакеты, ключевые классы, точки входа, зависимости.

### files.md
Карта файлов, показывающая:
- Имена файлов и количество строк
- Импорты и кто импортирует файл
- Классы и функции в каждом файле
- Наличие `if __name__ == "__main__"`

### classes.md
Карта классов, показывающая:
- Имена классов и их расположение
- Иерархию наследования
- Декораторы (@dataclass, @property и т.д.)
- Методы с указанием async/staticmethod/classmethod
- Type hints в сигнатурах

### functions.md
Функции уровня модуля с сигнатурами и декораторами.

### packages.md
Структура пакетов Python:
- Иерархия пакетов и подпакетов
- Публичный API (__all__)
- Документация пакетов

### reference.md
Краткий справочник с группировкой по назначению.

### project_config.md
Конфигурация из pyproject.toml/setup.py: зависимости, версия Python, точки входа.

---

## ПРОТОКОЛ РАБОТЫ

### При получении отчётов:
1. Подтверди получение и резюмируй структуру проекта
2. Определи архитектурный стиль (монолит, микросервисы, библиотека)
3. Отметь используемые паттерны и фреймворки
4. Сообщи о готовности помочь

### При запросах пользователя:
1. Пойми цель запроса
2. Оцени, достаточно ли информации из отчётов
3. Запроси конкретные файлы если нужно

---

## ПРОТОКОЛ ЗАПРОСА ФАЙЛОВ

📁 ЗАПРОС ФАЙЛОВ

Для [выполнения задачи] мне необходимо изучить:
Приоритет 	Файл 	Причина
🔴 Критично 	package/module.py 	[Причина]
🟡 Желательно 	package/utils.py 	[Причина]


---

## PYTHON-СПЕЦИФИЧНЫЕ ЗНАНИЯ

При анализе учитывай:

**Структура проекта:**
- src-layout vs flat-layout
- Относительные vs абсолютные импорты
- `__init__.py` и публичный API

**Type hints:**
- Аннотации в сигнатурах
- Generic типы и TypeVar
- Protocol и structural subtyping

**Асинхронность:**
- async/await паттерны
- Корутины и таски
- Асинхронные контекстные менеджеры

**Тестирование:**
- pytest fixtures
- Моки и патчи
- Параметризация тестов

---

## СТИЛЬ КОММУНИКАЦИИ

1. Используй точные имена модулей, классов и функций из отчётов
2. Структурируй ответы с заголовками
3. Учитывай PEP 8 и идиоматичный Python
4. Предлагай современные решения (3.10+ синтаксис где уместно)


============================================================

# PROJECT REPORTS

# Project: .
Source: Python: 93 py | 14,079 lines | 548 KB
Language: PYTHON

## Packages
commands/ — 9 modules, 0 subpackages
core/ — 16 modules, 1 subpackages
core.reminders/ — 6 modules, 0 subpackages
ipc/ — 4 modules, 0 subpackages
players/ — 0 modules, 0 subpackages
system/ — 4 modules, 0 subpackages
tests/ — 7 modules, 0 subpackages
ui/ — 4 modules, 1 subpackages
ui.pyside6/ — 3 modules, 1 subpackages
ui.pyside6.widgets/ — 4 modules, 0 subpackages
utils/ — 6 modules, 0 subpackages

## Key Classes
VoiceAIApp (ui/tkinter_ui.py)
VoicePipeline (main.py)
AudioStream (core/audio_stream.py)
DashboardWindow : QMainWindow (ui/pyside6/dashboard.py)
PipelineBridge : QObject (ui/pyside6/bridge.py)
LMStudioLLM : LLMProvider (core/lmstudio_client.py)
OllamaLLM : LLMProvider (core/llm.py)
WakeWordListener (core/wake_word.py)
_Worker : QThread (ui/pyside6/bridge.py)
MuteController (system/audio_session_mute.py)

## Entry Points
- check_stage_10.py
- check_stage_5.py
- check_stage_6.py
- check_stage_7.py
- check_stage_8.py
- check_stage_9.py
- check_stage_config_refactor.py
- check_stage_dashboard.py
- check_stage_m4.py
- check_stage_m6.py
- check_stage_m8.py
- main.py
- scripts/dump_commands_snapshot.py
- scripts/dump_config_snapshot.py
- scripts/screenshot_dashboard.py
- utils/audio_devices.py
- utils/bluetooth_battery.py
- utils/generate_ack_phrases.py
- utils/tts_speakers.py

## Dependencies
- Pillow
- PySide6
- comtypes
- coqui-tts
- deepfilternet
- httpx
- librosa
- mss
- num2words
- numpy
- openai-whisper
- pyaudio
- pycaw
- pydantic
- pydantic-settings
- ...and 11 more


---

# File Map

## (root)/
**bootstrap.py** (65 lines)
  classes: BootstrapResult
  functions: _force_utf8_stdout, bootstrap
  imports: __future__, dataclasses, logging_config, utils.audio_devices
  imported_by: check_stage_10.py, check_stage_6.py, check_stage_9.py, check_stage_m4.py, check_stage_m6.py

**check_stage_10.py** (290 lines) [has main]
  functions: _banner, _test_parser, _test_num_to_words, _run_pipeline, _test_schedule_now +4
  imports: __future__, time, pathlib, bootstrap

**check_stage_5.py** (91 lines) [has main]
  functions: main
  imports: __future__, main

**check_stage_6.py** (272 lines) [has main]
  functions: _banner, _pass, _fail, _test_health, _test_generate_only +4
  imports: __future__, time, traceback, pathlib, bootstrap

**check_stage_7.py** (121 lines) [has main]
  functions: main
  imports: __future__, traceback

**check_stage_8.py** (114 lines) [has main]
  functions: main
  imports: __future__, traceback

**check_stage_9.py** (167 lines) [has main]
  functions: _banner, _one_pass, main
  imports: __future__, time, pathlib, bootstrap, config

**check_stage_config_refactor.py** (155 lines) [has main]
  functions: _decode_value, step1_random_constants, step2_toml_override, step3_empty_diff_when_clean, main
  imports: __future__, random, tempfile, pathlib

**check_stage_dashboard.py** (318 lines) [has main]
  functions: step1_imports, step2_bridge_methods, step3_bridge_signals, _make_app_and_bridge, step4_dashboard_builds +5
  imports: __future__, pathlib

**check_stage_m4.py** (137 lines) [has main]
  functions: main
  imports: __future__, logging, time, bootstrap

**check_stage_m6.py** (110 lines) [has main]
  functions: main
  imports: __future__, logging, bootstrap

**check_stage_m8.py** (120 lines) [has main]
  functions: main
  imports: __future__, logging, bootstrap

**config.py** (151 lines)
  imports: __future__, config_model
  imported_by: check_stage_6.py, check_stage_9.py, logging_config.py, main.py, commands/note_command.py

**config_model.py** (396 lines)
  classes: _Section, PathsSettings, AudioSettings, VADSettings, DeepFilterSettings, STTSettings, OllamaSettings, LMStudioSettings, LLMSettings, SileroSettings, XTTSSettings, TTSSettings, WakeWordSettings, CommandSettings, DictateSettings, ScreenshotFlashSettings, UISettings, RemindersSettings, IPCSettings, LoggingSettings, Settings
  functions: _deep_merge, load_settings, _diff_dict, _to_toml_primitive, save_settings
  imports: __future__, pathlib, pydantic, tomllib, tomli
  imported_by: config.py

**logging_config.py** (76 lines)
  functions: setup_logging
  imports: logging, logging.handlers, config
  imported_by: bootstrap.py, main.py

**main.py** (1101 lines) [has main]
  classes: TurnResult, VoicePipeline
  functions: _tts_requires_gpu_swap, _start_ipc_server, run_console_mode, run_ipc_mode, main
  imports: __future__, argparse, logging, threading, time
  imported_by: check_stage_5.py, check_stage_6.py, ipc/server.py

## commands/
**__init__.py** (29 lines) [package init]
  imports: commands.base, commands.registry, commands.router
  imported_by: main.py

**base.py** (120 lines)
  classes: TurnStats, CommandType, CommandContext, BaseCommand
  imports: __future__, abc, dataclasses, enum
  imported_by: commands/note_command.py, commands/player_commands.py, commands/question_command.py, commands/registry.py, commands/reminder_command.py

**note_command.py** (114 lines)
  classes: NoteCommand
  functions: _extract_tail
  imports: __future__, logging, commands.base, commands.router, config
  imported_by: commands/question_command.py

**player_commands.py** (112 lines)
  classes: PauseCommand, ResumeCommand, VolumeUpCommand, VolumeDownCommand, MuteCommand, UnmuteCommand
  imports: __future__, logging, commands.base

**question_command.py** (81 lines)
  classes: QuestionCommand
  imports: __future__, logging, commands.base, commands.note_command, config

**registry.py** (105 lines)
  classes: CommandRegistry
  functions: build_default_registry
  imports: __future__, logging, commands.base
  imported_by: commands/router.py, commands/__init__.py, scripts/dump_commands_snapshot.py, tests/test_commands_registry.py

**reminder_command.py** (96 lines)
  classes: ReminderCommand
  imports: __future__, logging, commands.base, core.reminders.num_to_words, core.reminders.parser

**router.py** (147 lines)
  classes: CommandRouter
  functions: normalize, _strip_wake_word
  imports: __future__, logging, commands.base, commands.registry
  imported_by: commands/note_command.py, commands/__init__.py, core/reminders/parser.py

**screenshot_command.py** (52 lines)
  classes: ScreenshotCommand
  imports: __future__, logging, commands.base

**stubs.py** (75 lines)
  classes: StopCommand, SeekForwardCommand, SeekBackwardCommand
  imports: __future__, logging, commands.base

## core/
**__init__.py** (119 lines) [package init]
  functions: _make_whisper, _make_ollama, _make_lmstudio, _make_xtts, _make_silero +3
  imports: __future__, config, core.base, utils.errors
  imported_by: main.py

**audio_beep.py** (38 lines)
  functions: generate_beep
  imports: __future__, numpy
  imported_by: main.py, core/wake_word.py

**audio_output.py** (107 lines)
  classes: AudioPlayer
  imports: __future__, logging, threading, time, pathlib
  imported_by: main.py

**audio_stream.py** (247 lines)
  classes: AudioStream
  functions: _rms_to_percent, _compute_rms_int16
  imports: __future__, logging, queue, threading, collections
  imported_by: check_stage_9.py, main.py, core/vad.py

**base.py** (55 lines)
  classes: STTProvider, LLMProvider, TTSProvider
  imports: __future__, abc
  imported_by: core/llm.py, core/lmstudio_client.py, core/silero_tts.py, core/stt.py, core/tts.py

**llm.py** (160 lines)
  classes: OllamaLLM
  functions: is_thinking_model
  imports: __future__, logging, config, core.base, core.ollama_client

**llm_errors.py** (98 lines)
  classes: LLMErrorKind
  functions: classify_http_error, format_llm_error_message
  imports: __future__, enum, httpx
  imported_by: core/lmstudio_client.py, core/ollama_client.py

**lmstudio_client.py** (365 lines)
  classes: GenerateResult, LMStudioClient, LMStudioLLM
  functions: _is_thinking_model
  imports: __future__, logging, time, dataclasses, httpx

**ollama_client.py** (181 lines)
  classes: GenerateResult, OllamaClient
  imports: __future__, logging, time, dataclasses, httpx
  imported_by: core/llm.py

**preprocessing.py** (259 lines)
  functions: compute_rms, normalize_audio, resample_audio, _get_deepfilter, preload_deepfilter +1
  imports: __future__, logging, threading, pathlib, numpy
  imported_by: check_stage_9.py, main.py

**prompt_manager.py** (129 lines)
  functions: strip_think_tags, strip_thinking_chains, detect_thinking_markers, clean_llm_response
  imports: __future__
  imported_by: main.py, core/llm.py, core/lmstudio_client.py

**silero_tts.py** (351 lines)
  classes: SileroTTS
  functions: _truncate_at_sentence, _sanitize_for_silero, _transliterate_word, _transliterate_latin
  imports: __future__, gc, logging, time, pathlib
  imported_by: utils/generate_ack_phrases.py

**stt.py** (232 lines)
  classes: WhisperSTT
  functions: _is_hallucination, _vram_snapshot, _load_audio_float32
  imports: __future__, gc, logging, time, pathlib
  imported_by: check_stage_9.py

**tts.py** (188 lines)
  classes: XTSTTTS
  functions: _vram_snapshot
  imports: __future__, gc, logging, time, pathlib

**tts_utils.py** (69 lines)
  functions: resolve_speaker_wav, prepare_output_dir, make_output_path
  imports: __future__, itertools, logging, time, pathlib
  imported_by: core/silero_tts.py, core/tts.py

**vad.py** (317 lines)
  classes: VoiceActivityDetector
  functions: _trim_trailing_silence
  imports: __future__, logging, queue, tempfile, threading
  imported_by: check_stage_9.py, main.py

**wake_word.py** (305 lines)
  classes: WakeWordListener
  functions: _normalize, contains_wake_word
  imports: __future__, logging, threading, time, config
  imported_by: tests/test_wake_word.py

## core/reminders/
**__init__.py** (15 lines) [package init]
  imports: core.reminders.parser, core.reminders.scheduler, core.reminders.storage
  imported_by: main.py

**num_to_words.py** (35 lines)
  functions: humanize_duration
  imports: __future__, logging, config
  imported_by: commands/reminder_command.py

**num_to_words_external.py** (43 lines)
  functions: humanize_duration
  imports: __future__, core.reminders.num_to_words_manual, num2words

**num_to_words_manual.py** (80 lines)
  functions: _number_to_words, plural_form, humanize_duration
  imports: __future__
  imported_by: core/reminders/num_to_words_external.py

**parser.py** (83 lines)
  functions: parse_reminder_tail, unit_to_seconds
  imports: __future__, commands.router
  imported_by: commands/reminder_command.py, core/reminders/__init__.py

**scheduler.py** (125 lines)
  classes: ReminderScheduler
  imports: __future__, logging, threading, time, uuid
  imported_by: core/reminders/__init__.py

**storage.py** (80 lines)
  classes: ReminderStorage
  imports: __future__, logging, threading, pathlib
  imported_by: core/reminders/scheduler.py, core/reminders/__init__.py

## ipc/
**__init__.py** (13 lines) [package init]
  imports: ipc.client, ipc.protocol, ipc.server
  imported_by: check_stage_6.py

**client.py** (118 lines)
  classes: IPCRemoteError, VoiceAIClient
  imports: __future__, logging, socket, uuid, config
  imported_by: check_stage_6.py, ipc/__init__.py

**protocol.py** (110 lines)
  classes: ErrorCode, ProtocolError
  functions: send_line, recv_line
  imports: __future__, socket, enum
  imported_by: ipc/client.py, ipc/schemas.py, ipc/server.py, ipc/__init__.py

**schemas.py** (124 lines)
  classes: RequestEnvelope, ErrorBody, ResponseEnvelope, HealthCheckParams, GenerateOnlyParams, TranscribeAndRespondParams, RecalibrateParams, HealthCheckResult, GenerateOnlyResult, TranscribeAndRespondResult, RecalibrateResult
  imports: __future__, pydantic, ipc.protocol
  imported_by: ipc/server.py

**server.py** (302 lines)
  classes: _RequestHandler, _Server, VoiceAIServer
  functions: _classify, _handle_health_check, _handle_generate_only, _handle_transcribe_and_respond, _handle_recalibrate
  imports: __future__, logging, socket, socketserver, threading
  imported_by: ipc/__init__.py

## players/
**__init__.py** (6 lines) [package init]

## scripts/
**dump_commands_snapshot.py** (51 lines) [has main]
  functions: main
  imports: __future__, pathlib, commands.registry

**dump_config_snapshot.py** (78 lines) [has main]
  functions: _encode, collect_constants, main
  imports: __future__, pathlib, config

**screenshot_dashboard.py** (108 lines) [has main]
  classes: _FakeTurn
  functions: main
  imports: __future__, dataclasses, pathlib, PySide6.QtGui, PySide6.QtWidgets

## system/
**__init__.py** (6 lines) [package init]
  imported_by: commands/player_commands.py, commands/stubs.py

**audio_session_mute.py** (202 lines)
  classes: MuteController
  imports: __future__, logging, threading
  imported_by: main.py

**media_keys.py** (168 lines)
  classes: _KEYBDINPUT, _MOUSEINPUT, _HARDWAREINPUT, _INPUT_UNION, _INPUT
  functions: _send_key_event, _press_key, play_pause, next_track, prev_track +2
  imports: __future__, ctypes, logging, time

**screenshot.py** (57 lines)
  functions: take_screenshot
  imports: __future__, logging, mss, mss.tools
  imported_by: commands/screenshot_command.py

**session_manager.py** (117 lines)
  classes: SessionManager
  imports: __future__, logging, threading, datetime, pathlib
  imported_by: main.py

## tests/
**__init__.py** (1 lines) [package init]

**conftest.py** (87 lines)
  functions: mock_providers, mock_audio
  imports: __future__, pathlib, unittest.mock, pytest

**test_bluetooth_matcher.py** (58 lines)
  functions: test_wh1000xm4_matches_when_active_output, test_airpods_pro_matches, test_jbl_speaker_matches, test_bt_keyboard_does_not_match_typical_audio, test_xiaomi_sensor_does_not_match +3
  imports: __future__, utils.bluetooth_battery

**test_commands_registry.py** (75 lines)
  functions: _load_snapshot, test_default_registry_matches_snapshot, test_all_synonyms_two_words_or_more, test_registry_rejects_one_word_synonym
  imports: __future__, pathlib, pytest, commands.registry

**test_config_contract.py** (90 lines)
  functions: _load_snapshot, _decode_path, _decode_value, test_all_known_constants_present, test_no_unexpected_removals +2
  imports: __future__, pathlib, pytest, config

**test_config_importers.py** (67 lines)
  functions: test_smoke_import_all_consumers, test_smoke_import_stage_scripts
  imports: __future__, importlib, pathlib, pytest

**test_pipeline_smoke.py** (59 lines)
  functions: pipeline, test_voice_pipeline_init_without_audio, test_start_emits_expected_stages, test_start_stop_cycle
  imports: __future__, pytest

**test_wake_word.py** (84 lines)
  classes: TestNormalize, TestContainsWakeWord
  imports: __future__, pytest, core.wake_word

## ui/
**__init__.py** (1 lines) [package init]

**hotkey.py** (74 lines)
  classes: HotkeyListener
  imports: __future__, logging, threading
  imported_by: ui/tkinter_ui.py

**overlay.py** (232 lines)
  classes: Overlay
  imports: __future__, logging, tkinter, config
  imported_by: ui/tkinter_ui.py

**tkinter_ui.py** (1175 lines)
  classes: _UILogHandler, VoiceAIApp
  functions: run_ui
  imports: __future__, logging, queue, threading, tkinter

**tray.py** (160 lines)
  classes: SystemTray
  functions: _make_icon_image, open_folder
  imports: __future__, logging, threading, pathlib
  imported_by: ui/tkinter_ui.py

## ui/pyside6/
**__init__.py** (6 lines) [package init]

**app.py** (58 lines)
  functions: _load_qss, run_ui_pyside6
  imports: __future__, pathlib, PySide6.QtWidgets, bootstrap, config
  imported_by: scripts/screenshot_dashboard.py

**bridge.py** (445 lines)
  classes: _Worker, PipelineBridge
  imports: __future__, logging, queue, threading, PySide6.QtCore
  imported_by: scripts/screenshot_dashboard.py, ui/pyside6/app.py, ui/pyside6/dashboard.py

**dashboard.py** (470 lines)
  classes: _HealthDot, DashboardWindow
  functions: _fmt_ms
  imports: __future__, logging, PySide6.QtCore, PySide6.QtGui, PySide6.QtWidgets
  imported_by: scripts/screenshot_dashboard.py, ui/pyside6/app.py

## ui/pyside6/widgets/
**__init__.py** (2 lines) [package init]

**devices_panel.py** (292 lines)
  classes: _BtPoller, _BatteryRow, DevicesPanel
  functions: _format_device
  imports: __future__, logging, PySide6.QtCore, PySide6.QtGui, PySide6.QtWidgets
  imported_by: ui/pyside6/dashboard.py

**level_meter.py** (100 lines)
  classes: LevelMeter
  imports: __future__, PySide6.QtCore, PySide6.QtGui, PySide6.QtWidgets
  imported_by: ui/pyside6/dashboard.py

**screenshot_flash.py** (133 lines)
  classes: ScreenshotFlashOverlay
  imports: __future__, logging, PySide6.QtCore, PySide6.QtGui, PySide6.QtWidgets
  imported_by: ui/pyside6/dashboard.py

**status_indicator.py** (73 lines)
  classes: StatusIndicator
  imports: __future__, PySide6.QtCore, PySide6.QtGui, PySide6.QtWidgets, config
  imported_by: ui/pyside6/dashboard.py

## utils/
**__init__.py** (1 lines) [package init]

**audio_devices.py** (92 lines) [has main]
  classes: DeviceInfo
  functions: list_audio_devices, get_current_devices, _safe, print_devices
  imports: __future__, dataclasses, sounddevice
  imported_by: bootstrap.py, ui/pyside6/widgets/devices_panel.py

**bluetooth_battery.py** (188 lines) [has main]
  classes: BluetoothBattery
  functions: _norm_tokens, bt_matches_audio, get_battery_levels, _cli
  imports: __future__, logging, subprocess, dataclasses
  imported_by: tests/test_bluetooth_matcher.py, ui/pyside6/widgets/devices_panel.py

**errors.py** (42 lines)
  classes: VoiceAIError, AudioError, CancelledError, STTError, LLMError, OllamaError, TTSError, IPCError, ConfigError
  imported_by: main.py, commands/note_command.py, commands/question_command.py, commands/reminder_command.py, core/audio_output.py

**generate_ack_phrases.py** (152 lines) [has main]
  functions: ack_filename, _enumerate_targets, main
  imports: __future__, argparse, logging, shutil, pathlib

**helpers.py** (47 lines)
  functions: save_state_atomic
  imports: __future__, tempfile, pathlib

**tts_speakers.py** (59 lines) [has main]
  functions: main
  imports: __future__


---

# Class Map

## AudioError (utils/errors.py)
inherits: VoiceAIError
"""Raised for audio I/O, recording or device issues."""

## AudioPlayer (core/audio_output.py)
methods:
  def __init__(self, device: ... = None) -> None
  def play_file(self, path: ..., blocking: bool = True, cancel_event: ... = None) -> None
  def play_array(self, samples: np.ndarray, sample_rate: int, blocking: bool = True, cancel_event: ... = None) -> None
  static def _wait(cancel_event: ...) -> None
  static def stop() -> None
"""Plays WAV files synchronously via the system default output device."""

## AudioSettings (config_model.py)
inherits: _Section
members:
  sample_rate: int
  channels: int
  chunk_size: int
  sample_width: int

## AudioStream (core/audio_stream.py)
methods:
  def __init__(self, on_level_update: ... = None, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS, chunk_size: int = CHUNK_SIZE, device: ... = None) -> None
  def start(self) -> None
  def stop(self) -> None
  def __enter__(self) -> 'AudioStream'
  def __exit__(self, exc_type, exc, tb) -> None
  property def is_running(self) -> bool
  property def current_rms(self) -> float
  property def noise_floor_rms(self) -> float
  property def noise_floor_percent(self) -> int
  property def sample_rate(self) -> int
  property def chunk_size(self) -> int
  property def level_queue(self) -> 'queue.Queue[tuple[float, int]]'
  property def chunk_queue(self) -> 'queue.Queue[tuple[np.ndarray, float]]'
  def set_speech_active(self, active: bool) -> None
  def start_recording(self) -> None
  ...+3 more
"""One long-lived microphone stream with RMS monitoring."""

## BaseCommand (commands/base.py)
inherits: ABC
inherited_by: NoteCommand, PauseCommand, ResumeCommand, VolumeUpCommand, VolumeDownCommand, MuteCommand, UnmuteCommand, QuestionCommand, ReminderCommand, ScreenshotCommand, StopCommand, SeekForwardCommand, SeekBackwardCommand
members:
  name: str
  synonyms: Sequence[str]
  command_type: CommandType
  ack_before: ...
  ack_after: ...
methods:
  def execute(self, ctx: CommandContext) -> bool
  def __repr__(self) -> str
"""ABC for every assistant command.  Subclasses set the three class-level attributes and implement :met..."""

## BluetoothBattery [dataclass(frozen=True)] (utils/bluetooth_battery.py)
members:
  name: str
  percent: int

## BootstrapResult [dataclass(frozen=True)] (bootstrap.py)
members:
  input_device: ...
  output_device: ...

## CancelledError (utils/errors.py)
inherits: VoiceAIError
"""Raised when a user-initiated cancel (Esc) interrupts recording/playback."""

## CommandContext [dataclass] (commands/base.py)
members:
  pipeline: Any
  full_text: str
  matched_synonym: str
  session_manager: Any
  player_manager: Any
  volume_control: Any
  ui_callback: ...
  stats: ...
"""Everything a command may need at execution time.  Populated by :class:`VoicePipeline` per dispatch. ..."""

## CommandRegistry (commands/registry.py)
methods:
  def __init__(self, commands: Iterable[BaseCommand] = ...) -> None
  def register(self, command: BaseCommand) -> None
  def get(self, name: str) -> ...
  def __iter__(self) -> Iterator[BaseCommand]
  def __len__(self) -> int
  def names(self) -> list[str]
"""Holds command instances keyed by their canonical ``name``."""

## CommandRouter (commands/router.py)
methods:
  def __init__(self, registry: CommandRegistry, *, wake_words: Iterable[str] = ...) -> None
  property def registry(self) -> CommandRegistry
  def parse(self, text: str) -> ...
  def dispatch(self, text: str, ctx: CommandContext) -> ...
"""Parse normalised text into a :class:`BaseCommand`, then dispatch."""

## CommandSettings (config_model.py)
inherits: _Section
members:
  fuzzy_threshold: float
  llm_fallback: bool
  verbose_ack: bool
  note_fast_path_min_words: int
  question_fast_path_min_words: int

## CommandType (commands/base.py)
inherits: Enum
members:
  GLOBAL
  INSTANT
  CONTENT
  COMPOSITE
"""Coarse classification used by the router and standby state machine.  * ``GLOBAL`` — interrupts/overr..."""

## ConfigError (utils/errors.py)
inherits: VoiceAIError
"""Raised for misconfiguration (missing models, bad parameters)."""

## DashboardWindow (ui/pyside6/dashboard.py)
inherits: QMainWindow
members:
  WINDOW_WIDTH
  WINDOW_HEIGHT
methods:
  def __init__(self, bridge: PipelineBridge) -> None
  def _build_left_column(self) -> QVBoxLayout
  def _on_state_changed(self, name: str, detail: object) -> None
  def _refresh_level_text(self) -> None
  def _on_turn_result(self, result: Any) -> None
  def _on_health(self, snap: dict) -> None
  def _on_models_list(self, models: object, current: object) -> None
  def _on_model_applied(self, name: str, elapsed: float, thinking: bool) -> None
  def _on_model_error(self, msg: str) -> None
  def _on_ipc_changed(self, ok: object) -> None
  def _on_screenshot_taken(self, png: object) -> None
  def _on_ready(self) -> None
  def _on_fatal(self, msg: str) -> None
  def _on_apply_model(self) -> None
  def _on_standby_toggled(self, checked: bool) -> None
  ...+3 more
"""Пульт управления 960×640, двухколоночный."""

## DeepFilterSettings (config_model.py)
inherits: _Section
members:
  enabled: bool
  device: str

## DeviceInfo [dataclass(frozen=True)] (utils/audio_devices.py)
members:
  index: int
  name: str
  input_channels: int
  output_channels: int
  hostapi: str

## DevicesPanel (ui/pyside6/widgets/devices_panel.py)
inherits: QGroupBox
members:
  AUDIO_POLL_MS
  BT_POLL_MS
methods:
  def __init__(self, parent: ... = None) -> None
  def _refresh_audio(self) -> None
  def _on_bt_levels(self, levels: list) -> None
  def _render_bt_rows(self) -> None
  def shutdown(self) -> None
"""Группа: микрофон / выход + список BT-устройств с зарядом."""

## DictateSettings (config_model.py)
inherits: _Section
members:
  pause_threshold: float
  max_duration: float
  initial_timeout: float
  beep_freq: int
  beep_duration_ms: int
  beep_amplitude: float
  unrecognized_beep_freq: int
  unrecognized_beep_duration_ms: int
  unrecognized_beep_amplitude: float

## ErrorBody (ipc/schemas.py)
inherits: BaseModel
members:
  code: ErrorCode
  message: str

## ErrorCode (ipc/protocol.py)
inherits: str, Enum
members:
  INVALID_REQUEST
  UNKNOWN_METHOD
  FILE_NOT_FOUND
  STT_ERROR
  LLM_ERROR
  TTS_ERROR
  AUDIO_ERROR
  CONFIG_ERROR
  INTERNAL_ERROR
"""Server-side error taxonomy. Strings so the wire stays human-readable."""

## GenerateOnlyParams (ipc/schemas.py)
inherits: BaseModel
members:
  model_config
  text: str
  speak: bool
"""Run LLM → TTS on a supplied user text."""

## GenerateOnlyResult (ipc/schemas.py)
inherits: BaseModel
members:
  input_text: str
  output_text: str
  audio_file: ...
  processing_time: float

## GenerateResult [dataclass] (core/ollama_client.py)
members:
  text: str
  model: str
  elapsed_s: float
  eval_count: ...
  prompt_eval_count: ...

## HealthCheckParams (ipc/schemas.py)
inherits: BaseModel
members:
  model_config

## HealthCheckResult (ipc/schemas.py)
inherits: BaseModel
members:
  stt: dict[(str, Any)]
  llm: dict[(str, Any)]
  tts: dict[(str, Any)]
  audio: dict[(str, Any)]

## HotkeyListener (ui/hotkey.py)
methods:
  def __init__(self, hotkey: str, callback: Callable[(..., None)]) -> None
  def start(self) -> None
  def stop(self) -> None
"""Один hotkey → один колбэк. Ничего больше не слушаем."""

## IPCError (utils/errors.py)
inherits: VoiceAIError
inherited_by: IPCRemoteError
"""Raised for IPC protocol / socket issues."""

## IPCRemoteError (ipc/client.py)
inherits: IPCError
methods:
  def __init__(self, code: str, message: str) -> None
"""Raised when the server replies with ``status == "error"``."""

## IPCSettings (config_model.py)
inherits: _Section
members:
  host: str
  port: int

## LLMError (utils/errors.py)
inherits: VoiceAIError
inherited_by: OllamaError
"""Raised for LLM generation failures."""

## LLMErrorKind (core/llm_errors.py)
inherits: str, Enum
members:
  CONNECTION_ERROR
  TIMEOUT
  MODEL_NOT_FOUND
  CONTEXT_OVERFLOW
  RATE_LIMIT
  API_ERROR

## LLMProvider (core/base.py)
inherits: ABC
inherited_by: OllamaLLM, LMStudioLLM
methods:
  def generate(self, prompt: str) -> str
  def is_healthy(self) -> bool
"""Large language model backend (e.g. Ollama, LM Studio)."""

## LLMSettings (config_model.py)
inherits: _Section
members:
  provider: str
  system_prompt: str
  timeout: int
  max_tokens: int
  max_tokens_thinking_multiplier: int
  max_retries: int
  retry_delay: int
  thinking_model_patterns: list[str]
  ollama: OllamaSettings
  lmstudio: LMStudioSettings

## LMStudioClient (core/lmstudio_client.py)
members:
  BACKEND_NAME
methods:
  def __init__(self, base_url: str = LMSTUDIO_BASE_URL, *, timeout: float = OLLAMA_TIMEOUT, max_retries: int = OLLAMA_MAX_RETRIES, retry_delay: float = OLLAMA_RETRY_DELAY) -> None
  def is_healthy(self) -> bool
  def list_models(self) -> list[str]
  def generate(self, prompt: str, *, model: str, max_tokens: ... = None, timeout: ... = None, extra_options: ... = None, system_prompt: ... = None) -> GenerateResult
"""REST client for LM Studio's OpenAI-compatible server."""

## LMStudioLLM (core/lmstudio_client.py)
inherits: LLMProvider
methods:
  def __init__(self, model: ... = None, *, client: ... = None, base_timeout: float = OLLAMA_TIMEOUT, base_max_tokens: int = OLLAMA_MAX_TOKENS, thinking_multiplier: int = OLLAMA_MAX_TOKENS_THINKING_MULTIPLIER, system_prompt: ... = LLM_SYSTEM_PROMPT) -> None
  def generate(self, prompt: str) -> str
  def is_healthy(self) -> bool
  property def model(self) -> str
  property def client(self) -> LMStudioClient
  property def last_metrics(self) -> ...
  def list_models(self) -> list[str]
  def set_model(self, name: str) -> None
  def mark_thinking(self, name: str) -> None
  def _is_thinking_now(self, name: ...) -> bool
  def _maybe_mark_thinking(self, name: ..., raw_text: str) -> None
  def _ensure_model(self) -> str
"""``LLMProvider`` talking to LM Studio; returns TTS-ready text."""

## LMStudioSettings (config_model.py)
inherits: _Section
members:
  base_url: str
  model: str

## LevelMeter (ui/pyside6/widgets/level_meter.py)
inherits: QWidget
methods:
  def __init__(self, parent: ... = None) -> None
  def sizeHint(self) -> QSize
  def set_level(self, rms: float, percent: int) -> None
  def set_vad(self, noise_rms: float, threshold: float) -> None
  property def percent(self) -> int
  property def rms(self) -> float
  property def noise_rms(self) -> float
  property def threshold(self) -> float
  def paintEvent(self, _event) -> None
"""Горизонтальный bar с маркерами шума и порога."""

## LoggingSettings (config_model.py)
inherits: _Section
members:
  level: str
  max_bytes: int
  backup_count: int

## MuteCommand (commands/player_commands.py)
inherits: BaseCommand
members:
  name
  command_type
  synonyms
  ack_after
methods:
  def execute(self, ctx: CommandContext) -> bool

## MuteController (system/audio_session_mute.py)
methods:
  def __init__(self) -> None
  def mute_others(self) -> int
  def unmute_others(self) -> int
  def restore_all(self) -> None
  property def has_muted(self) -> bool
  def _with_com(self, fn)
  def _mute_others_locked(self) -> int
  def _unmute_others_locked(self) -> int
  static def _session_key(session, proc) -> str
"""Заглушает все чужие аудио-сессии Windows и снимает обратно."""

## NoteCommand (commands/note_command.py)
inherits: BaseCommand
members:
  name
  command_type
  ack_before
  NOTE_SAVED_ACK
  synonyms
methods:
  def execute(self, ctx: CommandContext) -> bool

## OllamaClient (core/ollama_client.py)
members:
  BACKEND_NAME
methods:
  def __init__(self, base_url: str = OLLAMA_BASE_URL, *, timeout: float = OLLAMA_TIMEOUT, max_retries: int = OLLAMA_MAX_RETRIES, retry_delay: float = OLLAMA_RETRY_DELAY) -> None
  def is_healthy(self) -> bool
  def list_models(self) -> list[str]
  def generate(self, prompt: str, *, model: ... = None, max_tokens: ... = None, timeout: ... = None, extra_options: ... = None, system_prompt: ... = None) -> GenerateResult
"""Minimal REST client around Ollama's ``/api/generate`` endpoint."""

## OllamaError (utils/errors.py)
inherits: LLMError
"""Raised for Ollama HTTP/API issues. See core.ollama_client for taxonomy."""

## OllamaLLM (core/llm.py)
inherits: LLMProvider
methods:
  def __init__(self, model: str = OLLAMA_MODEL, *, client: ... = None, base_timeout: float = OLLAMA_TIMEOUT, base_max_tokens: int = OLLAMA_MAX_TOKENS, thinking_multiplier: int = OLLAMA_MAX_TOKENS_THINKING_MULTIPLIER, system_prompt: ... = LLM_SYSTEM_PROMPT) -> None
  def generate(self, prompt: str) -> str
  def is_healthy(self) -> bool
  property def model(self) -> str
  property def client(self) -> OllamaClient
  property def last_metrics(self) -> ...
  def list_models(self) -> list[str]
  def set_model(self, name: str) -> None
  def mark_thinking(self, name: str) -> None
  def _is_thinking_now(self, name: ...) -> bool
  def _maybe_mark_thinking(self, name: ..., raw_text: str) -> None
"""``LLMProvider`` that talks to Ollama and returns TTS-ready text."""

## OllamaSettings (config_model.py)
inherits: _Section
members:
  base_url: str
  model: str

## Overlay (ui/overlay.py)
members:
  WIDTH
  HEIGHT
methods:
  def __init__(self, root: tk.Tk, *, position: str = OVERLAY_POSITION, alpha: float = OVERLAY_ALPHA, margin: int = OVERLAY_MARGIN) -> None
  def _build(self) -> None
  def _place(self) -> None
  def _apply_click_through(self) -> None
  def set_state(self, name: str, detail: ... = None) -> None
  def destroy(self) -> None
  def _apply_text(self, text: str) -> None
  def _do_destroy(self) -> None
  def _schedule(self, fn: Callable[(..., None)]) -> None
"""Небольшое always-on-top окно-статус.  Создаётся поверх существующего Tk root; `destroy()` убирает то..."""

## PathsSettings (config_model.py)
inherits: _Section
members:
  base_dir: Path
  models_dir: Path
  logs_dir: Path
  tests_dir: Path
  log_file: Path
  unrecognized_log_file: Path
  ack_dir: Path
  reminders_file: Path
  session_base_dir: str
  tts_output_dir: str
  ...+1 more
"""Пути. ``base_dir`` — корень проекта (задаётся программно, не из TOML).  ``session_base_dir`` / ``tts..."""

## PauseCommand (commands/player_commands.py)
inherits: BaseCommand
members:
  name
  command_type
  synonyms
  ack_after
methods:
  def execute(self, ctx: CommandContext) -> bool

## PipelineBridge (ui/pyside6/bridge.py)
inherits: QObject
members:
  state_changed
  turn_result
  health_update
  level_update
  models_list
  model_applied
  model_error
  ipc_changed
  screenshot_taken
  ready
  ...+7 more
methods:
  def __init__(self, *, with_ipc: bool = True, ipc_host: str = IPC_HOST, ipc_port: int = IPC_PORT, parent: ... = None) -> None
  property def pipeline(self) -> ...
  property def wake_listener(self) -> ...
  def start_pipeline(self) -> None
  def request_turn(self) -> None
  def request_recalibrate(self) -> None
  def request_list_models(self) -> None
  def request_set_model(self, name: str) -> None
  def request_cancel(self) -> None
  def request_toggle_standby(self, enable: bool) -> None
  def shutdown(self) -> None
  def _set_pipeline(self, pipeline: Any) -> None
  def _on_ui_event(self, kind: str, payload: object) -> None
  def _poll_level(self) -> None
  def attach(self, pipeline: Any) -> None
"""Qt-фасад над :class:`VoicePipeline`. Создаётся в UI-потоке."""

## ProtocolError (ipc/protocol.py)
inherits: Exception
"""Raised by the framing layer for malformed or oversized frames."""

## QuestionCommand (commands/question_command.py)
inherits: BaseCommand
members:
  name
  command_type
  ack_before
  synonyms
methods:
  def execute(self, ctx: CommandContext) -> bool

## RecalibrateParams (ipc/schemas.py)
inherits: BaseModel
members:
  model_config
  duration: ...
"""Re-run the VAD calibration (2 sec of silence expected)."""

## RecalibrateResult (ipc/schemas.py)
inherits: BaseModel
members:
  noise_rms: float
  threshold: float
  duration: float

## ReminderCommand (commands/reminder_command.py)
inherits: BaseCommand
members:
  name
  command_type
  ack_before
  ack_after
  synonyms
methods:
  def execute(self, ctx: CommandContext) -> bool

## ReminderScheduler (core/reminders/scheduler.py)
methods:
  def __init__(self, storage: ReminderStorage, fire_callback: FireCallback) -> None
  def add(self, delay_seconds: int, text: str) -> str
  def load_and_restore(self) -> tuple[(int, int)]
  def active_ids(self) -> list[str]
  def shutdown(self) -> None
  def _schedule_timer(self, reminder: dict) -> None
  def _fire(self, reminder: dict) -> None

## ReminderStorage (core/reminders/storage.py)
methods:
  def __init__(self, path: ...) -> None
  property def path(self) -> Path
  def load_all(self) -> list[dict]
  def save_all(self, reminders: Iterable[dict]) -> None
  def add(self, reminder: dict) -> None
  def remove(self, reminder_id: str) -> None
  static def _is_valid(r: object) -> bool

## RemindersSettings (config_model.py)
inherits: _Section
members:
  num_to_words_backend: str

## RequestEnvelope (ipc/schemas.py)
inherits: BaseModel
members:
  model_config
  id: ...
  method: str
  params: dict[(str, Any)]
"""Top-level wire request."""

## ResponseEnvelope (ipc/schemas.py)
inherits: BaseModel
members:
  model_config
  id: ...
  status: Literal[('ok', 'error')]
  result: ...
  error: ...
"""Top-level wire response. Exactly one of ``result`` / ``error`` is set."""

## ResumeCommand (commands/player_commands.py)
inherits: BaseCommand
members:
  name
  command_type
  synonyms
  ack_after
methods:
  def execute(self, ctx: CommandContext) -> bool

## STTError (utils/errors.py)
inherits: VoiceAIError
"""Raised when speech-to-text fails (model load, transcribe, etc.)."""

## STTProvider (core/base.py)
inherits: ABC
inherited_by: WhisperSTT
methods:
  def load_model(self) -> None
  def transcribe(self, audio_path: str) -> str
  def unload_model(self) -> None
"""Speech-to-text backend (e.g. Whisper, Vosk)."""

## STTSettings (config_model.py)
inherits: _Section
members:
  provider: str
  whisper_model_size: str
  whisper_device: str
  whisper_language: str

## ScreenshotCommand (commands/screenshot_command.py)
inherits: BaseCommand
members:
  name
  command_type
  synonyms
  ack_after
methods:
  def execute(self, ctx: CommandContext) -> bool

## ScreenshotFlashOverlay (ui/pyside6/widgets/screenshot_flash.py)
inherits: QWidget
methods:
  def __init__(self, png_bytes: bytes, *, hold_ms: int = 500, zoom_ms: int = 400, parent: ... = None) -> None
  def show_and_animate(self) -> None
  def _start_zoom(self) -> None
"""Полноэкранный оверлей: hold → zoom-to-center с fade-out → self-destroy."""

## ScreenshotFlashSettings (config_model.py)
inherits: _Section
members:
  enabled: bool
  hold_ms: int
  zoom_ms: int

## SeekBackwardCommand (commands/stubs.py)
inherits: BaseCommand
members:
  name
  command_type
  synonyms
  ack_after
methods:
  def execute(self, ctx: CommandContext) -> bool

## SeekForwardCommand (commands/stubs.py)
inherits: BaseCommand
members:
  name
  command_type
  synonyms
  ack_after
methods:
  def execute(self, ctx: CommandContext) -> bool
"""«Перемотай вперёд» — шлёт VK_MEDIA_NEXT_TRACK.  В YouTube/Spotify это «следующий трек/видео». Универ..."""

## SessionManager (system/session_manager.py)
methods:
  def __init__(self, base_dir: ...) -> None
  property def base_dir(self) -> Path
  property def current_dir(self) -> ...
  def ensure_session(self) -> Path
  def save_screenshot(self, png_data: bytes, *, prefix: str = "screenshot") -> Path
  def save_note(self, text: str) -> Path
  def _ensure_session_locked(self) -> Path
"""Хранит «текущую сессию» и пишет в неё артефакты команд."""

## Settings (config_model.py)
inherits: _Section
members:
  paths: PathsSettings
  audio: AudioSettings
  vad: VADSettings
  deepfilter: DeepFilterSettings
  stt: STTSettings
  llm: LLMSettings
  tts: TTSSettings
  wake_word: WakeWordSettings
  commands: CommandSettings
  dictate: DictateSettings
  ...+4 more
"""Корневая модель: собирает все секции в одном объекте.  Чтение из TOML — через ``load_settings()``; п..."""

## SileroSettings (config_model.py)
inherits: _Section
members:
  device: str
  model: str
  speaker: str
  sample_rate: int
  put_accent: bool
  put_yo: bool
  put_stress_homo: bool
  put_yo_homo: bool
  intensity: int

## SileroTTS (core/silero_tts.py)
inherits: TTSProvider
methods:
  def __init__(self, model_id: str = SILERO_MODEL, speaker: str = SILERO_SPEAKER, language: str = TTS_LANGUAGE, device: str = SILERO_DEVICE, sample_rate: int = SILERO_SAMPLE_RATE, put_accent: bool = SILERO_PUT_ACCENT, put_yo: bool = SILERO_PUT_YO, put_stress_homo: bool = SILERO_PUT_STRESS_HOMO, put_yo_homo: bool = SILERO_PUT_YO_HOMO, intensity: ... = SILERO_INTENSITY) -> None
  def load_model(self) -> None
  def synthesize(self, text: str) -> str
  def unload_model(self) -> None
  property def is_loaded(self) -> bool
"""Silero TTS backend (русская модель по умолчанию, CPU-friendly)."""

## StatusIndicator (ui/pyside6/widgets/status_indicator.py)
inherits: QWidget
methods:
  def __init__(self, parent: ... = None) -> None
  def set_state(self, name: str, detail: object = None) -> None
  property def state_name(self) -> str
"""Иконка + жирный текст состояния."""

## StopCommand (commands/stubs.py)
inherits: BaseCommand
members:
  name
  command_type
  synonyms
  ack_after
methods:
  def execute(self, ctx: CommandContext) -> bool
"""«Закончи работу» — выключает дежурный режим (wake-word listener).  Не выход из процесса: окно живёт,..."""

## SystemTray (ui/tray.py)
methods:
  def __init__(self, *, on_enable_assistant: ... = None, on_open_session: ... = None, on_reload_config: ... = None, on_quit: Callable[(..., None)], title: str = "Shura v2") -> None
  def start(self) -> None
  def _run(self) -> None
  def stop(self) -> None
  def _handle_enable(self, _icon, _item) -> None
  def _handle_open(self, _icon, _item) -> None
  def _handle_reload(self, _icon, _item) -> None
  def _handle_quit(self, _icon, _item) -> None
"""Фасад над `pystray.Icon`, крутится в daemon thread.  Колбэки вызываются **из потока pystray** — если..."""

## TTSError (utils/errors.py)
inherits: VoiceAIError
"""Raised when text-to-speech synthesis or model handling fails."""

## TTSProvider (core/base.py)
inherits: ABC
inherited_by: SileroTTS, XTSTTTS
methods:
  def load_model(self) -> None
  def synthesize(self, text: str) -> str
  def unload_model(self) -> None
"""Text-to-speech backend (e.g. XTTS-v2, MeloTTS)."""

## TTSSettings (config_model.py)
inherits: _Section
members:
  provider: str
  language: str
  silero: SileroSettings
  xtts: XTTSSettings

## TestContainsWakeWord (tests/test_wake_word.py)
members:
  WAKE
  ALIASES
methods:
  def test_exact_match(self) -> None
  def test_with_punctuation(self) -> None
  def test_alias_match(self) -> None
  def test_does_not_match_substring(self) -> None
  def test_case_insensitive(self) -> None
  def test_empty_text(self) -> None
  def test_no_aliases(self) -> None
  def test_word_in_middle_of_phrase(self) -> None
  def test_negatives(self, text: str) -> None

## TestNormalize (tests/test_wake_word.py)
methods:
  def test_lowercases(self) -> None
  def test_strips_punctuation(self) -> None
  def test_multiple_spaces_ok(self) -> None
  def test_empty(self) -> None
  def test_cyrillic_stays(self) -> None
  def test_digits_kept(self) -> None

## TranscribeAndRespondParams (ipc/schemas.py)
inherits: BaseModel
members:
  model_config
  audio_file: str
  speak: bool
"""Run STT → LLM → TTS on a pre-recorded WAV."""

## TranscribeAndRespondResult (ipc/schemas.py)
inherits: BaseModel
members:
  input_text: str
  output_text: str
  audio_file: ...
  processing_time: float

## TurnResult [dataclass] (main.py)
members:
  user_text: str
  llm_text: str
  wav_in: ...
  wav_out: ...
  total_s: float
  error: ...
  stt_ms: ...
  llm_ms: ...
  tts_ms: ...
  llm_prompt_tokens: ...
  ...+1 more

## TurnStats [dataclass] (commands/base.py)
members:
  user_text: str
  llm_text: str
  wav_out: ...
  stt_ms: ...
  llm_ms: ...
  tts_ms: ...
  llm_prompt_tokens: ...
  llm_completion_tokens: ...
methods:
  def add_stt_ms(self, ms: float) -> None
"""Накопитель метрик текущего хода для построения финального ``TurnResult``.  CONTENT-команды делают св..."""

## UISettings (config_model.py)
inherits: _Section
members:
  overlay_enabled: bool
  overlay_position: str
  overlay_alpha: float
  overlay_margin: int
  tray_enabled: bool
  screenshot_flash: ScreenshotFlashSettings

## UnmuteCommand (commands/player_commands.py)
inherits: BaseCommand
members:
  name
  command_type
  synonyms
  ack_after
methods:
  def execute(self, ctx: CommandContext) -> bool

## VADSettings (config_model.py)
inherits: _Section
members:
  calibration_duration: float
  calibration_multiplier: float
  min_energy_threshold: int
  pause_threshold: float
  noise_history_size: int
  dynamic_energy_damping: float
  dynamic_energy_ratio: float

## VoiceAIApp (ui/tkinter_ui.py)
members:
  POLL_UI_MS
  POLL_LEVEL_MS
  POLL_LOG_MS
  HEALTH_INTERVAL_S
  MAX_LOG_LINES
methods:
  def __init__(self, root: tk.Tk, *, with_ipc: bool = True, ipc_host: str = IPC_HOST, ipc_port: int = IPC_PORT) -> None
  def _build_ui(self) -> None
  def _attach_log_handler(self) -> None
  def _detach_log_handler(self) -> None
  def _on_listen(self) -> None
  def _on_recalibrate(self) -> None
  def _on_open_sndvol(self) -> None
  def _on_escape(self, _event: object = None) -> None
  def _on_toggle_standby(self) -> None
  def _on_refresh_models(self) -> None
  def _on_apply_model(self) -> None
  def _on_close(self) -> None
  def _tick_shutdown(self) -> None
  def _worker_loop(self) -> None
  def _do_init(self, pipeline_cls: type) -> None
  ...+27 more
"""Tk app shell — see module docstring for threading contract."""

## VoiceAIClient (ipc/client.py)
methods:
  def __init__(self, host: str = IPC_HOST, port: int = IPC_PORT, timeout: float = DEFAULT_TIMEOUT) -> None
  def health_check(self) -> dict[(str, Any)]
  def generate_only(self, text: str, *, speak: bool = True) -> dict[(str, Any)]
  def transcribe_and_respond(self, audio_file: str, *, speak: bool = True) -> dict[(str, Any)]
  def recalibrate(self, duration: ... = None) -> dict[(str, Any)]
  def _call(self, method: str, params: dict[(str, Any)]) -> dict[(str, Any)]
"""Synchronous client for :class:`ipc.server.VoiceAIServer`.  Keeps no state between calls. Safe to cre..."""

## VoiceAIError (utils/errors.py)
inherits: Exception
inherited_by: AudioError, CancelledError, STTError, LLMError, TTSError, IPCError, ConfigError
"""Base class for all voice-assistant-specific errors."""

## VoiceAIServer (ipc/server.py)
methods:
  def __init__(self, pipeline: 'VoicePipeline', host: str = IPC_HOST, port: int = IPC_PORT) -> None
  property def address(self) -> tuple[(str, int)]
  def start(self) -> None
  def stop(self) -> None
"""Manages the background TCP server lifetime.  Typical use::      server = VoiceAIServer(pipeline)    ..."""

## VoiceActivityDetector (core/vad.py)
methods:
  def __init__(self, stream: AudioStream, *, calibration_multiplier: float = CALIBRATION_MULTIPLIER, min_threshold: float = MIN_ENERGY_THRESHOLD, pause_threshold: float = PAUSE_THRESHOLD, damping: float = DYNAMIC_ENERGY_DAMPING, ratio: float = DYNAMIC_ENERGY_RATIO) -> None
  property def threshold(self) -> float
  property def noise_rms(self) -> float
  def reset_threshold(self) -> None
  def calibrate(self, duration: float = CALIBRATION_DURATION) -> tuple[(float, float)]
  def record_until_silence(self, pause_threshold: ... = None, max_duration: float = 30.0, output_path: ... = None, initial_silence_timeout: ... = None, cancel_event: ... = None) -> str
  def _require_running(self) -> None
"""RMS-threshold VAD driven by a shared ``AudioStream``."""

## VoicePipeline (main.py)
methods:
  def __init__(self) -> None
  property def lock(self) -> threading.RLock
  property def session(self) -> SessionManager
  property def audio_mute(self) -> MuteController
  property def stream(self) -> AudioStream
  property def vad(self) -> ...
  property def stt(self)
  property def player(self) -> AudioPlayer
  property def router(self) -> CommandRouter
  property def reminder_scheduler(self) -> ReminderScheduler
  property def cancel_event(self) -> threading.Event
  property def wake_listener(self) -> Any
  def set_ui_callback(self, cb: ...) -> None
  def set_wake_listener(self, listener: Any) -> None
  def request_cancel(self) -> None
  ...+19 more
"""One AudioStream + VAD + STT + LLM + TTS, orchestrated per-turn."""

## VolumeDownCommand (commands/player_commands.py)
inherits: BaseCommand
members:
  name
  command_type
  synonyms
  ack_after
methods:
  def execute(self, ctx: CommandContext) -> bool

## VolumeUpCommand (commands/player_commands.py)
inherits: BaseCommand
members:
  name
  command_type
  synonyms
  ack_after
methods:
  def execute(self, ctx: CommandContext) -> bool

## WakeWordListener (core/wake_word.py)
methods:
  def __init__(self, pipeline, *, on_state: ... = None, wake_word: str = WAKE_WORD, aliases: Sequence[str] = tuple(...), scan_window: float = WAKE_WORD_SCAN_WINDOW, active_timeout: float = WAKE_WORD_ACTIVE_TIMEOUT) -> None
  def start(self) -> None
  def stop(self, timeout: ... = None) -> None
  def enable(self) -> None
  def disable(self) -> None
  property def is_enabled(self) -> bool
  def _loop(self) -> None
  def _iterate(self) -> None
  def _play_beep(self, samples) -> None
  def _emit(self, state: str, payload: object = None) -> None
"""Background wake-word listener driving the standby / active cycle."""

## WakeWordSettings (config_model.py)
inherits: _Section
members:
  word: str
  aliases: list[str]
  enabled_at_startup: bool
  scan_window: float
  active_timeout: float
  beep_on_freq: int
  beep_off_freq: int
  beep_duration_ms: int
  beep_sample_rate: int
  beep_amplitude: float
  ...+1 more

## WhisperSTT (core/stt.py)
inherits: STTProvider
methods:
  def __init__(self, model_size: str = WHISPER_MODEL_SIZE, device: str = WHISPER_DEVICE, language: str = WHISPER_LANGUAGE, download_root: ... = MODELS_DIR) -> None
  def load_model(self) -> None
  def transcribe(self, audio_path: str) -> str
  def unload_model(self) -> None
  property def is_loaded(self) -> bool
"""OpenAI Whisper backend (large-v3 by default)."""

## XTSTTTS (core/tts.py)
inherits: TTSProvider
methods:
  def __init__(self, model_name: str = TTS_MODEL_NAME, device: str = TTS_DEVICE, language: str = TTS_LANGUAGE, speaker_name: ... = None, speaker_wav: ... = None) -> None
  def load_model(self) -> None
  def synthesize(self, text: str) -> str
  def unload_model(self) -> None
  property def is_loaded(self) -> bool
"""Coqui XTTS-v2 backend (multilingual, voice-cloning)."""

## XTTSSettings (config_model.py)
inherits: _Section
members:
  device: str
  model_name: str
  speaker_name: str

## _BatteryRow (ui/pyside6/widgets/devices_panel.py)
inherits: QWidget
methods:
  def __init__(self, name: str, percent: int) -> None
  def set_name(self, name: str) -> None
  def set_percent(self, percent: int) -> None
"""Имя устройства + полоска заряда + проценты."""

## _BtPoller (ui/pyside6/widgets/devices_panel.py)
inherits: QObject
members:
  levels_updated
methods:
  def __init__(self, interval_ms: int = 60000) -> None
  def start(self) -> None
  def stop(self) -> None
  def _tick(self) -> None
"""Тянет get_battery_levels() по таймеру в собственном потоке."""

## _FakeTurn [dataclass] (scripts/screenshot_dashboard.py)
members:
  user_text: str
  llm_text: str
  stt_ms: float
  llm_ms: float
  tts_ms: float
  total_s: float
  error: object
  wav_in: object
  wav_out: object
  llm_prompt_tokens: object
  ...+1 more

## _HARDWAREINPUT (system/media_keys.py)
inherits: ctypes.Structure
members:
  _fields_

## _HealthDot (ui/pyside6/dashboard.py)
inherits: QLabel
members:
  _COLORS
methods:
  def __init__(self, label: str, parent: ... = None) -> None
  def _set(self, kind: str) -> None
  def set_ok(self) -> None
  def set_warn(self) -> None
  def set_err(self) -> None
  def set_off(self) -> None
"""Кружок-индикатор здоровья сервиса (STT/LLM/TTS) для статус-бара."""

## _INPUT (system/media_keys.py)
inherits: ctypes.Structure
members:
  _anonymous_
  _fields_

## _INPUT_UNION (system/media_keys.py)
inherits: ctypes.Union
members:
  _fields_

## _KEYBDINPUT (system/media_keys.py)
inherits: ctypes.Structure
members:
  _fields_

## _MOUSEINPUT (system/media_keys.py)
inherits: ctypes.Structure
members:
  _fields_

## _RequestHandler (ipc/server.py)
inherits: socketserver.BaseRequestHandler
members:
  server: '_Server'
methods:
  def handle(self) -> None
  def _send_error(self, sock: socket.socket, req_id: ..., code: ErrorCode, message: str) -> None
"""One connection, one request, one response. Then close."""

## _Section (config_model.py)
inherits: BaseModel
inherited_by: PathsSettings, AudioSettings, VADSettings, DeepFilterSettings, STTSettings, OllamaSettings, LMStudioSettings, LLMSettings, SileroSettings, XTTSSettings, TTSSettings, WakeWordSettings, CommandSettings, DictateSettings, ScreenshotFlashSettings, UISettings, RemindersSettings, IPCSettings, LoggingSettings, Settings
members:
  model_config
"""База для всех секций: запрет лишних полей, чтобы ``settings.toml`` с опечаткой падал на валидации, а..."""

## _Server (ipc/server.py)
inherits: socketserver.ThreadingTCPServer
members:
  allow_reuse_address
  daemon_threads
methods:
  def __init__(self, server_address: tuple[(str, int)], pipeline: 'VoicePipeline') -> None
"""Stash the pipeline reference on the server so handlers can reach it."""

## _UILogHandler (ui/tkinter_ui.py)
inherits: logging.Handler
members:
  _FMT
methods:
  def __init__(self, sink: queue.Queue[tuple[(int, str)]]) -> None
  def emit(self, record: logging.LogRecord) -> None
"""Ship formatted records into a bounded queue for the UI log viewer."""

## _Worker (ui/pyside6/bridge.py)
inherits: QThread
methods:
  def __init__(self, bridge: 'PipelineBridge') -> None
  def submit(self, job: str, payload: Any = None) -> None
  def run(self) -> None
  def _do_init(self, pipeline_cls: type) -> None
  def _do_turn(self) -> None
  def _do_recalibrate(self) -> None
  def _do_list_models(self) -> None
  def _do_set_model(self, name: str) -> None
  def _do_health(self) -> None
  def _do_stop(self) -> None
"""Поток-владелец :class:`VoicePipeline`. Выполняет init/turn/recalibrate/...  Все сигналы наружу — чер..."""


---

# Functions

## bootstrap.py
def _force_utf8_stdout() -> None
def bootstrap(verbose: bool = True) -> BootstrapResult

## check_stage_10.py
def _banner(title: str) -> None
def _run_pipeline() -> 'object'
def _test_interactive_voice(pipeline: 'object') -> None
def _test_num_to_words() -> None
def _test_parser() -> None
def _test_persistence_note(pipeline: 'object') -> None
def _test_queue_behind_answer(pipeline: 'object') -> None
def _test_schedule_now(pipeline: 'object', delay_seconds: int = 10) -> None
def main() -> int

## check_stage_5.py
def main() -> int

## check_stage_6.py
def _banner(title: str) -> None
def _fail(msg: str) -> None
def _pass(msg: str) -> None
def _test_error_paths(client: VoiceAIClient) -> bool
def _test_generate_only(client: VoiceAIClient) -> bool
def _test_health(client: VoiceAIClient) -> bool
def _test_recalibrate(client: VoiceAIClient) -> bool
def _test_transcribe(client: VoiceAIClient) -> bool
def main() -> int

## check_stage_7.py
def main() -> int

## check_stage_8.py
def main() -> int

## check_stage_9.py
def _banner(title: str) -> None
def _one_pass(stt: WhisperSTT, vad: VoiceActivityDetector, idx: int) -> bool
def main() -> int

## check_stage_config_refactor.py
def _decode_value(encoded)
def main() -> int
def step1_random_constants() -> bool
def step2_toml_override() -> bool
def step3_empty_diff_when_clean() -> bool

## check_stage_dashboard.py
def _make_app_and_bridge()
def main() -> int
def step1_imports() -> bool
def step2_bridge_methods() -> bool
def step3_bridge_signals() -> bool
def step4_dashboard_builds() -> bool
def step5_ready_unlocks_buttons() -> bool
def step6_level_update() -> bool
def step7_turn_result() -> bool
def step8_state_change_icon() -> bool

## check_stage_m4.py
def main() -> int

## check_stage_m6.py
def main() -> int

## check_stage_m8.py
def main() -> int

## commands/note_command.py
def _extract_tail(full_text: str, matched_synonym: str) -> str

## commands/registry.py
def build_default_registry() -> CommandRegistry

## commands/router.py
def _strip_wake_word(text: str, wake_words: Iterable[str]) -> str
def normalize(text: str) -> str

## config_model.py
def _deep_merge(dst: dict[(str, Any)], src: dict[(str, Any)]) -> dict[(str, Any)]
def _diff_dict(current: dict[(str, Any)], defaults: dict[(str, Any)]) -> dict[(str, Any)]
def _to_toml_primitive(value: Any) -> Any
def load_settings(path: ... = None) -> Settings
def save_settings(settings: Settings, path: ... = None, *, diff_only: bool = True) -> Path

## core/__init__.py
def _make_lmstudio() -> LLMProvider
def _make_ollama() -> LLMProvider
def _make_silero() -> TTSProvider
def _make_whisper() -> STTProvider
def _make_xtts() -> TTSProvider
def create_llm_provider(name: ... = None) -> LLMProvider
def create_stt_provider(name: ... = None) -> STTProvider
def create_tts_provider(name: ... = None) -> TTSProvider

## core/audio_beep.py
def generate_beep(freq_hz: float, duration_ms: float, sample_rate: int = 24000, amplitude: float = 0.3, fade_ms: float = 10.0) -> np.ndarray

## core/audio_stream.py
def _compute_rms_int16(samples: np.ndarray) -> float
def _rms_to_percent(rms: float) -> int

## core/llm.py
def is_thinking_model(name: ...) -> bool

## core/llm_errors.py
def classify_http_error(exc: BaseException) -> LLMErrorKind
def format_llm_error_message(kind: LLMErrorKind, exc: ..., *, backend: str, model: str, base_url: str) -> str

## core/lmstudio_client.py
def _is_thinking_model(name: ...) -> bool

## core/preprocessing.py
def _get_deepfilter()
def compute_rms(source: ..., sample_rate: ... = None) -> float
def enhance_audio(input_path: ..., output_path: ...) -> Path
def normalize_audio(input_path: ..., output_path: ..., target_sample_rate: int = SAMPLE_RATE, target_channels: int = CHANNELS, peak_dbfs: float = ...) -> Path
def preload_deepfilter() -> None
def resample_audio(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray

## core/prompt_manager.py
def clean_llm_response(text: str) -> str
def detect_thinking_markers(text: str) -> bool
def strip_think_tags(text: str) -> str
def strip_thinking_chains(text: str) -> str

## core/reminders/num_to_words.py
def humanize_duration(n: int, unit: str) -> str

## core/reminders/num_to_words_external.py
def humanize_duration(n: int, unit: str) -> str

## core/reminders/num_to_words_manual.py
def _number_to_words(n: int) -> str
def humanize_duration(n: int, unit: str) -> str
def plural_form(n: int, forms: tuple[(str, str, str)]) -> str

## core/reminders/parser.py
def parse_reminder_tail(tail: str) -> ...
def unit_to_seconds(count: int, unit: str) -> int

## core/silero_tts.py
def _sanitize_for_silero(text: str) -> str
def _transliterate_latin(text: str) -> str
def _transliterate_word(word: str) -> str
def _truncate_at_sentence(text: str, limit: int = _SILERO_MAX_CHARS) -> str

## core/stt.py
def _is_hallucination(text: str) -> bool
def _load_audio_float32(path: Path) -> np.ndarray
def _vram_snapshot() -> str

## core/tts.py
def _vram_snapshot() -> str

## core/tts_utils.py
def make_output_path(prefix: str = "tts") -> Path
def prepare_output_dir() -> Path
def resolve_speaker_wav(override: ... = None) -> Path

## core/vad.py
def _trim_trailing_silence(audio: np.ndarray, *, sample_rate: int, threshold: float, keep_ms: int, chunk_size: int) -> np.ndarray

## core/wake_word.py
def _normalize(text: str) -> list[str]
def contains_wake_word(text: str, wake_word: str, aliases: Iterable[str] = ...) -> bool

## ipc/protocol.py
def recv_line(sock: socket.socket) -> dict[(str, Any)]
def send_line(sock: socket.socket, payload: dict[(str, Any)]) -> None

## ipc/server.py
def _classify(exc: BaseException) -> ErrorCode
def _handle_generate_only(pipeline: 'VoicePipeline', params: GenerateOnlyParams) -> dict[(str, Any)]
def _handle_health_check(pipeline: 'VoicePipeline', _params: HealthCheckParams) -> dict[(str, Any)]
def _handle_recalibrate(pipeline: 'VoicePipeline', params: RecalibrateParams) -> dict[(str, Any)]
def _handle_transcribe_and_respond(pipeline: 'VoicePipeline', params: TranscribeAndRespondParams) -> dict[(str, Any)]

## logging_config.py
def setup_logging(level: ... = None) -> logging.Logger

## main.py
def _start_ipc_server(pipeline: VoicePipeline, host: str, port: int)
def _tts_requires_gpu_swap() -> bool
def main() -> int
def run_console_mode(*, with_ipc: bool = True, ipc_host: str = IPC_HOST, ipc_port: int = IPC_PORT) -> int
def run_ipc_mode(*, ipc_host: str = IPC_HOST, ipc_port: int = IPC_PORT) -> int

## scripts/dump_commands_snapshot.py
def main() -> None

## scripts/dump_config_snapshot.py
def _encode(value: object) -> object
def collect_constants() -> dict[(str, dict[(str, object)])]
def main() -> None

## scripts/screenshot_dashboard.py
def main() -> int

## system/media_keys.py
def _press_key(vk: int) -> None
def _send_key_event(vk: int, key_up: bool) -> None
def next_track() -> None
def play_pause() -> None
def prev_track() -> None
def volume_down(presses: int = VOLUME_STEP_PRESSES) -> None
def volume_up(presses: int = VOLUME_STEP_PRESSES) -> None

## system/screenshot.py
def take_screenshot(monitor: ... = None) -> bytes

## tests/conftest.py
[pytest.fixture] def mock_audio(mocker)
[pytest.fixture] def mock_providers(mocker)

## tests/test_bluetooth_matcher.py
def test_airpods_pro_matches() -> None
def test_bt_keyboard_does_not_match_typical_audio() -> None
def test_generic_only_bt_name_returns_false() -> None
def test_jbl_speaker_matches() -> None
def test_no_audio_devices_means_no_match() -> None
def test_realtek_does_not_falsely_match_realtek_audio() -> None
def test_wh1000xm4_matches_when_active_output() -> None
def test_xiaomi_sensor_does_not_match() -> None

## tests/test_commands_registry.py
def _load_snapshot() -> list[dict]
def test_all_synonyms_two_words_or_more() -> None
def test_default_registry_matches_snapshot() -> None
def test_registry_rejects_one_word_synonym() -> None

## tests/test_config_contract.py
def _decode_path(entry: dict) -> Path
def _decode_value(encoded: object) -> object
def _load_snapshot() -> dict[(str, dict[(str, object)])]
def test_all_known_constants_present() -> None
[pytest.mark.parametrize("name", sorted(...))] def test_default_values_unchanged(name: str) -> None
def test_no_unexpected_removals() -> None
[pytest.mark.parametrize("name", sorted(...))] def test_types_unchanged(name: str) -> None

## tests/test_config_importers.py
[pytest.mark.parametrize("module_name", CONSUMERS)] def test_smoke_import_all_consumers(module_name: str) -> None
[pytest.mark.parametrize("module_name", STAGE_SCRIPTS)] def test_smoke_import_stage_scripts(module_name: str) -> None

## tests/test_pipeline_smoke.py
[pytest.fixture] def pipeline(mock_providers, mock_audio)
def test_start_emits_expected_stages(pipeline, mock_providers) -> None
def test_start_stop_cycle(pipeline) -> None
def test_voice_pipeline_init_without_audio(pipeline, mock_providers) -> None

## ui/pyside6/app.py
def _load_qss() -> str
def run_ui_pyside6(*, with_ipc: bool = True, ipc_host: str = IPC_HOST, ipc_port: int = IPC_PORT) -> int

## ui/pyside6/dashboard.py
def _fmt_ms(value: ...) -> str

## ui/pyside6/widgets/devices_panel.py
def _format_device(info: ...) -> str

## ui/tkinter_ui.py
def run_ui(*, with_ipc: bool = True, ipc_host: str = IPC_HOST, ipc_port: int = IPC_PORT) -> int

## ui/tray.py
def _make_icon_image()
def open_folder(path: ...) -> None

## utils/audio_devices.py
def _safe(text: str) -> str
def get_current_devices() -> tuple[(..., ...)]
def list_audio_devices() -> list[DeviceInfo]
def print_devices() -> None

## utils/bluetooth_battery.py
def _cli() -> int
def _norm_tokens(name: str) -> set[str]
def bt_matches_audio(bt_name: str, audio_names: list[str]) -> bool
def get_battery_levels(timeout: float = 20.0) -> list[BluetoothBattery]

## utils/generate_ack_phrases.py
def _enumerate_targets() -> list[tuple[(str, str, str)]]
def ack_filename(command_name: str, phase: str) -> str
def main() -> int

## utils/helpers.py
def save_state_atomic(path: ..., payload: Any) -> None

## utils/tts_speakers.py
def main() -> int


---

# Package Structure

## commands/
"""Command subsystem for the Shurochka assistant.  The router parses post-STT text into a :class:`BaseCommand` and dispatches it. If no command matches, """
__all__ = ['BaseCommand', 'CommandContext', 'CommandType', 'TurnStats', 'CommandRegistry', 'CommandRouter', 'build_default_registry']
modules: base, note_command, player_commands, question_command, registry, reminder_command, router, screenshot_command, stubs

## core/
"""Provider factories.  Keeps orchestration code (``main.py``, check scripts, IPC) free from concrete imports: ``create_stt_provider('whisper')`` is all """
__all__ = ['LLMProvider', 'STTProvider', 'TTSProvider', 'create_llm_provider', 'create_stt_provider', 'create_tts_provider']
subpackages: reminders
modules: audio_beep, audio_output, audio_stream, base, llm, llm_errors, lmstudio_client, ollama_client, preprocessing, prompt_manager, silero_tts, stt, tts, tts_utils, vad, wake_word

## core.reminders/
"""Подсистема напоминаний (Этап 10).  * :mod:`parser` — regex-парсер фраз «напомни через N минут …». * :mod:`storage` — JSON-персистентность (абсолютный """
__all__ = ['parse_reminder_tail', 'ReminderScheduler', 'ReminderStorage']
modules: num_to_words, num_to_words_external, num_to_words_manual, parser, scheduler, storage

## ipc/
"""IPC package — exposes server/client entry points for Stage 6.  The wire protocol is a single JSON object per line over TCP (see ``protocol``). Orchest"""
__all__ = ['ErrorCode', 'VoiceAIClient', 'VoiceAIServer']
modules: client, protocol, schemas, server

## players/
"""Media player adapters (VLC / MPC-HC / YouTube) — populated in M4.  Empty in M1; package placeholder so ``commands/`` can import lazily once the real i"""

## system/
"""System-level helpers: SessionManager (M2), screenshots (M3), volume (M5).  Empty in M1 — the package exists so commands can import lazily without hitt"""
modules: audio_session_mute, media_keys, screenshot, session_manager

## tests/
modules: conftest, test_bluetooth_matcher, test_commands_registry, test_config_contract, test_config_importers, test_pipeline_smoke, test_wake_word

## ui/
subpackages: pyside6
modules: hotkey, overlay, tkinter_ui, tray

## ui.pyside6/
"""PySide6-бэкенд UI (в разработке, этапы 3–8 soft-sniffing-allen.md).  Активируется флагом ``python main.py --ui pyside6``. До завершения Этапа 8 живёт """
subpackages: widgets
modules: app, bridge, dashboard

## ui.pyside6.widgets/
"""Кастомные виджеты для PySide6-UI: LevelMeter, StatusIndicator и т.д."""
modules: devices_panel, level_meter, screenshot_flash, status_indicator

## utils/
modules: audio_devices, bluetooth_battery, errors, generate_ack_phrases, helpers, tts_speakers


---

# Quick Reference

## Core/Main
- core/__init__.py
- core/audio_beep.py
- core/audio_output.py
- core/audio_stream.py
- core/base.py
- core/llm.py
- core/llm_errors.py
- core/lmstudio_client.py
- core/ollama_client.py
- core/preprocessing.py
- ...and 16 more

## Models/Entities
- config_model.py
- ipc/schemas.py

## API/Routes
- commands/router.py

## Utils/Helpers
- utils/__init__.py
- utils/audio_devices.py
- utils/bluetooth_battery.py
- utils/errors.py
- utils/generate_ack_phrases.py
- utils/helpers.py
- utils/tts_speakers.py

## Config
- check_stage_config_refactor.py
- config.py
- logging_config.py
- scripts/dump_config_snapshot.py

## Tests
- tests/__init__.py
- tests/conftest.py
- tests/test_bluetooth_matcher.py
- tests/test_commands_registry.py
- tests/test_config_contract.py
- tests/test_config_importers.py
- tests/test_pipeline_smoke.py
- tests/test_wake_word.py

## Other
- bootstrap.py
- check_stage_10.py
- check_stage_5.py
- check_stage_6.py
- check_stage_7.py
- check_stage_8.py
- check_stage_9.py
- check_stage_dashboard.py
- check_stage_m4.py
- check_stage_m6.py
- ...and 35 more
