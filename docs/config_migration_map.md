# Карта миграции config.py → Pydantic Settings

Базовая таблица для Этапа 2 редизайна UI: каждая из 90 текущих верхнеуровневых
констант `config.py` получает место в nested-модели `Settings`
(`config_model.py`). `config.py` сохранится как shim — после рефакторинга
24 модуля-потребителя продолжат работать через `from config import X`.

**Колонки:**
- **Старое имя** — имя константы, как её читают потребители сейчас.
- **Новый путь** — точка доступа через singleton `settings.<section>.<field>`.
- **Способ применения** — как этот параметр будет проставляться из UI Settings:
  - ⚡ — мгновенно, через сеттер подсистемы (без перезагрузки);
  - 🔄 — требует перезагрузки одного компонента (Whisper / Silero / XTTS / LLM);
  - ⚠ — только полный перезапуск процесса.

Иконки ⚡/🔄/⚠ попадают в UI Settings рядом с каждым полем (Этап 5).

## Paths (секция `paths`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `BASE_DIR` | `settings.paths.base_dir` | ⚠ |
| `MODELS_DIR` | `settings.paths.models_dir` | ⚠ |
| `LOGS_DIR` | `settings.paths.logs_dir` | ⚠ |
| `TESTS_DIR` | `settings.paths.tests_dir` | ⚠ |
| `LOG_FILE` | `settings.paths.log_file` | ⚠ |
| `UNRECOGNIZED_LOG_FILE` | `settings.paths.unrecognized_log_file` | ⚠ |
| `ACK_DIR` | `settings.paths.ack_dir` | ⚠ |
| `REMINDERS_FILE` | `settings.paths.reminders_file` | ⚠ |
| `SESSION_BASE_DIR` | `settings.paths.session_base_dir` | ⚠ |
| `TTS_OUTPUT_DIR` | `settings.paths.tts_output_dir` | ⚠ |
| `TTS_SPEAKER_WAV` | `settings.paths.tts_speaker_wav` | 🔄 |

## Audio (секция `audio`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `SAMPLE_RATE` | `settings.audio.sample_rate` | ⚠ |
| `CHANNELS` | `settings.audio.channels` | ⚠ |
| `CHUNK_SIZE` | `settings.audio.chunk_size` | ⚠ |
| `SAMPLE_WIDTH` | `settings.audio.sample_width` | ⚠ |

## VAD и калибровка (секция `vad`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `CALIBRATION_DURATION` | `settings.vad.calibration_duration` | ⚡ |
| `CALIBRATION_MULTIPLIER` | `settings.vad.calibration_multiplier` | ⚡ |
| `MIN_ENERGY_THRESHOLD` | `settings.vad.min_energy_threshold` | ⚡ |
| `PAUSE_THRESHOLD` | `settings.vad.pause_threshold` | ⚡ |
| `NOISE_HISTORY_SIZE` | `settings.vad.noise_history_size` | ⚡ |
| `DYNAMIC_ENERGY_DAMPING` | `settings.vad.dynamic_energy_damping` | ⚡ |
| `DYNAMIC_ENERGY_RATIO` | `settings.vad.dynamic_energy_ratio` | ⚡ |

## DeepFilterNet (секция `deepfilter`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `USE_DEEPFILTER` | `settings.deepfilter.enabled` | ⚠ |
| `DEEPFILTER_DEVICE` | `settings.deepfilter.device` | ⚠ |

## STT / Whisper (секция `stt`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `STT_PROVIDER` | `settings.stt.provider` | ⚠ |
| `WHISPER_MODEL_SIZE` | `settings.stt.whisper_model_size` | ⚠ |
| `WHISPER_DEVICE` | `settings.stt.whisper_device` | ⚠ |
| `WHISPER_LANGUAGE` | `settings.stt.whisper_language` | 🔄 |

