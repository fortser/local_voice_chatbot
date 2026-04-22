"""Command registry — a name→instance map, plus a default-registry factory.

Threading: the registry is built once at startup and treated as read-only at
runtime (M9 may add LLM-resolved aliases, but those will go through a
separate code path). No locking required for lookups.
"""

from __future__ import annotations

import logging
from typing import Iterable, Iterator

from commands.base import BaseCommand

logger = logging.getLogger(__name__)


class CommandRegistry:
    """Holds command instances keyed by their canonical ``name``."""

    def __init__(self, commands: Iterable[BaseCommand] = ()) -> None:
        self._by_name: dict[str, BaseCommand] = {}
        for cmd in commands:
            self.register(cmd)

    def register(self, command: BaseCommand) -> None:
        if not command.name:
            raise ValueError(f"Command {type(command).__name__} has empty name")
        if command.name in self._by_name:
            raise ValueError(f"Duplicate command name: {command.name!r}")
        # Жёсткое требование: каждый синоним — минимум 2 слова. Однословные
        # триггеры ловят шум Whisper'а — это решено осознанно, см.
        # feedback memory `feedback_two_word_commands`.
        if not command.synonyms:
            raise ValueError(f"Command {command.name!r} has no synonyms")
        for syn in command.synonyms:
            if not syn or len(syn.split()) < 2:
                raise ValueError(
                    f"Command {command.name!r}: synonym {syn!r} must contain "
                    f"at least 2 words (one-word triggers cause false matches)"
                )
        self._by_name[command.name] = command

    def get(self, name: str) -> BaseCommand | None:
        return self._by_name.get(name)

    def __iter__(self) -> Iterator[BaseCommand]:
        return iter(self._by_name.values())

    def __len__(self) -> int:
        return len(self._by_name)

    def names(self) -> list[str]:
        return list(self._by_name.keys())


def build_default_registry() -> CommandRegistry:
    """Construct the registry with all M1 stub commands.

    Imported lazily inside the function so a test importing only
    :class:`CommandRegistry` doesn't pay for the full command tree.
    """
    from commands.note_command import NoteCommand
    from commands.player_commands import (
        MuteCommand,
        PauseCommand,
        ResumeCommand,
        UnmuteCommand,
        VolumeDownCommand,
        VolumeUpCommand,
    )
    from commands.question_command import QuestionCommand
    from commands.screenshot_command import ScreenshotCommand
    from commands.stubs import (
        CancelCommand,
        SeekBackwardCommand,
        SeekForwardCommand,
        StopCommand,
    )

    registry = CommandRegistry(
        [
            # GLOBAL first — semantic priority, not lookup order.
            StopCommand(),
            CancelCommand(),
            # INSTANT
            PauseCommand(),
            ResumeCommand(),
            VolumeUpCommand(),
            VolumeDownCommand(),
            MuteCommand(),
            UnmuteCommand(),
            SeekForwardCommand(),
            SeekBackwardCommand(),
            ScreenshotCommand(),
            # CONTENT
            NoteCommand(),
            QuestionCommand(),
        ]
    )
    logger.info("Command registry built: %d commands", len(registry))
    return registry
