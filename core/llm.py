"""LLM provider wrapping :class:`OllamaClient`.

The client is dumb on purpose; this layer adds the model-aware defaults:

* **Thinking-model detection** (name matches one of
  ``config.THINKING_MODEL_PATTERNS``) doubles ``num_predict`` and stretches
  the timeout so reasoning-heavy replies don't get chopped — which is exactly
  the case where :func:`strip_think_tags` would otherwise feed TTS a half
  ``<think>`` block.

* **Reasoning scrub at the boundary.** ``generate()`` returns speak-ready
  text via :func:`clean_llm_response`. Callers don't need to remember.

Raw HTTP access stays available through ``self.client`` for diagnostics
(health checks, model listing).
"""

from __future__ import annotations

import logging

from config import (
    LLM_SYSTEM_PROMPT,
    OLLAMA_MAX_TOKENS,
    OLLAMA_MAX_TOKENS_THINKING_MULTIPLIER,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
    THINKING_MODEL_PATTERNS,
)
from core.base import LLMProvider
from core.ollama_client import OllamaClient
from core.prompt_manager import clean_llm_response, detect_thinking_markers

logger = logging.getLogger(__name__)


def is_thinking_model(name: str | None) -> bool:
    """True if ``name`` contains one of the configured thinking patterns."""
    if not name:
        return False
    lower = name.lower()
    return any(pat.lower() in lower for pat in THINKING_MODEL_PATTERNS)


class OllamaLLM(LLMProvider):
    """``LLMProvider`` that talks to Ollama and returns TTS-ready text."""

    def __init__(
        self,
        model: str = OLLAMA_MODEL,
        *,
        client: OllamaClient | None = None,
        base_timeout: float = OLLAMA_TIMEOUT,
        base_max_tokens: int = OLLAMA_MAX_TOKENS,
        thinking_multiplier: int = OLLAMA_MAX_TOKENS_THINKING_MULTIPLIER,
        system_prompt: str | None = LLM_SYSTEM_PROMPT,
    ) -> None:
        self._model = model
        self._client = client or OllamaClient()
        self._base_timeout = float(base_timeout)
        self._base_max_tokens = int(base_max_tokens)
        self._thinking_multiplier = int(thinking_multiplier)
        self._system_prompt = (system_prompt or "").strip() or None
        self._last_metrics: dict | None = None
        # Models we auto-classified as thinking from their own output markers
        # (harmony channels, "Thinking Process:" headers, etc.). Populated by
        # warmup and by every ``generate`` — once a model outs itself as
        # thinking we permanently grant it the larger token/timeout budget.
        self._runtime_thinking: set[str] = set()

    # ---- LLMProvider ----

    def generate(self, prompt: str) -> str:
        thinking = self._is_thinking_now(self._model)
        if thinking:
            max_tokens = self._base_max_tokens * self._thinking_multiplier
            timeout = self._base_timeout * self._thinking_multiplier
            logger.info(
                "Model %s detected as thinking; max_tokens=%d, timeout=%.0fs",
                self._model,
                max_tokens,
                timeout,
            )
        else:
            max_tokens = self._base_max_tokens
            timeout = self._base_timeout

        result = self._client.generate(
            prompt,
            model=self._model,
            max_tokens=max_tokens,
            timeout=timeout,
            system_prompt=self._system_prompt,
        )
        self._last_metrics = {
            "elapsed_s": result.elapsed_s,
            "completion_tokens": result.eval_count,
            "prompt_tokens": result.prompt_eval_count,
        }
        self._maybe_mark_thinking(self._model, result.text)
        cleaned = clean_llm_response(result.text)
        if not cleaned:
            logger.warning(
                "Ollama response empty after cleaning (raw len=%d, thinking=%s)",
                len(result.text),
                thinking,
            )
        return cleaned

    def is_healthy(self) -> bool:
        return self._client.is_healthy()

    # ---- diagnostics ----

    @property
    def model(self) -> str:
        return self._model

    @property
    def client(self) -> OllamaClient:
        return self._client

    @property
    def last_metrics(self) -> dict | None:
        """Timing + token counts from the most recent ``generate`` call."""
        return self._last_metrics

    def list_models(self) -> list[str]:
        """All models installed locally in Ollama (from ``/api/tags``)."""
        return self._client.list_models()

    def set_model(self, name: str) -> None:
        if not name:
            raise ValueError("Model name must not be empty")
        logger.info("OllamaLLM: switching model %r → %r", self._model, name)
        self._model = name

    def mark_thinking(self, name: str) -> None:
        """Flag ``name`` as a thinking model (autodetected or external)."""
        if name and name not in self._runtime_thinking:
            self._runtime_thinking.add(name)
            logger.info(
                "OllamaLLM: model %r marked as thinking — using ×%d token budget",
                name,
                self._thinking_multiplier,
            )

    # ---- internals ----

    def _is_thinking_now(self, name: str | None) -> bool:
        return is_thinking_model(name) or (name is not None and name in self._runtime_thinking)

    def _maybe_mark_thinking(self, name: str | None, raw_text: str) -> None:
        if not name or name in self._runtime_thinking:
            return
        if is_thinking_model(name):
            return
        if detect_thinking_markers(raw_text):
            self.mark_thinking(name)
