"""Shared, lazy speech resources. No LLM, commands or Qt dependencies."""

from __future__ import annotations

from contextlib import contextmanager
import logging
import os
from pathlib import Path
import re
import tempfile
import threading

from utils.errors import CancelledError, TTSError

logger = logging.getLogger(__name__)


def check_cancel(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise CancelledError("Операция отменена")


def split_text(text: str, limit: int = 300) -> list[str]:
    """Bound every call, including a single oversized word; never truncate."""
    text = text.strip()
    parts = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        window = text[:limit]
        ends = [m.end() for m in re.finditer(r"[.!?;]\s|\n", window)]
        cut = ends[-1] if ends else window.rfind(" ")
        if cut <= 0:
            cut = limit
        parts.append(text[:cut].strip())
        text = text[cut:].lstrip()
    return [part for part in parts if part]


def atomic_export(source: str | Path, destination: str | Path,
                  cancel: threading.Event) -> None:
    """Replace only after a complete copy; retain both source and old target on error."""
    destination = Path(destination)
    check_cancel(cancel)
    fd, temporary = tempfile.mkstemp(prefix=".shura-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as out, open(source, "rb") as inp:
            while block := inp.read(1024 * 1024):
                check_cancel(cancel)
                out.write(block)
        check_cancel(cancel)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


class SpeechRuntime:
    """One owner for resources shared by the assistant and speech tools.

    Operations, including pipeline initialization, hold ``lock``. Merely
    constructing this object does not import audio or model libraries.
    """

    def __init__(self, *, stt_factory=None, tts_factory=None,
                 stream_factory=None, player_factory=None, vad_factory=None,
                 gpu_swap: bool | None = None, speech_gate=None) -> None:
        self.lock = threading.RLock()
        self._speech_gate = speech_gate
        self._stt_factory = stt_factory
        self._tts_factory = tts_factory
        self._stream_factory = stream_factory
        self._player_factory = player_factory
        self._vad_factory = vad_factory
        self._stt = self._tts = self._stream = self._player = self.vad = None
        self._gpu_swap = gpu_swap
        self._temporary = None

    @property
    def stt(self):
        if self._stt is None:
            from core import create_stt_provider
            self._stt = (self._stt_factory or create_stt_provider)()
        return self._stt

    @property
    def tts(self):
        if self._tts is None:
            from core import create_tts_provider
            self._tts = (self._tts_factory or create_tts_provider)()
        return self._tts

    @property
    def stream(self):
        if self._stream is None:
            from core.audio_stream import AudioStream
            self._stream = (self._stream_factory or AudioStream)()
        return self._stream

    @property
    def player(self):
        if self._player is None:
            from core.audio_output import AudioPlayer
            self._player = (self._player_factory or AudioPlayer)()
        return self._player

    @property
    def speech_gate(self):
        """Silero VAD перед распознаванием; общий с ассистентом по умолчанию."""
        if self._speech_gate is None:
            from core.speech_gate import get_speech_gate
            self._speech_gate = get_speech_gate()
        return self._speech_gate

    @property
    def gpu_swap(self) -> bool:
        if self._gpu_swap is None:
            from config import TTS_PROVIDER, TTS_DEVICE, SILERO_DEVICE
            device = SILERO_DEVICE if TTS_PROVIDER.lower() == "silero" else TTS_DEVICE
            self._gpu_swap = str(device).lower().startswith("cuda")
        return self._gpu_swap

    @property
    def workspace(self) -> Path:
        if self._temporary is None:
            self._temporary = tempfile.TemporaryDirectory(prefix="shura-speech-")
        return Path(self._temporary.name)

    @contextmanager
    def operation(self, cancel: threading.Event):
        """Allow cancelling a tool waiting behind an assistant/IPC turn."""
        check_cancel(cancel)
        while not self.lock.acquire(timeout=0.1):
            check_cancel(cancel)
        try:
            check_cancel(cancel)
            yield
        finally:
            self.lock.release()

    def ensure_stt(self, stage=lambda message: None) -> None:
        if self.gpu_swap and self._tts is not None:
            self._tts.unload_model()
        if not self.stt.is_loaded:
            stage("Загружаю распознавание речи…")
            self.stt.load_model()
        # Silero VAD грузится один раз (доли секунды); при сбое — без фильтра.
        self.speech_gate.preload()

    def ensure_microphone(self, stage=lambda message: None) -> None:
        if self.stream.is_running and self.vad is not None:
            return
        try:
            self.stream.start()
            from core.vad import VoiceActivityDetector
            self.vad = (self._vad_factory or VoiceActivityDetector)(self.stream)
            stage("Измеряю шум. Пожалуйста, помолчите…")
            self.vad.calibrate()
        except Exception:
            self.stream.stop()
            self.vad = None
            raise

    @contextmanager
    def tts_session(self, stage=lambda message: None):
        restore_stt = bool(self._stt is not None and self._stt.is_loaded and self.gpu_swap)
        try:
            if self.gpu_swap and self._stt is not None:
                self._stt.unload_model()
            if not self.tts.is_loaded:
                stage("Загружаю голос…")
                self.tts.load_model()
            yield self.tts
        finally:
            if self.gpu_swap:
                if self._tts is not None:
                    self._tts.unload_model()
                if restore_stt:
                    self.ensure_stt(stage)

    def transcribe(self, path: str, cancel: threading.Event,
                   stage=lambda message: None) -> str:
        """Фильтр речи → STT. Фрагмент без речи возвращает пустую строку."""
        from core.speech_gate import discard

        self.ensure_stt(stage)
        check_cancel(cancel)
        gate = self.speech_gate.filter_file(path, purpose="речевые инструменты")
        if not gate.has_speech:
            return ""
        try:
            check_cancel(cancel)
            stage("Распознаю речь…")
            result = self.stt.transcribe(gate.path, profile="dictation").strip()
        finally:
            discard(gate)
        check_cancel(cancel)
        return result

    def synthesize(self, text: str, cancel: threading.Event,
                   stage=lambda message: None, progress=lambda done, total: None) -> str:
        import soundfile as sf

        parts = split_text(text, limit=self.tts.max_input_chars)
        if not parts:
            raise TTSError("Введите текст для озвучки")
        fd, output = tempfile.mkstemp(suffix=".wav", dir=self.workspace)
        os.close(fd)
        writer = None
        try:
            with self.tts_session(stage) as provider:
                for index, part in enumerate(parts):
                    check_cancel(cancel)
                    stage(f"Синтезирую часть {index + 1} из {len(parts)}…")
                    segment = provider.synthesize(part)
                    try:
                        check_cancel(cancel)
                        with sf.SoundFile(segment) as audio:
                            if writer is None:
                                writer = sf.SoundFile(output, "w", samplerate=audio.samplerate,
                                                      channels=audio.channels, subtype="PCM_16")
                            if (audio.samplerate, audio.channels) != (writer.samplerate, writer.channels):
                                raise TTSError("Несовместимые параметры частей аудио")
                            for block in audio.blocks(blocksize=65536):
                                check_cancel(cancel)
                                writer.write(block)
                    finally:
                        Path(segment).unlink(missing_ok=True)
                    progress(index + 1, len(parts))
            check_cancel(cancel)
            if writer is None or writer.frames == 0:
                raise TTSError("Модель вернула пустое аудио")
            writer.close()
            writer = None
            return output
        except BaseException:
            if writer is not None:
                writer.close()
                writer = None
            Path(output).unlink(missing_ok=True)
            raise
        finally:
            if writer is not None:
                writer.close()

    def close(self) -> None:
        with self.lock:
            for resource, method in ((self._player, "stop"), (self._stream, "stop"),
                                     (self._tts, "unload_model"), (self._stt, "unload_model")):
                if resource is not None:
                    try:
                        getattr(resource, method)()
                    except Exception:
                        logger.exception("Speech resource cleanup failed: %s", method)
            self.vad = None
            if self._temporary is not None:
                self._temporary.cleanup()
                self._temporary = None
