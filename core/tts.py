"""Text-to-speech via Coqui XTTS-v2.

Mirrors ``core/stt.py`` so the pipeline sees a symmetric ``load → use →
unload`` lifecycle and can swap VRAM between Whisper and XTTS cleanly.

Design choices:

  * **Lazy import of TTS.api** — Coqui TTS pulls in ~1 GB of deps. We don't
    want every `import core` to pay that cost. The check_stage_4 script or
    ``create_tts_provider`` triggers the real import.
  * **First-run license prompt** — XTTS-v2 is CPML-licensed. The library
    prints an interactive ToS prompt to stdin; we export ``COQUI_TOS_AGREED=1``
    from inside the app so the model loads headlessly. Accepting the license
    is a user responsibility; we just forward the intent.
  * **GPU swap parity** — `unload_model()` mirrors Whisper's cleanup (drop
    refs → ``gc.collect`` → ``torch.cuda.empty_cache``), so Stage 5 can ping-
    pong STT↔TTS on one GPU without piling up allocations.
  * **No streaming for MVP** — Stage 4 requires end-to-end synthesis. Streaming
    inference is left for later; keep the interface small.
"""

from __future__ import annotations

import gc
import logging
import os
import time
from pathlib import Path

from config import (
    TTS_DEVICE,
    TTS_LANGUAGE,
    TTS_MODEL_NAME,
    TTS_SPEAKER_NAME,
)
from core.base import TTSProvider
from core.tts_utils import make_output_path, resolve_speaker_wav
from utils.errors import TTSError

logger = logging.getLogger(__name__)


def _vram_snapshot() -> str:
    """Return a short ``allocated / reserved`` string, or '(no cuda)'."""
    try:
        import torch

        if not torch.cuda.is_available():
            return "(no cuda)"
        alloc = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        return f"alloc={alloc:.2f} GiB, reserved={reserved:.2f} GiB"
    except Exception as exc:
        return f"(vram query failed: {exc})"


class XTSTTTS(TTSProvider):
    """Coqui XTTS-v2 backend (multilingual, voice-cloning)."""

    def __init__(
        self,
        model_name: str = TTS_MODEL_NAME,
        device: str = TTS_DEVICE,
        language: str = TTS_LANGUAGE,
        speaker_name: str | None = None,
        speaker_wav: str | Path | None = None,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._language = language
        # Speaker resolution: explicit arg > config default. Empty string = not set.
        # Built-in speaker wins over WAV cloning if both are configured — it's
        # the cleaner, production-grade path; WAV is for personalisation.
        name = speaker_name if speaker_name is not None else TTS_SPEAKER_NAME
        self._speaker_name = (name or "").strip() or None
        if self._speaker_name is None:
            # Eager path validation — surfaces config mistakes at construction time
            # instead of one minute into model download.
            self._speaker_wav: Path | None = resolve_speaker_wav(speaker_wav)
        else:
            self._speaker_wav = None
        self._model = None

    # ---- TTSProvider ----

    def load_model(self) -> None:
        if self._model is not None:
            logger.debug("XTTS already loaded, skipping")
            return

        # CPML license: the library asks interactively on first load. We opt
        # in via env var so headless runs don't hang on stdin.
        os.environ.setdefault("COQUI_TOS_AGREED", "1")

        try:
            from TTS.api import TTS as CoquiTTS
        except ImportError as exc:
            raise TTSError(
                "coqui-tts is not installed — run `pip install coqui-tts` "
                "(see requirements.txt)."
            ) from exc

        logger.info(
            "Loading XTTS %s on %s (VRAM before: %s)",
            self._model_name,
            self._device,
            _vram_snapshot(),
        )
        t0 = time.monotonic()
        try:
            # gpu=True flag is the path Coqui docs recommend; it internally
            # calls .to(device). We still call .to() below for explicitness
            # on non-cuda devices (e.g. 'cpu' fallback during debugging).
            self._model = CoquiTTS(self._model_name)
            if self._device and self._device != "cpu":
                self._model = self._model.to(self._device)
        except Exception as exc:
            raise TTSError(
                f"Failed to load XTTS {self._model_name} on {self._device}: {exc}"
            ) from exc
        elapsed = time.monotonic() - t0
        logger.info(
            "XTTS loaded in %.1fs (VRAM after: %s)", elapsed, _vram_snapshot()
        )

    def synthesize(self, text: str) -> str:
        if self._model is None:
            raise TTSError("XTTS model not loaded — call load_model() first")

        clean = (text or "").strip()
        if not clean:
            # Explicit error instead of silently producing an empty WAV.
            raise TTSError("Cannot synthesize empty text")

        out_path = make_output_path(prefix="xtts")
        speaker_desc = (
            f"name={self._speaker_name!r}"
            if self._speaker_name is not None
            else f"wav={self._speaker_wav.name}"
        )
        logger.info(
            "Synthesizing %d chars (lang=%s, speaker=%s) → %s",
            len(clean),
            self._language,
            speaker_desc,
            out_path.name,
        )
        t0 = time.monotonic()
        try:
            kwargs: dict = {
                "text": clean,
                "language": self._language,
                "file_path": str(out_path),
            }
            if self._speaker_name is not None:
                kwargs["speaker"] = self._speaker_name
            else:
                kwargs["speaker_wav"] = str(self._speaker_wav)
            self._model.tts_to_file(**kwargs)
        except Exception as exc:
            raise TTSError(f"XTTS synthesis failed: {exc}") from exc
        elapsed = time.monotonic() - t0
        logger.info("Synthesis done in %.2fs → %s", elapsed, out_path)
        return str(out_path)

    def unload_model(self) -> None:
        if self._model is None:
            return
        logger.info("Unloading XTTS (VRAM before: %s)", _vram_snapshot())
        del self._model
        self._model = None
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            logger.debug("torch cleanup skipped", exc_info=True)
        logger.info("XTTS unloaded (VRAM after: %s)", _vram_snapshot())

    # ---- misc ----

    @property
    def is_loaded(self) -> bool:
        return self._model is not None
