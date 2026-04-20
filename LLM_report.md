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
Source: Python: 28 py | 3,198 lines | 109 KB
Language: PYTHON

## Packages
core/ — 14 modules, 0 subpackages
ipc/ — 0 modules, 0 subpackages
tests/ — 0 modules, 0 subpackages
ui/ — 0 modules, 0 subpackages
utils/ — 4 modules, 0 subpackages

## Key Classes
AudioStream (core/audio_stream.py)
VoicePipeline (main.py)
LMStudioLLM : LLMProvider (core/lmstudio_client.py)
VoiceActivityDetector (core/vad.py)
OllamaLLM : LLMProvider (core/llm.py)
SileroTTS : TTSProvider (core/silero_tts.py)
WhisperSTT : STTProvider (core/stt.py)
XTSTTTS : TTSProvider (core/tts.py)
AudioPlayer (core/audio_output.py)
LMStudioClient (core/lmstudio_client.py)

## Entry Points
- check_stage_5.py
- main.py
- utils/audio_devices.py
- utils/tts_speakers.py

## Dependencies
- coqui-tts
- httpx
- librosa
- numpy
- openai-whisper
- pyaudio
- pydantic
- pytest
- pytest-mock
- requests
- scipy
- sounddevice
- soundfile
- transformers


---

# File Map

## (root)/
**bootstrap.py** (65 lines)
  classes: BootstrapResult
  functions: _force_utf8_stdout, bootstrap
  imports: __future__, dataclasses, logging_config, utils.audio_devices
  imported_by: main.py

**check_stage_5.py** (91 lines) [has main]
  functions: main
  imports: __future__, main

**config.py** (134 lines)
  imports: pathlib
  imported_by: logging_config.py, main.py, core/audio_stream.py, core/llm.py, core/lmstudio_client.py

**logging_config.py** (47 lines)
  functions: setup_logging
  imports: logging, logging.handlers, config
  imported_by: bootstrap.py

**main.py** (312 lines) [has main]
  classes: TurnResult, VoicePipeline
  functions: _tts_requires_gpu_swap, run_console_mode, main
  imports: __future__, argparse, logging, time, dataclasses
  imported_by: check_stage_5.py

## core/
**__init__.py** (119 lines) [package init]
  functions: _make_whisper, _make_ollama, _make_lmstudio, _make_xtts, _make_silero +3
  imports: __future__, config, core.base, utils.errors
  imported_by: main.py

**audio_output.py** (75 lines)
  classes: AudioPlayer
  imports: __future__, logging, time, pathlib, numpy
  imported_by: main.py

**audio_stream.py** (247 lines)
  classes: AudioStream
  functions: _rms_to_percent, _compute_rms_int16
  imports: __future__, logging, queue, threading, collections
  imported_by: main.py, core/vad.py

**base.py** (55 lines)
  classes: STTProvider, LLMProvider, TTSProvider
  imports: __future__, abc
  imported_by: core/llm.py, core/lmstudio_client.py, core/silero_tts.py, core/stt.py, core/tts.py

**llm.py** (106 lines)
  classes: OllamaLLM
  functions: is_thinking_model
  imports: __future__, logging, config, core.base, core.ollama_client

**llm_errors.py** (98 lines)
  classes: LLMErrorKind
  functions: classify_http_error, format_llm_error_message
  imports: __future__, enum, httpx
  imported_by: core/lmstudio_client.py, core/ollama_client.py

**lmstudio_client.py** (301 lines)
  classes: GenerateResult, LMStudioClient, LMStudioLLM
  functions: _is_thinking_model
  imports: __future__, logging, time, dataclasses, httpx

**ollama_client.py** (177 lines)
  classes: GenerateResult, OllamaClient
  imports: __future__, logging, time, dataclasses, httpx
  imported_by: core/llm.py

**preprocessing.py** (126 lines)
  functions: compute_rms, normalize_audio, resample_audio
  imports: __future__, logging, pathlib, numpy, soundfile

**prompt_manager.py** (45 lines)
  functions: strip_think_tags, clean_llm_response
  imports: __future__
  imported_by: core/llm.py, core/lmstudio_client.py

**silero_tts.py** (241 lines)
  classes: SileroTTS
  functions: _sanitize_for_silero
  imports: __future__, gc, logging, time, pathlib

**stt.py** (183 lines)
  classes: WhisperSTT
  functions: _vram_snapshot, _load_audio_float32
  imports: __future__, gc, logging, time, pathlib

**tts.py** (188 lines)
  classes: XTSTTTS
  functions: _vram_snapshot
  imports: __future__, gc, logging, time, pathlib

**tts_utils.py** (69 lines)
  functions: resolve_speaker_wav, prepare_output_dir, make_output_path
  imports: __future__, itertools, logging, time, pathlib
  imported_by: core/silero_tts.py, core/tts.py

**vad.py** (279 lines)
  classes: VoiceActivityDetector
  functions: _trim_trailing_silence
  imports: __future__, logging, queue, tempfile, time
  imported_by: main.py

