"""Pydantic-модель конфигурации + загрузка/сохранение ``settings.toml``.

Эта модель — внутренняя механика Этапа 2 редизайна UI. ``config.py``
превращён в shim: импортирует singleton ``settings`` отсюда и пробрасывает
старые module-level константы (WHISPER_MODEL_SIZE, OLLAMA_TIMEOUT, …) через
маппинг из ``docs/config_migration_map.md``. 24 модуля-потребителя, которые
читают ``from config import X``, продолжают работать без правок.

Слои конфигурации (в порядке приоритета):

1. Дефолты полей (в классах ниже) — соответствуют значениям из исходного
   ``config.py`` (baseline-snapshot).
2. ``settings.toml`` в корне репозитория (если есть) — перекрывает дефолты
   только по перечисленным в нём полям.

Запись через ``save_settings(new, diff_only=True)``: в файл попадают
только поля, отличающиеся от дефолта. Это даёт диф-ориентированный файл,
который читается как "что пользователь изменил".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

try:  # Python 3.11+
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # Python 3.10 — этот проект
    import tomli as tomllib  # type: ignore[no-redef]

import tomli_w

REPO_ROOT = Path(__file__).resolve().parent
SETTINGS_TOML_PATH = REPO_ROOT / "settings.toml"


# --------------------------------------------------------------------------- #
# Секции
# --------------------------------------------------------------------------- #


class _Section(BaseModel):
    """База для всех секций: запрет лишних полей, чтобы ``settings.toml``
    с опечаткой падал на валидации, а не молча терялся."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class PathsSettings(_Section):
    """Пути. ``base_dir`` — корень проекта (задаётся программно, не из TOML).

    ``session_base_dir`` / ``tts_output_dir`` / ``tts_speaker_wav`` остаются
    строками (как в исходном ``config.py``) — чтобы shim отдавал ровно те же
    типы, что были в baseline-snapshot.
    """

    base_dir: Path = REPO_ROOT
    models_dir: Path = REPO_ROOT / "models"
    logs_dir: Path = REPO_ROOT / "logs"
    tests_dir: Path = REPO_ROOT / "tests"
    log_file: Path = REPO_ROOT / "logs" / "voice_ai.log"
    unrecognized_log_file: Path = REPO_ROOT / "logs" / "unrecognized.log"
    ack_dir: Path = REPO_ROOT / "assets" / "ack"
    reminders_file: Path = REPO_ROOT / "logs" / "reminders.json"
    session_base_dir: str = "~/Shura"
    tts_output_dir: str = "logs/tts_out"
    tts_speaker_wav: str = "tests/fixtures/sample.wav"


class AudioSettings(_Section):
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
    sample_width: int = 2  # 16-bit PCM


class VADSettings(_Section):
    calibration_duration: float = 2.0
    calibration_multiplier: float = 1.8
    min_energy_threshold: int = 150
    pause_threshold: float = 1.0
    noise_history_size: int = 100
    dynamic_energy_damping: float = 0.15
    dynamic_energy_ratio: float = 1.5


class DeepFilterSettings(_Section):
    enabled: bool = False
    device: str = "cuda"


class STTSettings(_Section):
    provider: str = "whisper"
    whisper_model_size: str = "large-v3-turbo"
    whisper_device: str = "cuda"
    whisper_language: str = "russian"


class OllamaSettings(_Section):
    base_url: str = "http://localhost:11434"
    model: str = "gemma-4-coder"


class LMStudioSettings(_Section):
    base_url: str = "http://localhost:1234"
    model: str = "gemma-4-coder"