## LLM — общие (секция `llm`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `LLM_PROVIDER` | `settings.llm.provider` | 🔄 |
| `LLM_SYSTEM_PROMPT` | `settings.llm.system_prompt` | ⚡ |
| `OLLAMA_TIMEOUT` | `settings.llm.timeout` | ⚡ |
| `OLLAMA_MAX_TOKENS` | `settings.llm.max_tokens` | ⚡ |
| `OLLAMA_MAX_TOKENS_THINKING_MULTIPLIER` | `settings.llm.max_tokens_thinking_multiplier` | ⚡ |
| `OLLAMA_MAX_RETRIES` | `settings.llm.max_retries` | ⚡ |
| `OLLAMA_RETRY_DELAY` | `settings.llm.retry_delay` | ⚡ |
| `THINKING_MODEL_PATTERNS` | `settings.llm.thinking_model_patterns` | ⚡ |

## LLM — Ollama (секция `llm.ollama`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `OLLAMA_BASE_URL` | `settings.llm.ollama.base_url` | 🔄 |
| `OLLAMA_MODEL` | `settings.llm.ollama.model` | 🔄 |

## LLM — LM Studio (секция `llm.lmstudio`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `LMSTUDIO_BASE_URL` | `settings.llm.lmstudio.base_url` | 🔄 |
| `LMSTUDIO_MODEL` | `settings.llm.lmstudio.model` | 🔄 |

## TTS — общие (секция `tts`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `TTS_PROVIDER` | `settings.tts.provider` | ⚠ |
| `TTS_LANGUAGE` | `settings.tts.language` | 🔄 |

## TTS — Silero (секция `tts.silero`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `SILERO_DEVICE` | `settings.tts.silero.device` | 🔄 |
| `SILERO_MODEL` | `settings.tts.silero.model` | 🔄 |
| `SILERO_SPEAKER` | `settings.tts.silero.speaker` | 🔄 |
| `SILERO_SAMPLE_RATE` | `settings.tts.silero.sample_rate` | 🔄 |
| `SILERO_PUT_ACCENT` | `settings.tts.silero.put_accent` | ⚡ |
| `SILERO_PUT_YO` | `settings.tts.silero.put_yo` | ⚡ |
| `SILERO_PUT_STRESS_HOMO` | `settings.tts.silero.put_stress_homo` | ⚡ |
| `SILERO_PUT_YO_HOMO` | `settings.tts.silero.put_yo_homo` | ⚡ |
| `SILERO_INTENSITY` | `settings.tts.silero.intensity` | ⚡ |

## TTS — XTTS (секция `tts.xtts`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `TTS_DEVICE` | `settings.tts.xtts.device` | ⚠ |
| `TTS_MODEL_NAME` | `settings.tts.xtts.model_name` | 🔄 |
| `TTS_SPEAKER_NAME` | `settings.tts.xtts.speaker_name` | ⚡ |

## Wake-word (секция `wake_word`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `WAKE_WORD` | `settings.wake_word.word` | ⚡ |
| `WAKE_WORD_ALIASES` | `settings.wake_word.aliases` | ⚡ |
| `WAKE_WORD_ENABLED_AT_STARTUP` | `settings.wake_word.enabled_at_startup` | ⚠ |
| `WAKE_WORD_SCAN_WINDOW` | `settings.wake_word.scan_window` | ⚡ |
| `WAKE_WORD_ACTIVE_TIMEOUT` | `settings.wake_word.active_timeout` | ⚡ |
| `WAKE_WORD_BEEP_ON_FREQ` | `settings.wake_word.beep_on_freq` | ⚡ |
| `WAKE_WORD_BEEP_OFF_FREQ` | `settings.wake_word.beep_off_freq` | ⚡ |
| `WAKE_WORD_BEEP_DURATION_MS` | `settings.wake_word.beep_duration_ms` | ⚡ |
| `WAKE_WORD_BEEP_SAMPLE_RATE` | `settings.wake_word.beep_sample_rate` | ⚡ |
| `WAKE_WORD_BEEP_AMPLITUDE` | `settings.wake_word.beep_amplitude` | ⚡ |
| `WAKE_HOTKEY` | `settings.wake_word.hotkey` | 🔄 |

