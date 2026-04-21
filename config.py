"""Centralised configuration for the Voice AI Assistant.

All tunables live here so experiments don't require code changes across modules.
Values are grouped by subsystem; see DEVELOPMENT_PLAN.md §"Этап 0" for rationale.
"""

from pathlib import Path

# ====== Пути ======
BASE_DIR = Path(__file__).parent
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"
TESTS_DIR = BASE_DIR / "tests"

LOG_FILE = LOGS_DIR / "voice_ai.log"

# ====== Аудио ======
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1024
SAMPLE_WIDTH = 2  # 16-bit PCM

# Устройства ввода/вывода пользователь выбирает сам в системных настройках
# Windows (Parameters → System → Sound → Input / Output). Приложение берёт
# текущие системные дефолты и лишь показывает их при запуске, чтобы было видно,
# какой микрофон/динамики будут использоваться. Для Bluetooth-гарнитур с
# двусторонним аудио выбирайте профиль "Hands-Free AG Audio" (один и тот же
# вход И выход) — иначе колонки играют, а мик молчит.

# ====== VAD и калибровка (из voice_converter.py) ======
CALIBRATION_DURATION = 2.0        # секунд для калибровки шума
CALIBRATION_MULTIPLIER = 1.8      # порог = max_rms * 1.8
MIN_ENERGY_THRESHOLD = 150        # минимальный порог (защита от тишины)
PAUSE_THRESHOLD = 1.0             # секунд тишины = конец фразы
NOISE_HISTORY_SIZE = 100          # размер скользящего окна для шума
DYNAMIC_ENERGY_DAMPING = 0.15     # скорость адаптации порога
DYNAMIC_ENERGY_RATIO = 1.5        # коэффициент над шумом для динамического порога

# ====== STT (Whisper) ======
STT_PROVIDER = "whisper"
WHISPER_MODEL_SIZE = "large-v3"
WHISPER_DEVICE = "cuda"
WHISPER_LANGUAGE = "russian"

# ====== LLM — общие параметры (reused by Ollama and LM Studio) ======
# Default provider. Switch to "ollama" if you prefer Ollama.
LLM_PROVIDER = "lmstudio"

# Системный промпт: русский сплошной текст, без нумерации/маркеров — чтобы
# модель не копировала «1. 2. 3.» в ответ. Консенсус EP (NAACL 2025): RU-промпт
# снижает language confusion и EN-leak, что критично для русского tacotron'а
# Silero — латиница, emoji и markdown ломают синтез.
#
# Если конкретная модель плохо слушается русского промпта, раскомментируйте
# LLM_SYSTEM_PROMPT_EN ниже и присвойте его в LLM_SYSTEM_PROMPT.
# LLM_SYSTEM_PROMPT_EN = (
#     "You are a voice assistant. Your responses are spoken aloud by a Russian TTS engine "
#     "that only understands Cyrillic script and basic punctuation. "
#     "Latin characters, emoji, and any markup break the speech synthesis.\n"
#     "\n"
#     "Always respond in Russian. Transliterate foreign words into Cyrillic: "
#     "Python → Пайтон, GPU → джи-пи-ю, Linux → Линукс, API → эй-пи-ай. "
#     "Write numbers and dates as words when appropriate.\n"
#     "\n"
#     "Never use emoji, smileys, asterisks, hashes, bullet lists, or any formatting.\n"
#     "\n"
#     "Answer in two to three sentences, straight to the point, as if leaving a voice message. "
#     "If the topic is complex, give the key point only"
# )
LLM_SYSTEM_PROMPT = (
    "Ты — голосовой ассистент. Твои ответы озвучиваются русским синтезатором речи, "
    "который понимает только кириллицу и базовую пунктуацию. "
    "Латиница, эмодзи и любая разметка ломают озвучку.\n"
    "\n"
    "Отвечай только на русском языке. Иностранные слова и имена передавай кириллицей: "
    "Python — Пайтон, GPU — джи-пи-ю, Linux — Линукс, API — эй-пи-ай. "
    "Числа и даты пиши словами, если это уместно.\n"
    "\n"
    "Никогда не используй эмодзи, смайлики, звёздочки, решётки, "
    "списки с маркерами или любое другое форматирование.\n"
    "\n"
    "Отвечай по существу, двумя-тремя предложениями, как в голосовом сообщении. "
    "Если тема сложная, дай главное."
)

# Tunables below share the ``OLLAMA_`` prefix for legacy reasons but apply to
# every HTTP-based LLM backend (Ollama, LM Studio, …).
OLLAMA_TIMEOUT = 120                          # секунд на запрос
# 300 токенов ≈ 450–600 кириллических символов — безопасно для Silero
# (apply_tts падает около 1000 символов; держим запас 75% от лимита).
OLLAMA_MAX_TOKENS = 300
# Thinking-модели: ×3 = 900 токенов (≈600 на <think> + 300 на видимый ответ).
# После strip_think_tags остаётся тот же ~300-токенный ответ для TTS.
OLLAMA_MAX_TOKENS_THINKING_MULTIPLIER = 3
OLLAMA_MAX_RETRIES = 2
OLLAMA_RETRY_DELAY = 5                        # базовая задержка для exp backoff
THINKING_MODEL_PATTERNS = ["thinking", "think", "r1", "reasoning", "qwq"]

# ====== Ollama-specific ======
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma-4-coder"