## ipc/
**__init__.py** (1 lines) [package init]

## tests/
**__init__.py** (1 lines) [package init]

## ui/
**__init__.py** (1 lines) [package init]

## utils/
**__init__.py** (1 lines) [package init]

**audio_devices.py** (92 lines) [has main]
  classes: DeviceInfo
  functions: list_audio_devices, get_current_devices, _safe, print_devices
  imports: __future__, dataclasses, sounddevice
  imported_by: bootstrap.py

**errors.py** (38 lines)
  classes: VoiceAIError, AudioError, STTError, LLMError, OllamaError, TTSError, IPCError, ConfigError
  imported_by: main.py, core/audio_output.py, core/audio_stream.py, core/lmstudio_client.py, core/ollama_client.py

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
  def play_file(self, path: ..., blocking: bool = True) -> None
  def play_array(self, samples: np.ndarray, sample_rate: int, blocking: bool = True) -> None
  static def stop() -> None
"""Plays WAV files synchronously via the system default output device."""

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

## BootstrapResult [dataclass(frozen=True)] (bootstrap.py)
members:
  input_device: ...
  output_device: ...

## ConfigError (utils/errors.py)
inherits: VoiceAIError
"""Raised for misconfiguration (missing models, bad parameters)."""

## DeviceInfo [dataclass(frozen=True)] (utils/audio_devices.py)
members:
  index: int
  name: str
  input_channels: int
  output_channels: int
  hostapi: str

## GenerateResult [dataclass] (core/ollama_client.py)
members:
  text: str
  model: str
  elapsed_s: float
  eval_count: ...
  prompt_eval_count: ...

## IPCError (utils/errors.py)
inherits: VoiceAIError
"""Raised for IPC protocol / socket issues."""

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

## LMStudioClient (core/lmstudio_client.py)
members:
  BACKEND_NAME
methods:
  def __init__(self, base_url: str = LMSTUDIO_BASE_URL, *, timeout: float = OLLAMA_TIMEOUT, max_retries: int = OLLAMA_MAX_RETRIES, retry_delay: float = OLLAMA_RETRY_DELAY) -> None
  def is_healthy(self) -> bool
  def list_models(self) -> list[str]
  def generate(self, prompt: str, *, model: str, max_tokens: ... = None, timeout: ... = None, extra_options: ... = None) -> GenerateResult
"""REST client for LM Studio's OpenAI-compatible server."""

## LMStudioLLM (core/lmstudio_client.py)
inherits: LLMProvider
methods:
  def __init__(self, model: ... = None, *, client: ... = None, base_timeout: float = OLLAMA_TIMEOUT, base_max_tokens: int = OLLAMA_MAX_TOKENS, thinking_multiplier: int = OLLAMA_MAX_TOKENS_THINKING_MULTIPLIER) -> None
  def generate(self, prompt: str) -> str
  def is_healthy(self) -> bool
  property def model(self) -> str
  property def client(self) -> LMStudioClient
  def _ensure_model(self) -> str
"""``LLMProvider`` talking to LM Studio; returns TTS-ready text."""

## OllamaClient (core/ollama_client.py)
members:
  BACKEND_NAME
methods:
  def __init__(self, base_url: str = OLLAMA_BASE_URL, *, timeout: float = OLLAMA_TIMEOUT, max_retries: int = OLLAMA_MAX_RETRIES, retry_delay: float = OLLAMA_RETRY_DELAY) -> None
  def is_healthy(self) -> bool
  def list_models(self) -> list[str]
  def generate(self, prompt: str, *, model: ... = None, max_tokens: ... = None, timeout: ... = None, extra_options: ... = None) -> GenerateResult
"""Minimal REST client around Ollama's ``/api/generate`` endpoint."""

## OllamaError (utils/errors.py)
inherits: LLMError
"""Raised for Ollama HTTP/API issues. See core.ollama_client for taxonomy."""

## OllamaLLM (core/llm.py)
inherits: LLMProvider
methods:
  def __init__(self, model: str = OLLAMA_MODEL, *, client: ... = None, base_timeout: float = OLLAMA_TIMEOUT, base_max_tokens: int = OLLAMA_MAX_TOKENS, thinking_multiplier: int = OLLAMA_MAX_TOKENS_THINKING_MULTIPLIER) -> None
  def generate(self, prompt: str) -> str
  def is_healthy(self) -> bool
  property def model(self) -> str
  property def client(self) -> OllamaClient
"""``LLMProvider`` that talks to Ollama and returns TTS-ready text."""

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

## SileroTTS (core/silero_tts.py)
inherits: TTSProvider
methods:
  def __init__(self, model_id: str = SILERO_MODEL, speaker: str = SILERO_SPEAKER, language: str = TTS_LANGUAGE, device: str = SILERO_DEVICE, sample_rate: int = SILERO_SAMPLE_RATE, put_accent: bool = SILERO_PUT_ACCENT, put_yo: bool = SILERO_PUT_YO, put_stress_homo: bool = SILERO_PUT_STRESS_HOMO, put_yo_homo: bool = SILERO_PUT_YO_HOMO, intensity: ... = SILERO_INTENSITY) -> None
  def load_model(self) -> None
  def synthesize(self, text: str) -> str
  def unload_model(self) -> None
  property def is_loaded(self) -> bool
