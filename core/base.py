"""Abstract provider interfaces.

Every concrete backend (Whisper, Ollama, XTTS, ...) subclasses one of these.
Consumers depend on the ABCs so swapping implementations doesn't touch
orchestration code — see VOICE_AI_PROJECT_SPECIFICATION.md §"Инверсия управления".
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class STTProvider(ABC):
    """Speech-to-text backend (e.g. Whisper, Vosk)."""

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

    @abstractmethod
    def load_model(self) -> None:
        """Load the synthesis model."""

    @abstractmethod
    def synthesize(self, text: str) -> str:
        """Synthesize ``text`` and return a path to the generated WAV."""

    @abstractmethod
    def unload_model(self) -> None:
        """Release model resources."""