## Команды / диктовка (секция `commands`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `COMMAND_PARSE_FUZZY_THRESHOLD` | `settings.commands.fuzzy_threshold` | ⚡ |
| `COMMAND_LLM_FALLBACK` | `settings.commands.llm_fallback` | ⚡ |
| `COMMAND_VERBOSE_ACK` | `settings.commands.verbose_ack` | ⚡ |
| `NOTE_FAST_PATH_MIN_WORDS` | `settings.commands.note_fast_path_min_words` | ⚡ |
| `QUESTION_FAST_PATH_MIN_WORDS` | `settings.commands.question_fast_path_min_words` | ⚡ |

## Диктовка (секция `dictate`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `DICTATE_PAUSE_THRESHOLD` | `settings.dictate.pause_threshold` | ⚡ |
| `DICTATE_MAX_DURATION` | `settings.dictate.max_duration` | ⚡ |
| `DICTATE_INITIAL_TIMEOUT` | `settings.dictate.initial_timeout` | ⚡ |
| `DICTATE_BEEP_FREQ` | `settings.dictate.beep_freq` | ⚡ |
| `DICTATE_BEEP_DURATION_MS` | `settings.dictate.beep_duration_ms` | ⚡ |
| `DICTATE_BEEP_AMPLITUDE` | `settings.dictate.beep_amplitude` | ⚡ |
| `UNRECOGNIZED_BEEP_FREQ` | `settings.dictate.unrecognized_beep_freq` | ⚡ |
| `UNRECOGNIZED_BEEP_DURATION_MS` | `settings.dictate.unrecognized_beep_duration_ms` | ⚡ |
| `UNRECOGNIZED_BEEP_AMPLITUDE` | `settings.dictate.unrecognized_beep_amplitude` | ⚡ |

## UI / overlay / tray (секция `ui`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `OVERLAY_ENABLED` | `settings.ui.overlay_enabled` | 🔄 |
| `OVERLAY_POSITION` | `settings.ui.overlay_position` | ⚡ |
| `OVERLAY_ALPHA` | `settings.ui.overlay_alpha` | ⚡ |
| `OVERLAY_MARGIN` | `settings.ui.overlay_margin` | ⚡ |
| `TRAY_ENABLED` | `settings.ui.tray_enabled` | ⚠ |

## Напоминания (секция `reminders`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `NUM_TO_WORDS_BACKEND` | `settings.reminders.num_to_words_backend` | ⚡ |

## IPC (секция `ipc`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `IPC_HOST` | `settings.ipc.host` | ⚠ |
| `IPC_PORT` | `settings.ipc.port` | ⚠ |

## Logging (секция `logging`)

| Старое имя | Новый путь | Применение |
|---|---|---|
| `LOG_LEVEL` | `settings.logging.level` | ⚡ |
| `LOG_MAX_BYTES` | `settings.logging.max_bytes` | ⚠ |
| `LOG_BACKUP_COUNT` | `settings.logging.backup_count` | ⚠ |

---

**Итого:** 90 констант в 14 секциях (`paths`, `audio`, `vad`, `deepfilter`,
`stt`, `llm` с `ollama`/`lmstudio`, `tts` с `silero`/`xtts`, `wake_word`,
`commands`, `dictate`, `ui`, `reminders`, `ipc`, `logging`).

**Важно по shim.** При рефакторинге `config.py` в Этапе 2 каждое старое имя
из колонки «Старое имя» должно остаться доступным как module-level атрибут
(`from config import WHISPER_MODEL_SIZE` продолжает работать). Значения
берутся из singleton `settings` по новому пути. Тест
`tests/test_config_contract.py` (Этап 1) сверяет типы и значения с
baseline-snapshot, поэтому расхождения поймаются автоматически.
