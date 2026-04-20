"""Thin HTTP client for Ollama with an error taxonomy and targeted retries.

Design (ported from ``benchmark_runner.py``):

* **Classify first, react second.** Every failure goes through
  :func:`classify_ollama_error` (alias of the shared
  :func:`core.llm_errors.classify_http_error`) to become an
  :class:`LLMErrorKind`. Retry policy and user messages read cleanly off the
  enum instead of pattern-matching strings at each call site.
* **Retry only what's worth retrying.** ``TIMEOUT`` and ``RATE_LIMIT`` are
  transient; everything else fails fast.
* **Exponential-ish backoff.** ``delay * (attempt + 2)``.

The taxonomy lives in ``core.llm_errors`` so LM Studio (and anything else
OpenAI/REST-ish) shares the same error kinds and retry rules.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from config import (
    OLLAMA_BASE_URL,
    OLLAMA_MAX_RETRIES,
    OLLAMA_MAX_TOKENS,
    OLLAMA_MODEL,
    OLLAMA_RETRY_DELAY,
    OLLAMA_TIMEOUT,
)
from core.llm_errors import (
    LLMErrorKind,
    RETRIABLE_KINDS,
    classify_http_error,
    format_llm_error_message,
)
from utils.errors import OllamaError

logger = logging.getLogger(__name__)

# Back-compat aliases — plan and check_stage_3 refer to these names.
OllamaErrorKind = LLMErrorKind
classify_ollama_error = classify_http_error


@dataclass
class GenerateResult:
    text: str
    model: str
    elapsed_s: float
    eval_count: int | None = None
    prompt_eval_count: int | None = None


class OllamaClient:
    """Minimal REST client around Ollama's ``/api/generate`` endpoint."""

    BACKEND_NAME = "Ollama"

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
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
            r = httpx.get(f"{self._base_url}/api/tags", timeout=2.0)
            return 200 <= r.status_code < 300
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            r = httpx.get(f"{self._base_url}/api/tags", timeout=5.0)
            r.raise_for_status()
            data = r.json()
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception as exc:
            logger.debug("list_models failed: %s", exc)
            return []

    # ---- generation ----

    def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
        extra_options: dict[str, Any] | None = None,
        system_prompt: str | None = None,
    ) -> GenerateResult:
        model = model or OLLAMA_MODEL
        max_tokens = int(max_tokens if max_tokens is not None else OLLAMA_MAX_TOKENS)
        request_timeout = float(timeout if timeout is not None else self._timeout)

        options: dict[str, Any] = {"num_predict": max_tokens}
        if extra_options:
            options.update(extra_options)

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        # Ollama принимает system-prompt прямо в payload /api/generate.
        if system_prompt:
            payload["system"] = system_prompt

        last_exc: BaseException | None = None
        last_kind = LLMErrorKind.API_ERROR

        for attempt in range(self._max_retries + 1):
            t0 = time.monotonic()
            try:
                r = httpx.post(
                    f"{self._base_url}/api/generate",
                    json=payload,
                    timeout=request_timeout,
                )
                r.raise_for_status()
                data = r.json()
                elapsed = time.monotonic() - t0
                text = data.get("response", "") or ""
                logger.info(
                    "Ollama generate ok: model=%s elapsed=%.2fs eval=%s prompt_eval=%s",
                    model,
                    elapsed,
                    data.get("eval_count"),
                    data.get("prompt_eval_count"),
                )
                return GenerateResult(
                    text=text,
                    model=model,
                    elapsed_s=elapsed,
                    eval_count=data.get("eval_count"),
                    prompt_eval_count=data.get("prompt_eval_count"),
                )
            except Exception as exc:
                last_exc = exc
                last_kind = classify_http_error(exc)
                logger.warning(
                    "Ollama generate failed (kind=%s, attempt=%d/%d): %s",
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
        err = OllamaError(msg)
        err.kind = last_kind  # type: ignore[attr-defined]
        raise err from last_exc
