"""CommandRouter — text → BaseCommand dispatch.

M1 matching strategy (simple, deterministic, debuggable):

1. Normalise input: lowercase, ``ё → е``, strip punctuation, collapse whitespace.
2. Walk all synonyms across all commands sorted by **descending length** —
   longer synonyms win so ``"запиши заметку"`` doesn't get shadowed by
   ``"запиши"``.
3. Match if the normalised text **equals** the synonym, or **starts with**
   ``synonym + " "`` (so ``"пауза"`` matches ``"пауза."`` after normalisation,
   and ``"запиши заметку купить молоко"`` matches the ``"запиши заметку"``
   synonym while leaving the tail for the command to consume from
   ``ctx.full_text``).

GLOBAL commands win ties: if a GLOBAL synonym matches, it's preferred over
INSTANT/CONTENT even when both produce the same matched length. M9 will layer
fuzzy matching and LLM fallback on top of this; the deterministic core stays
intact so behaviour remains predictable in the common case.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

from commands.base import BaseCommand, CommandContext, CommandType
from commands.registry import CommandRegistry

logger = logging.getLogger(__name__)

_PUNCT = re.compile(r"[^\w\s]+", flags=re.UNICODE)
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, strip punctuation, ``ё→е``, collapse whitespace."""
    if not text:
        return ""
    cleaned = text.lower().replace("ё", "е")
    cleaned = _PUNCT.sub(" ", cleaned)
    cleaned = _WS.sub(" ", cleaned).strip()
    return cleaned


def _strip_wake_word(text: str, wake_words: Iterable[str]) -> str:
    """Drop a leading wake-word token if present.

    The wake-word listener already gates activation, but in serial mode (M10)
    or in the console REPL the user may still prefix the command with
    ``"шурочка"``. Stripping it here keeps the synonym tables clean.
    """
    tokens = text.split()
    if not tokens:
        return text
    candidates = {w.lower().replace("ё", "е") for w in wake_words}
    if tokens[0] in candidates:
        return " ".join(tokens[1:])
    return text


class CommandRouter:
    """Parse normalised text into a :class:`BaseCommand`, then dispatch."""

    def __init__(
        self,
        registry: CommandRegistry,
        *,
        wake_words: Iterable[str] = (),
    ) -> None:
        self._registry = registry
        self._wake_words = tuple(wake_words)
        # Pre-compute (synonym, command) pairs sorted by descending length so
        # the parse loop can scan once and pick the longest match.
        pairs: list[tuple[str, BaseCommand]] = []
        for cmd in registry:
            for syn in cmd.synonyms:
                norm_syn = normalize(syn)
                if norm_syn:
                    pairs.append((norm_syn, cmd))
        pairs.sort(key=lambda p: (-len(p[0]), p[0]))
        self._pairs = pairs

    @property
    def registry(self) -> CommandRegistry:
        return self._registry

    def parse(self, text: str) -> tuple[BaseCommand, str] | None:
        """Return ``(command, matched_synonym)`` or ``None`` if no match.

        Tries GLOBAL commands first (so Stop/Cancel always pre-empt), then
        the rest by descending synonym length.
        """
        norm = normalize(text)
        if not norm:
            return None
        norm = _strip_wake_word(norm, self._wake_words)
        if not norm:
            return None

        # GLOBAL pass — exact-or-prefix on global commands only.
        for syn, cmd in self._pairs:
            if cmd.command_type is not CommandType.GLOBAL:
                continue
            if norm == syn or norm.startswith(syn + " "):
                logger.info("Router GLOBAL match: %r → %s (syn=%r)", text, cmd.name, syn)
                return cmd, syn

        # Regular pass — longest match wins (already sorted).
        for syn, cmd in self._pairs:
            if cmd.command_type is CommandType.GLOBAL:
                continue
            if norm == syn or norm.startswith(syn + " "):
                logger.info(
                    "Router match: %r → %s (type=%s, syn=%r)",
                    text, cmd.name, cmd.command_type.value, syn,
                )
                return cmd, syn

        logger.info("Router no-match: %r", text)
        return None

    def dispatch(self, text: str, ctx: CommandContext) -> BaseCommand | None:
        """Parse and execute.

        Возвращает выполнившую команду или ``None``. Имея на руках сам
        объект, вызывающая сторона может проиграть `cmd.ack_after`,
        логировать `cmd.name` и т.п. без повторного парса.

        Если ``cmd.execute(ctx)`` вернул ``False`` (отказ — например, нет
        подсистемы) или бросил исключение, возвращаем ``None``: для
        вызывающего «команда не отработала», поведение симметрично с
        no-match.
        """
        match = self.parse(text)
        if match is None:
            return None
        cmd, syn = match
        ctx.full_text = text
        ctx.matched_synonym = syn
        try:
            ok = bool(cmd.execute(ctx))
        except Exception:
            logger.exception("Command %s raised", cmd.name)
            return None
        return cmd if ok else None
