"""Prompt / response text utilities.

Two jobs:

* **Scrub reasoning chains** before the text reaches TTS. Old thinking models
  wrapped reasoning in ``<think>...</think>``. Newer ones (harmony / gpt-oss
  style: ``<|channel|>analysis...<|channel|>final``, or freeform
  ``Thinking Process:`` headers followed by numbered self-analysis) do not —
  if we only strip ``<think>`` tags, Silero happily narrates the whole
  reasoning trace at the user (in English, to boot).

* **Detect thinking output** from a raw response so ``LLMProvider`` can mark
  the model as "needs thinking-sized token budget" without a hardcoded name
  list. Pattern-based autodetection replaces a flaky ``THINKING_MODEL_PATTERNS``
  substring check; the moment a model emits any thinking marker, future calls
  get the 3× ``max_tokens``/``timeout`` multiplier so it has room to finish
  reasoning and produce the final answer.
"""

from __future__ import annotations

import re

_THINK_CLOSED = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_UNCLOSED = re.compile(r"<think>.*\Z", re.DOTALL | re.IGNORECASE)

# Harmony / gpt-oss channel markers. Accept both ``<|channel|>`` and the
# single-pipe ``<|channel>`` variants seen in the wild.
_HARMONY_ANALYSIS_BLOCK = re.compile(
    r"<\|channel\|?>\s*(?:analysis|thought|thinking|reasoning)\b"
    r".*?"
    r"(?=<\|channel\|?>\s*(?:final|message|answer|response)\b|\Z)",
    re.DOTALL | re.IGNORECASE,
)

# Generic harmony control tokens to drop once analysis blocks are gone — e.g.
# ``<|channel|>final<|message|>`` or leftover ``<|end|>``.
_HARMONY_MARKER = re.compile(r"<\|[a-z][a-z_]*\|?>", re.IGNORECASE)

# "Thinking Process:" / "Here's a thinking process" / "Analysis:" preamble.
# These models emit freeform reasoning (numbered list, drafts, self-critique)
# before — sometimes — finally writing the real Russian answer. Strip the
# whole preamble up to a blank-line boundary followed by Cyrillic text (the
# real answer) or, failing that, up to EOS.
_THINKING_PROSE_SECTION = re.compile(
    r"(?:^|\n)\s*(?:here['']?s\s+(?:a|my|the)\s+)?"
    r"(?:thinking\s*process|analysis|reasoning|chain[-\s]of[-\s]thought)"
    r"\s*:?\s*\n"
    r".*?"
    r"(?=\n\s*\n\s*[А-ЯЁ][а-яё]|\n\s*(?:final|итог)[^:\n]*:\s*|\Z)",
    re.DOTALL | re.IGNORECASE,
)

# Residual draft labels ("Draft 1:", "Final version:", "Final answer:").
_DRAFT_LABEL = re.compile(
    r"^\s*(?:final\s+(?:version|answer|response|draft|russian[^:\n]*)"
    r"|draft\s*\d+|итоговый\s+ответ)\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)

# Fenced code blocks read terribly through TTS; strip the fence markers but
# keep the code text itself so the user still hears what was generated.
_CODE_FENCE_OPEN = re.compile(r"```[a-zA-Z0-9_+\-]*\n?")

# Anything that unambiguously says "this output is a thinking trace". Used by
# ``detect_thinking_markers`` — checked against just the head of the output
# because these markers always appear at the very top of a thinking response.
_THINKING_INDICATORS = re.compile(
    r"<\|(?:channel|analysis|reasoning|thinking|thought)\b"
    r"|<think\b"
    r"|(?:^|\n)\s*(?:here['']?s\s+(?:a|my|the)\s+)?"
    r"(?:thinking\s*process|chain[-\s]of[-\s]thought)\s*:"
    r"|(?:^|\n)\s*\*?\s*(?:analysis|reasoning)\s*:",
    re.IGNORECASE,
)


def strip_think_tags(text: str) -> str:
    """Remove ``<think>...</think>`` blocks (closed) and any unclosed tail."""
    if not text:
        return text
    text = _THINK_CLOSED.sub("", text)
    text = _THINK_UNCLOSED.sub("", text)
    return text


def strip_thinking_chains(text: str) -> str:
    """Strip harmony-channel analysis blocks and ``Thinking Process:`` prose.

    Runs *after* ``strip_think_tags`` — handles the newer, tag-less formats.
    If the model never emitted a final channel / Cyrillic answer (e.g. it
    ran out of tokens mid-reasoning), the whole thinking tail is dropped so
    TTS doesn't speak English reasoning; the empty result then falls through
    to the ``FALLBACK_EMPTY_LLM`` path in ``VoicePipeline``.
    """
    if not text:
        return text
    text = _HARMONY_ANALYSIS_BLOCK.sub("", text)
    text = _THINKING_PROSE_SECTION.sub("", text)
    text = _HARMONY_MARKER.sub("", text)
    text = _DRAFT_LABEL.sub("", text)
    return text


def detect_thinking_markers(text: str) -> bool:
    """True if the raw LLM output looks like it contains a reasoning trace.

    Used by warmup to auto-flag a model as thinking without hardcoding its
    name — the moment we see a harmony channel or a ``Thinking Process:``
    header, the provider gets to bump ``max_tokens``/``timeout`` ×3 on
    future calls so the reasoning has room to complete.
    """
    if not text:
        return False
    # Markers always appear at the top of the response; restrict the scan so
    # we don't false-positive on a mention deep in prose.
    return bool(_THINKING_INDICATORS.search(text[:500]))


def clean_llm_response(text: str) -> str:
    """MVP cleanup for speak-ready text: scrub reasoning + fences, then trim."""
    if not text:
        return ""
    text = strip_think_tags(text)
    text = strip_thinking_chains(text)
    text = _CODE_FENCE_OPEN.sub("", text)
    text = text.replace("```", "")
    return text.strip()
