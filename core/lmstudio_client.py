"""LM Studio LLM backend (OpenAI-compatible REST).

LM Studio exposes an OpenAI-style API on ``http://localhost:1234/v1`` by
default:

* ``GET  /v1/models``            — list loaded models
* ``POST /v1/chat/completions``  — chat-style generation (used here)

Semantics modelled to match :class:`OllamaClient`:

* Same error taxonomy (:class:`core.llm_errors.LLMErrorKind`) and retry rules
  — only ``TIMEOUT`` / ``RATE_LIMIT`` are retried.
* Same ``GenerateResult`` shape.
* ``LMStudioLLM`` wraps the client with the thinking-model auto-bump, just
  like :class:`core.llm.OllamaLLM`.

Model selection:
  * If ``config.LMSTUDIO_MODEL`` is non-empty, it's used verbatim.
  * If empty, we fetch ``/v1/models``. Exactly one loaded → use it (that's
    not heuristic, there's literally nothing else to pick). Zero or many →
    raise an informative error listing the options so the user picks.

The single-loaded-model case is the common one for LM Studio users who
loaded their model via the UI — they don't have to duplicate the ID into
``config.py``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from config import (
    LLM_SYSTEM_PROMPT,
    LMSTUDIO_BASE_URL,
    LMSTUDIO_MODEL,
    OLLAMA_MAX_RETRIES,
    OLLAMA_MAX_TOKENS,
    OLLAMA_MAX_TOKENS_THINKING_MULTIPLIER,
    OLLAMA_RETRY_DELAY,
    OLLAMA_TIMEOUT,
    THINKING_MODEL_PATTERNS,
)
from core.base import LLMProvider
from core.llm_errors import (
    LLMErrorKind,
    RETRIABLE_KINDS,
    classify_http_error,
    format_llm_error_message,
)
from core.prompt_manager import clean_llm_response, detect_thinking_markers
from utils.errors import ConfigError, OllamaError

logger = logging.getLogger(__name__)


@dataclass
class GenerateResult:
    text: str
    model: str
    elapsed_s: float
    eval_count: int | None = None
    prompt_eval_count: int | None = None


class LMStudioClient:
    """REST client for LM Studio's OpenAI-compatible server."""

    BACKEND_NAME = "LM Studio"

    def __init__(
        self,
        base_url: str = LMSTUDIO_BASE_URL,
        *,
        timeout: float = OLLAMA_TIMEOUT,
        max_retries: int = OLLAMA_MAX_RETRIES,
        retry_delay: float = OLLAMA_RETRY_DELAY,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = float(timeout)
        self._max_retries = int(max_retries)
        self._retry_delay = float(retry_delay)

    # ---- health ----

    def is_healthy(self) -> bool:
        try:
            r = httpx.get(f"{self._base_url}/v1/models", timeout=2.0)
            return 200 <= r.status_code < 300
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Return loaded model IDs (LM Studio only lists loaded ones)."""
        try:
            r = httpx.get(f"{self._base_url}/v1/models", timeout=5.0)
            r.raise_for_status()
            data = r.json()
            return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        except Exception as exc:
            logger.debug("LM Studio list_models failed: %s", exc)
            return []

    # ---- generation ----

    def generate(
        self,
        prompt: str,
        *,
        model: str,
        max_tokens: int | None = None,
        timeout: float | None = None,
        extra_options: dict[str, Any] | None = None,
        system_prompt: str | None = None,
    ) -> GenerateResult:
        max_tokens = int(max_tokens if max_tokens is not None else OLLAMA_MAX_TOKENS)
        request_timeout = float(timeout if timeout is not None else self._timeout)

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if extra_options:
            payload.update(extra_options)

        last_exc: BaseException | None = None
        last_kind = LLMErrorKind.API_ERROR

        for attempt in range(self._max_retries + 1):
            t0 = time.monotonic()
            try:
                r = httpx.post(
                    f"{self._base_url}/v1/chat/completions",
                    json=payload,
                    timeout=request_timeout,
                )
                r.raise_for_status()
                data = r.json()
                elapsed = time.monotonic() - t0

                choices = data.get("choices") or []
                text = ""
                if choices:
                    msg = choices[0].get("message") or {}
                    text = msg.get("content", "") or ""

                usage = data.get("usage") or {}
                eval_count = usage.get("completion_tokens")
                prompt_eval_count = usage.get("prompt_tokens")

                logger.info(
                    "LM Studio generate ok: model=%s elapsed=%.2fs completion=%s prompt=%s",
                    model,
                    elapsed,
                    eval_count,
                    prompt_eval_count,
                )
                return GenerateResult(
                    text=text,
                    model=model,
                    elapsed_s=elapsed,
                    eval_count=eval_count,
                    prompt_eval_count=prompt_eval_count,
                )
            except Exception as exc:
                last_exc = exc
                last_kind = classify_http_error(exc)
                logger.warning(
                    "LM Studio generate failed (kind=%s, attempt=%d/%d): %s",
                    last_kind.value,
                    attempt,
                    self._max_retries,
                    exc,
                )
                if last_kind not in RETRIABLE_KINDS or attempt >= self._max_retries:
                    break
                backoff = self._retry_delay * (attempt + 2)
                logger.info("Retrying after %.1fs…", backoff)
                time.sleep(backoff)

        msg = format_llm_error_message(
            last_kind,
            last_exc,
            backend=self.BACKEND_NAME,
            model=model,
            base_url=self._base_url,
        )
        err = OllamaError(msg)  # LLMError ancestor — reused for parity
        err.kind = last_kind  # type: ignore[attr-defined]
        raise err from last_exc


def _is_thinking_model(name: str | None) -> bool:
    if not name:
        return False
    lower = name.lower()
    return any(pat.lower() in lower for pat in THINKING_MODEL_PATTERNS)


class LMStudioLLM(LLMProvider):
    """``LLMProvider`` talking to LM Studio; returns TTS-ready text."""

    def __init__(
        self,
        model: str | None = None,
        *,
        client: LMStudioClient | None = None,
        base_timeout: float = OLLAMA_TIMEOUT,
        base_max_tokens: int = OLLAMA_MAX_TOKENS,
        thinking_multiplier: int = OLLAMA_MAX_TOKENS_THINKING_MULTIPLIER,
        system_prompt: str | None = LLM_SYSTEM_PROMPT,
    ) -> None:
        # "" / None → defer resolution to first use so construction doesn't
        # hit the server (factory stays cheap, tests don't require a live box).
        self._configured_model = (model if model is not None else LMSTUDIO_MODEL) or ""
        self._resolved_model: str | None = (
            self._configured_model if self._configured_model else None
        )
        self._client = client or LMStudioClient()
        self._base_timeout = float(base_timeout)
        self._base_max_tokens = int(base_max_tokens)
        self._thinking_multiplier = int(thinking_multiplier)
        self._system_prompt = (system_prompt or "").strip() or None
        self._last_metrics: dict | None = None
        # Models auto-classified as thinking from their own output markers.
        # Populated by warmup and by every ``generate``; once flagged the
        # model permanently gets the ×N max_tokens/timeout budget.
        self._runtime_thinking: set[str] = set()

    # ---- LLMProvider ----

    def generate(self, prompt: str) -> str:
        model = self._ensure_model()

        thinking = self._is_thinking_now(model)
        if thinking:
            max_tokens = self._base_max_tokens * self._thinking_multiplier
            timeout = self._base_timeout * self._thinking_multiplier
            logger.info(
                "Model %s detected as thinking; max_tokens=%d, timeout=%.0fs",
                model,
                max_tokens,
                timeout,
            )
        else:
            max_tokens = self._base_max_tokens
            timeout = self._base_timeout

        result = self._client.generate(
            prompt,
            model=model,
            max_tokens=max_tokens,
            timeout=timeout,
            system_prompt=self._system_prompt,
        )
        self._last_metrics = {
            "elapsed_s": result.elapsed_s,
            "completion_tokens": result.eval_count,
            "prompt_tokens": result.prompt_eval_count,
        }
        self._maybe_mark_thinking(model, result.text)
        cleaned = clean_llm_response(result.text)
        if not cleaned:
            logger.warning(
                "LM Studio response empty after cleaning (raw len=%d, thinking=%s)",
                len(result.text),
                thinking,
            )
        return cleaned

    def is_healthy(self) -> bool:
        return self._client.is_healthy()

    # ---- diagnostics ----

    @property
    def model(self) -> str:
        # For read-only consumers (UI, logs). If not resolved, show the raw
        # config value so users see what will be attempted.
        return self._resolved_model or self._configured_model or "(auto)"

    @property
    def client(self) -> LMStudioClient:
        return self._client

    @property
    def last_metrics(self) -> dict | None:
        """Timing + token counts from the most recent ``generate`` call."""
        return self._last_metrics

    def list_models(self) -> list[str]:
        """Models currently loaded in LM Studio (from ``/v1/models``)."""
        return self._client.list_models()

    def set_model(self, name: str) -> None:
        if not name:
            raise ValueError("Model name must not be empty")
        logger.info(
            "LMStudioLLM: switching model %r → %r",
            self._resolved_model or self._configured_model,
            name,
        )
        self._configured_model = name
        self._resolved_model = name

    def mark_thinking(self, name: str) -> None:
        """Flag ``name`` as a thinking model (autodetected or external)."""
        if name and name not in self._runtime_thinking:
            self._runtime_thinking.add(name)
            logger.info(
                "LMStudioLLM: model %r marked as thinking — using ×%d token budget",
                name,
                self._thinking_multiplier,
            )

    # ---- internals ----

    def _is_thinking_now(self, name: str | None) -> bool:
        return _is_thinking_model(name) or (
            name is not None and name in self._runtime_thinking
        )

    def _maybe_mark_thinking(self, name: str | None, raw_text: str) -> None:
        if not name or name in self._runtime_thinking:
            return
        if _is_thinking_model(name):
            return
        if detect_thinking_markers(raw_text):
            self.mark_thinking(name)

    def _ensure_model(self) -> str:
        if self._resolved_model:
            return self._resolved_model

        models = self._client.list_models()
        if len(models) == 1:
            self._resolved_model = models[0]
            logger.info(
                "LM Studio: no model configured; using the single loaded model %r",
                self._resolved_model,
            )
            return self._resolved_model
        if not models:
            raise ConfigError(
                "LM Studio reports no loaded models. Load a model in the UI "
                "(Developer → Local Server → Load Model) or set LMSTUDIO_MODEL "
                "explicitly in config.py."
            )
        raise ConfigError(
            "LM Studio has multiple models loaded: "
            + ", ".join(repr(m) for m in models)
            + ". Set LMSTUDIO_MODEL in config.py to the one you want to use."
        )
