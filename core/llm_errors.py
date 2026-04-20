"""Shared HTTP-based LLM error taxonomy.

Both Ollama and LM Studio (and anything else OpenAI/REST-ish we might add) map
their failure modes to the same ``LLMErrorKind`` enum so retry logic and
error messages live in one place.

Rules encoded here:

* ``CONNECTION_ERROR`` / ``MODEL_NOT_FOUND`` / ``CONTEXT_OVERFLOW`` — fail
  fast. Retrying a server that isn't running, or a prompt that's already too
  long, is pointless.
* ``TIMEOUT`` / ``RATE_LIMIT`` — transient, safe to retry.
* Everything else falls back to ``API_ERROR``.
"""

from __future__ import annotations

from enum import Enum

import httpx


class LLMErrorKind(str, Enum):
    CONNECTION_ERROR = "CONNECTION_ERROR"
    TIMEOUT = "TIMEOUT"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"
    RATE_LIMIT = "RATE_LIMIT"
    API_ERROR = "API_ERROR"


RETRIABLE_KINDS: frozenset[LLMErrorKind] = frozenset(
    {LLMErrorKind.TIMEOUT, LLMErrorKind.RATE_LIMIT}
)


def classify_http_error(exc: BaseException) -> LLMErrorKind:
    """Map an exception from an HTTP LLM client to an :class:`LLMErrorKind`.

    Order matters: specific types (HTTPStatusError, TimeoutException) come
    before the broad ``NetworkError`` / builtin ``ConnectionError`` catch.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        body = (exc.response.text or "").lower()
        if status == 429:
            return LLMErrorKind.RATE_LIMIT
        if status == 404 or ("model" in body and "not found" in body):
            return LLMErrorKind.MODEL_NOT_FOUND
        if "context" in body and (
            "length" in body or "exceed" in body or "overflow" in body
        ):
            return LLMErrorKind.CONTEXT_OVERFLOW
        return LLMErrorKind.API_ERROR

    if isinstance(exc, httpx.TimeoutException):
        return LLMErrorKind.TIMEOUT

    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError, ConnectionError)):
        return LLMErrorKind.CONNECTION_ERROR

    if isinstance(exc, httpx.HTTPError):
        return LLMErrorKind.API_ERROR

    return LLMErrorKind.API_ERROR


def format_llm_error_message(
    kind: LLMErrorKind,
    exc: BaseException | None,
    *,
    backend: str,
    model: str,
    base_url: str,
) -> str:
    """Human-readable message for a failed LLM call."""
    cause = f": {exc}" if exc else ""
    if kind is LLMErrorKind.CONNECTION_ERROR:
        return (
            f"{backend} is not reachable at {base_url}{cause}. "
            "Is the server running?"
        )
    if kind is LLMErrorKind.TIMEOUT:
        return (
            f"{backend} request timed out{cause}. "
            "Increase the timeout or shorten the prompt."
        )
    if kind is LLMErrorKind.MODEL_NOT_FOUND:
        return (
            f"{backend} model {model!r} not found{cause}. "
            "Check the model name in config.py and that it's loaded on the server."
        )
    if kind is LLMErrorKind.CONTEXT_OVERFLOW:
        return f"Prompt exceeds {backend} context window{cause}. Shorten the prompt."
    if kind is LLMErrorKind.RATE_LIMIT:
        return f"{backend} rate-limited the request{cause}."
    return f"{backend} API error{cause}."