_DEFAULT_SYSTEM_PROMPT = (
    "Ты — Шурочка, голосовой ассистент. О себе говори в женском роде: "
    "готова, узнала, рада.\n"
    "\n"
    "Твои ответы озвучивает русский синтезатор речи. Он понимает только "
    "кириллицу и базовую пунктуацию. Латиница, эмодзи, списки, звёздочки, "
    "решётки и любая разметка ломают озвучку.\n"
    "\n"
    "Отвечай только на русском, даже если вопрос задан иначе.\n"
    "\n"
    "Обращайся к собеседнику на «ты».\n"
    "\n"
    "Иностранные слова и имена передавай кириллицей: Python — Пайтон, "
    "Linux — Линукс, GPU — джи-пи-ю, API — эй-пи-ай.\n"
    "\n"
    "КРИТИЧЕСКИ ВАЖНО: все без исключения цифры, числа, даты, годы, время, "
    "температуры, проценты и любые другие числовые значения пиши ТОЛЬКО "
    "словами в нужном падеже. Ни одной арабской цифры в ответе быть не "
    "должно. Это касается и многозначных чисел, и дат, и диапазонов.\n"
    "Примеры правильного написания:\n"
    "— «12 апреля 1961 года» → «двенадцатого апреля тысяча девятьсот "
    "шестьдесят первого года»\n"
    "— «14:30» → «четырнадцать часов тридцать минут»\n"
    "— «25°C» → «двадцать пять градусов»\n"
    "— «в 2024 году» → «в две тысячи двадцать четвёртом году»\n"
    "— «100 метров» → «сто метров»\n"
    "— «с 1 по 5 мая» → «с первого по пятое мая»\n"
    "Прежде чем выдать ответ, мысленно проверь: нет ли в нём цифр? "
    "Если есть — перепиши словами.\n"
    "\n"
    "Отвечай по существу: одно предложение для простых вопросов, до четырёх — "
    "для сложных. Не растягивай ради полноты и не сокращай в ущерб точности.\n"
    "\n"
    "Если точного ответа не знаешь, скажи «не знаю» одним предложением. "
    "Не выдумывай факты.\n"
    "\n"
    "Не начинай ответ с фраз: «Конечно», «Отличный вопрос», «Как ИИ», "
    "«Как языковая модель», «Важно отметить», «В заключение», "
    "«Надеюсь, это помогло». Не пересказывай вопрос и не пиши "
    "мета-комментарии вроде «давай подумаем», «сейчас разберёмся».\n"
    "\n"
    "Теперь ответь."
)


class LLMSettings(_Section):
    provider: str = "lmstudio"
    system_prompt: str = _DEFAULT_SYSTEM_PROMPT
    timeout: int = 120
    max_tokens: int = 300
    max_tokens_thinking_multiplier: int = 3
    max_retries: int = 2
    retry_delay: int = 5
    thinking_model_patterns: list[str] = Field(
        default_factory=lambda: ["thinking", "think", "r1", "reasoning", "qwq"]
    )
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    lmstudio: LMStudioSettings = Field(default_factory=LMStudioSettings)


class SileroSettings(_Section):
    device: str = "cpu"
    model: str = "v5_4_ru"
    speaker: str = "xenia"
    sample_rate: int = 48000
    put_accent: bool = True
    put_yo: bool = True
    put_stress_homo: bool = True
    put_yo_homo: bool = True
    intensity: int = 3


class XTTSSettings(_Section):
    device: str = "cuda"
    model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    speaker_name: str = "Claribel Dervla"


class TTSSettings(_Section):
    provider: str = "silero"
    language: str = "ru"
    silero: SileroSettings = Field(default_factory=SileroSettings)
    xtts: XTTSSettings = Field(default_factory=XTTSSettings)


class WakeWordSettings(_Section):
    word: str = "шурочка"
    aliases: list[str] = Field(default_factory=lambda: ["шура"])
    enabled_at_startup: bool = False
    scan_window: float = 4.0
    active_timeout: float = 8.0
    beep_on_freq: int = 880
    beep_off_freq: int = 440
    beep_duration_ms: int = 250
    beep_sample_rate: int = 24000
    beep_amplitude: float = 0.6
    hotkey: str = "<ctrl>+<alt>+s"


class CommandSettings(_Section):
    fuzzy_threshold: float = 0.80
    llm_fallback: bool = False
    verbose_ack: bool = True
    note_fast_path_min_words: int = 3
    question_fast_path_min_words: int = 2


class DictateSettings(_Section):
    pause_threshold: float = 5.0
    max_duration: float = 60.0
    initial_timeout: float = 8.0
    beep_freq: int = 1200
    beep_duration_ms: int = 150
    beep_amplitude: float = 0.5
    unrecognized_beep_freq: int = 350
    unrecognized_beep_duration_ms: int = 180
    unrecognized_beep_amplitude: float = 0.5


class UISettings(_Section):
    overlay_enabled: bool = True
    overlay_position: str = "top_right"
    overlay_alpha: float = 0.85
    overlay_margin: int = 16
    tray_enabled: bool = True


class RemindersSettings(_Section):
    num_to_words_backend: str = "manual"


