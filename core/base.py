"""Abstract provider interfaces.

Every concrete backend (Whisper, Ollama, XTTS, ...) subclasses one of these.
Consumers depend on the ABCs so swapping implementations doesn't touch
orchestration code — see VOICE_AI_PROJECT_SPECIFICATION.md §"Инверсия управления".
"""

from __future__ import annotations

from abc import ABC, abstractmethod


def model_device(model, target: str) -> str:
    """Read a loaded torch model's placement without importing torch."""
    if model is not None:
        device = getattr(model, "device", None)
        if device is not None:
            return str(device)
        try:
            return str(next(model.parameters()).device)
        except (AttributeError, StopIteration, TypeError):
            pass
    return target


class STTProvider(ABC):
    """Speech-to-text backend (e.g. Whisper, Vosk)."""

    @property
    def model_name(self) -> str | None:
        return None

    @property
    def device(self) -> str | None:
        return None

    @abstractmethod
    def load_model(self) -> None:
        """Load the model into memory / GPU."""

    @abstractmethod
    def transcribe(self, audio_path: str) -> str:
        """Transcribe a WAV file to text."""

    @abstractmethod
    def unload_model(self) -> None:
        """Release model resources (important for GPU VRAM swap)."""


class LLMProvider(ABC):
    """Large language model backend (e.g. Ollama, LM Studio)."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate a completion for ``prompt``."""

    def is_healthy(self) -> bool:
        """Return True if the backend is reachable. Override in subclasses."""
        return True


class TTSProvider(ABC):
    """Text-to-speech backend (e.g. XTTS-v2, MeloTTS)."""

    @property
    def model_name(self) -> str | None:
        return None

    @property
    def device(self) -> str | None:
        return None

    @abstractmethod
    def load_model(self) -> None:
        """Load the synthesis model."""

    @abstractmethod
    def synthesize(self, text: str) -> str:
        """Synthesize ``text`` and return a path to the generated WAV."""

    @abstractmethod
    def unload_model(self) -> None:
        """Release model resources."""