"""Silero TTS backend (русская модель по умолчанию, CPU-friendly)."""

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

## TurnResult [dataclass] (main.py)
members:
  user_text: str
  llm_text: str
  wav_in: ...
  wav_out: ...
  total_s: float
  error: ...

## VoiceAIError (utils/errors.py)
inherits: Exception
inherited_by: AudioError, STTError, LLMError, TTSError, IPCError, ConfigError
"""Base class for all voice-assistant-specific errors."""

## VoiceActivityDetector (core/vad.py)
methods:
  def __init__(self, stream: AudioStream, *, calibration_multiplier: float = CALIBRATION_MULTIPLIER, min_threshold: float = MIN_ENERGY_THRESHOLD, pause_threshold: float = PAUSE_THRESHOLD, damping: float = DYNAMIC_ENERGY_DAMPING, ratio: float = DYNAMIC_ENERGY_RATIO) -> None
  property def threshold(self) -> float
  property def noise_rms(self) -> float
  def calibrate(self, duration: float = CALIBRATION_DURATION) -> tuple[(float, float)]
  def record_until_silence(self, pause_threshold: ... = None, max_duration: float = 30.0, output_path: ... = None) -> str
  def _require_running(self) -> None
"""RMS-threshold VAD driven by a shared ``AudioStream``."""

## VoicePipeline (main.py)
methods:
  def __init__(self) -> None
  def start(self) -> None
  def stop(self) -> None
  def process_voice_input(self) -> TurnResult
  def _speak(self, text: str) -> str
  def _speak_safely(self, text: str) -> ...
"""One AudioStream + VAD + STT + LLM + TTS, orchestrated per-turn."""

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


---

# Functions

## bootstrap.py
def _force_utf8_stdout() -> None
def bootstrap(verbose: bool = True) -> BootstrapResult

## check_stage_5.py
def main() -> int

## core/__init__.py
def _make_lmstudio() -> LLMProvider
def _make_ollama() -> LLMProvider
def _make_silero() -> TTSProvider
def _make_whisper() -> STTProvider
def _make_xtts() -> TTSProvider
def create_llm_provider(name: ... = None) -> LLMProvider
def create_stt_provider(name: ... = None) -> STTProvider
def create_tts_provider(name: ... = None) -> TTSProvider

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
def compute_rms(source: ..., sample_rate: ... = None) -> float
def normalize_audio(input_path: ..., output_path: ..., target_sample_rate: int = SAMPLE_RATE, target_channels: int = CHANNELS, peak_dbfs: float = ...) -> Path
def resample_audio(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray

## core/prompt_manager.py
def clean_llm_response(text: str) -> str
def strip_think_tags(text: str) -> str

## core/silero_tts.py
def _sanitize_for_silero(text: str) -> str

## core/stt.py
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

## logging_config.py
def setup_logging(level: ... = None) -> logging.Logger

## main.py
def _tts_requires_gpu_swap() -> bool
def main() -> int
def run_console_mode() -> int

## utils/audio_devices.py
def _safe(text: str) -> str
def get_current_devices() -> tuple[(..., ...)]
def list_audio_devices() -> list[DeviceInfo]
def print_devices() -> None

## utils/helpers.py
def save_state_atomic(path: ..., payload: Any) -> None

## utils/tts_speakers.py
def main() -> int


---

# Package Structure

## core/
"""Provider factories.  Keeps orchestration code (``main.py``, check scripts, IPC) free from concrete imports: ``create_stt_provider('whisper')`` is all """
__all__ = ['LLMProvider', 'STTProvider', 'TTSProvider', 'create_llm_provider', 'create_stt_provider', 'create_tts_provider']
modules: audio_output, audio_stream, base, llm, llm_errors, lmstudio_client, ollama_client, preprocessing, prompt_manager, silero_tts, stt, tts, tts_utils, vad

## ipc/

## tests/

## ui/

## utils/
modules: audio_devices, errors, helpers, tts_speakers


---

# Quick Reference

## Core/Main
- core/__init__.py
- core/audio_output.py
- core/audio_stream.py
- core/base.py
- core/llm.py
- core/llm_errors.py
- core/lmstudio_client.py
- core/ollama_client.py
- core/preprocessing.py
- core/prompt_manager.py
- ...and 6 more

## Utils/Helpers
- utils/__init__.py
- utils/audio_devices.py
- utils/errors.py
- utils/helpers.py
- utils/tts_speakers.py

## Config
- config.py
- logging_config.py

## Tests
- tests/__init__.py

## Other
- bootstrap.py
- check_stage_5.py
- ipc/__init__.py
- ui/__init__.py
