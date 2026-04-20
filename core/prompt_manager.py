"""Prompt / response text utilities.

Right now only the reasoning-tag scrubber and the MVP response-cleaner. Kept
separate from the HTTP layer so unit tests don't need a live Ollama.

Ported from ``benchmark_runner.py`` — the non-obvious bit is that reasoning
models sometimes run out of tokens **mid-thought**, leaving an unclosed
``<think>...`` that stretches to EOS. If we don't strip those too, TTS ends up
happily narrating chain-of-thought at the user.
"""

from __future__ import annotations

import re

_THINK_CLOSED = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_UNCLOSED = re.compile(r"<think>.*\Z", re.DOTALL | re.IGNORECASE)

# Fenced code blocks read terribly through TTS; strip the fence markers but
# keep the code text itself so the user still hears what was generated.
_CODE_FENCE_OPEN = re.compile(r"```[a-zA-Z0-9_+\-]*\n?")


def strip_think_tags(text: str) -> str:
    """Remove ``<think>...</think>`` blocks (closed) and any unclosed tail.

    Unclosed matters: thinking models can burn all tokens before emitting
    ``</think>``. Without this, TTS would speak the reasoning.
    """
    if not text:
        return text
    text = _THINK_CLOSED.sub("", text)
    text = _THINK_UNCLOSED.sub("", text)
    return text


def clean_llm_response(text: str) -> str:
    """MVP cleanup for speak-ready text: scrub reasoning + fences, then trim."""
    if not text:
        return ""
    text = strip_think_tags(text)
    text = _CODE_FENCE_OPEN.sub("", text)
    text = text.replace("```", "")
    return text.strip()
