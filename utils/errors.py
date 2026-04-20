"""Domain-specific exceptions for the Voice AI Assistant.

Each subsystem raises its own subclass so callers can react with fine-grained
handling (e.g. retry on TTSError, fail fast on ConfigError).
"""


class VoiceAIError(Exception):
    """Base class for all voice-assistant-specific errors."""


class AudioError(VoiceAIError):
    """Raised for audio I/O, recording or device issues."""


class STTError(VoiceAIError):
    """Raised when speech-to-text fails (model load, transcribe, etc.)."""


class LLMError(VoiceAIError):
    """Raised for LLM generation failures."""


class OllamaError(LLMError):
    """Raised for Ollama HTTP/API issues. See core.ollama_client for taxonomy."""


class TTSError(VoiceAIError):
    """Raised when text-to-speech synthesis or model handling fails."""


class IPCError(VoiceAIError):
    """Raised for IPC protocol / socket issues."""


class ConfigError(VoiceAIError):
    """Raised for misconfiguration (missing models, bad parameters)."""