# ====== LM Studio-specific ======
# Leave LMSTUDIO_MODEL empty ('') to auto-use the single loaded model (if
# exactly one is loaded via the LM Studio UI). Set to a full ID from
# `/v1/models` if several are loaded.
LMSTUDIO_BASE_URL = "http://localhost:1234"
LMSTUDIO_MODEL = "gemma-4-coder"

# ====== TTS — общие параметры ======
# Доступны два бэкенда: "silero" (русский нативный, CPU, быстрый, по умолчанию)
# и "xtts" (мультиязычный, GPU, с voice-cloning). Фабрика — core.create_tts_provider.
TTS_PROVIDER = "silero"
TTS_LANGUAGE = "ru"                                   # ISO код языка синтеза

# ====== TTS — Silero ======
# Silero v5 для русского — специализированная модель с правильной вопросительной
# интонацией, ударениями и омографами. Работает real-time на CPU (~140 MB),
# освобождает GPU под Whisper → GPU-swap не нужен.
SILERO_DEVICE = "cpu"                                 # "cpu" достаточно; "cuda" — для длинных синтезов
SILERO_MODEL = "v5_4_ru"                              # v5_4_ru: xenia/baya/kseniya/aidar; v4_ru: те же + eugene
SILERO_SPEAKER = "xenia"                              # xenia рекомендована для чатботов
SILERO_SAMPLE_RATE = 48000                            # 8000 / 24000 / 48000; 48k — лучшее качество
# Параметры качества (поддерживаются v5; v4 принимает только put_accent/put_yo).
SILERO_PUT_ACCENT = True                              # автоматическая расстановка ударений
SILERO_PUT_YO = True                                  # автоподстановка "ё" вместо "е"
SILERO_PUT_STRESS_HOMO = True                         # ударения в омографах: зАмок/замОк (v5)
SILERO_PUT_YO_HOMO = True                             # "ё" в омографах (v5)
SILERO_INTENSITY = 3                                  # сила вопросительной интонации 1–5 (v5); None отключает

# ====== TTS — Coqui XTTS-v2 ======
TTS_DEVICE = "cuda"                                   # для XTTS
TTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
# У XTTS-v2 два способа задать голос:
#   1. Встроенный студийный спикер по имени (чистый, многократно проверенный).
#   2. Voice-cloning из reference WAV (твой голос/чей-то; нужно 6–30 сек чистой речи).
# Если TTS_SPEAKER_NAME непустая — используется встроенный голос и TTS_SPEAKER_WAV
# игнорируется. Полный список имён: `python -m utils.tts_speakers` (после загрузки модели).
# Проверенные чистые русские по качеству: "Claribel Dervla" (ж),
# "Daisy Studious" (ж), "Damien Black" (м), "Aaron Dreschner" (м).
TTS_SPEAKER_NAME = "Claribel Dervla"
# Reference WAV — fallback когда TTS_SPEAKER_NAME пустая. XTTS клонирует тембр;
# язык reference и синтеза могут отличаться. Рекомендуется 6–30 сек чистой речи.
TTS_SPEAKER_WAV = "tests/fixtures/sample.wav"
# Куда складывать сгенерированные WAV'ы. Создаётся лениво.
TTS_OUTPUT_DIR = "logs/tts_out"

# ====== Wake-word (дежурный режим) ======
# Кодовое слово активации. При его обнаружении в STT-результате программа
# переходит из дежурного режима в активный и ждёт вопрос. Сравнение идёт
# по токенам, в нижнем регистре, без пунктуации — подстроки не считаются
# (шурочкин ≠ шурочка).
WAKE_WORD = "шурочка"
# Альтернативные формы, которые тоже считаются активацией — на случай,
# если STT стабильно слышит одно и то же искажение. Exact-match по токенам.
WAKE_WORD_ALIASES: list[str] = ["шура"]
# Запускать ли дежурный режим автоматически при старте UI.
WAKE_WORD_ENABLED_AT_STARTUP = False
# Максимальная длительность одного окна сканирования (сек). Чем короче —
# тем отзывчивее выключение и меньше монополизация микрофона; но слишком
# короткое обрывает произнесение кодового слова. 4с — компромисс.
WAKE_WORD_SCAN_WINDOW = 4.0
# Таймаут ожидания начала речи в активном режиме (сек). Если пользователь
# молчит дольше — сигнал отмены и возврат в дежурный.
WAKE_WORD_ACTIVE_TIMEOUT = 8.0
# Параметры сигнальных бипов (генерируются в памяти, без внешних файлов).
# Высокий короткий бип на активацию, низкий — на возврат в дежурный (как
# после удачного ответа, так и на таймаут). Амплитуда ощутимая — бипы
# должны быть явно слышны поверх фонового шума.
WAKE_WORD_BEEP_ON_FREQ = 880            # Гц — сигнал активации
WAKE_WORD_BEEP_OFF_FREQ = 440           # Гц — сигнал возврата в дежурный
WAKE_WORD_BEEP_DURATION_MS = 250
WAKE_WORD_BEEP_SAMPLE_RATE = 24000
WAKE_WORD_BEEP_AMPLITUDE = 0.6

# ====== IPC ======
IPC_HOST = "127.0.0.1"
IPC_PORT = 9999

# ====== Logging ======
LOG_LEVEL = "INFO"
LOG_MAX_BYTES = 5 * 1024 * 1024   # 5 MB на файл
LOG_BACKUP_COUNT = 3              # сколько ротированных файлов хранить