class IPCSettings(_Section):
    host: str = "127.0.0.1"
    port: int = 9999


class LoggingSettings(_Section):
    level: str = "INFO"
    max_bytes: int = 5 * 1024 * 1024
    backup_count: int = 3


# --------------------------------------------------------------------------- #
# Агрегатор
# --------------------------------------------------------------------------- #


class Settings(_Section):
    """Корневая модель: собирает все секции в одном объекте.

    Чтение из TOML — через ``load_settings()``; прямое инстанцирование
    ``Settings()`` даёт чистые дефолты (используется в ``save_settings``
    для вычисления дифа).
    """

    paths: PathsSettings = Field(default_factory=PathsSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    vad: VADSettings = Field(default_factory=VADSettings)
    deepfilter: DeepFilterSettings = Field(default_factory=DeepFilterSettings)
    stt: STTSettings = Field(default_factory=STTSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    wake_word: WakeWordSettings = Field(default_factory=WakeWordSettings)
    commands: CommandSettings = Field(default_factory=CommandSettings)
    dictate: DictateSettings = Field(default_factory=DictateSettings)
    ui: UISettings = Field(default_factory=UISettings)
    reminders: RemindersSettings = Field(default_factory=RemindersSettings)
    ipc: IPCSettings = Field(default_factory=IPCSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


# --------------------------------------------------------------------------- #
# Load / Save
# --------------------------------------------------------------------------- #


def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    """Рекурсивно перекрывает ``dst`` значениями из ``src``. dst мутируется
    и возвращается. Пропущенные секции не очищают дефолты."""
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = value
    return dst


def load_settings(path: Path | None = None) -> Settings:
    """Строит ``Settings``: дефолты + overrides из ``settings.toml`` (если файл есть).

    Отсутствие файла — штатная ситуация (чистый запуск, всё на дефолтах).
    Лишние ключи в TOML падают на валидации ``extra='forbid'`` — это
    намеренно: опечатка в имени поля не должна молча игнорироваться.
    """
    path = path or SETTINGS_TOML_PATH
    if not path.exists():
        return Settings()

    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    # Дефолтная модель → dict, поверх кладём TOML, валидируем в модель.
    merged = Settings().model_dump(mode="python")
    _deep_merge(merged, raw)
    return Settings.model_validate(merged)


def _diff_dict(current: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Возвращает только те пары, где ``current`` отличается от ``defaults``.

    Рекурсивно заходит в вложенные dict'ы. Пустые поддеревья отбрасываются,
    чтобы в TOML не появлялись пустые секции ``[llm.ollama]`` без полей.
    """
    out: dict[str, Any] = {}
    for key, cur_val in current.items():
        def_val = defaults.get(key, object())
        if isinstance(cur_val, dict) and isinstance(def_val, dict):
            sub = _diff_dict(cur_val, def_val)
            if sub:
                out[key] = sub
        elif cur_val != def_val:
            out[key] = cur_val
    return out


def _to_toml_primitive(value: Any) -> Any:
    """tomli_w не пишет Path/Posix* напрямую — нормализуем в str."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: _to_toml_primitive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_toml_primitive(v) for v in value]
    return value


def save_settings(
    settings: Settings,
    path: Path | None = None,
    *,
    diff_only: bool = True,
) -> Path:
    """Сохраняет ``settings`` в TOML. По умолчанию — только отличия от дефолтов.

    ``diff_only=False`` пишет полный снимок (удобно для ``settings.toml.example``).
    """
    path = path or SETTINGS_TOML_PATH
    data = settings.model_dump(mode="python")
    if diff_only:
        data = _diff_dict(data, Settings().model_dump(mode="python"))
    payload = _to_toml_primitive(data)
    path.write_bytes(tomli_w.dumps(payload).encode("utf-8"))
    return path


__all__ = [
    "Settings",
    "PathsSettings",
    "AudioSettings",
    "VADSettings",
    "DeepFilterSettings",
    "STTSettings",
    "LLMSettings",
    "OllamaSettings",
    "LMStudioSettings",
    "TTSSettings",
    "SileroSettings",
    "XTTSSettings",
    "WakeWordSettings",
    "CommandSettings",
    "DictateSettings",
    "UISettings",
    "RemindersSettings",
    "IPCSettings",
    "LoggingSettings",
    "load_settings",
    "save_settings",
    "SETTINGS_TOML_PATH",
]
