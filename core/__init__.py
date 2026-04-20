"""Provider factories.

Keeps orchestration code (``main.py``, check scripts, IPC) free from concrete
imports: ``create_stt_provider('whisper')`` is all they need. New backends are
added by extending the ``_STT_FACTORIES`` map; existing callers don't change.
"""

from __future__ import annotations

from typing import Callable

from config import LLM_PROVIDER, STT_PROVIDER, TTS_PROVIDER
from core.base import LLMProvider, STTProvider, TTSProvider
from utils.errors import ConfigError


def _make_whisper() -> STTProvider:
    # Local import so optional backends don't drag their deps into every import.
    from core.stt import WhisperSTT

    return WhisperSTT()


def _make_ollama() -> LLMProvider:
    from core.llm import OllamaLLM

    return OllamaLLM()


def _make_lmstudio() -> LLMProvider:
    from core.lmstudio_client import LMStudioLLM

    return LMStudioLLM()


def _make_xtts() -> TTSProvider:
    from core.tts import XTSTTTS

    return XTSTTTS()


def _make_silero() -> TTSProvider:
    from core.silero_tts import SileroTTS

    return SileroTTS()


_STT_FACTORIES: dict[str, Callable[[], STTProvider]] = {
    "whisper": _make_whisper,
}

_LLM_FACTORIES: dict[str, Callable[[], LLMProvider]] = {
    "ollama": _make_ollama,
    "lmstudio": _make_lmstudio,
}

_TTS_FACTORIES: dict[str, Callable[[], TTSProvider]] = {
    "xtts": _make_xtts,
    "silero": _make_silero,
}


def create_stt_provider(name: str | None = None) -> STTProvider:
    """Instantiate an STT provider by name.

    ``name=None`` reads ``config.STT_PROVIDER`` (default: ``whisper``).
    """
    key = (name or STT_PROVIDER).lower()
    try:
        factory = _STT_FACTORIES[key]
    except KeyError as exc:
        available = ", ".join(sorted(_STT_FACTORIES))
        raise ConfigError(
            f"Unknown STT provider {key!r}. Available: {available}"
        ) from exc
    return factory()


def create_llm_provider(name: str | None = None) -> LLMProvider:
    """Instantiate an LLM provider by name.

    ``name=None`` reads ``config.LLM_PROVIDER`` (default: ``ollama``).
    """
    key = (name or LLM_PROVIDER).lower()
    try:
        factory = _LLM_FACTORIES[key]
    except KeyError as exc:
        available = ", ".join(sorted(_LLM_FACTORIES))
        raise ConfigError(
            f"Unknown LLM provider {key!r}. Available: {available}"
        ) from exc
    return factory()


def create_tts_provider(name: str | None = None) -> TTSProvider:
    """Instantiate a TTS provider by name.

    ``name=None`` reads ``config.TTS_PROVIDER`` (default: ``xtts``).
    """
    key = (name or TTS_PROVIDER).lower()
    try:
        factory = _TTS_FACTORIES[key]
    except KeyError as exc:
        available = ", ".join(sorted(_TTS_FACTORIES))
        raise ConfigError(
            f"Unknown TTS provider {key!r}. Available: {available}"
        ) from exc
    return factory()


__all__ = [
    "LLMProvider",
    "STTProvider",
    "TTSProvider",
    "create_llm_provider",
    "create_stt_provider",
    "create_tts_provider",
]
