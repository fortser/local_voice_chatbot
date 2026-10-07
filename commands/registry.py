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


def _default_commands() -> list[BaseCommand]:
    """Instantiate all built-in command handlers.

    Imported lazily inside the function so a test importing only
    :class:`CommandRegistry` doesn't pay for the full command tree.
    """
    from commands.list_reminders_command import ListRemindersCommand
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
    from commands.reminder_command import ReminderCommand
    from commands.screenshot_command import ScreenshotCommand
    from commands.translate_video_command import TranslateVideoCommand
    from commands.subscribe_channel_command import SubscribeChannelCommand
    from commands.stubs import (
        SeekBackwardCommand,
        SeekForwardCommand,
        SkipBackwardCommand,
        SkipForwardCommand,
        StopCommand,
    )

    return [
        # GLOBAL first — semantic priority, not lookup order.
        # Cancel не голосовой (M6) — Esc в UI: `pipeline.request_cancel()`.
        StopCommand(),
        # INSTANT
        PauseCommand(),
        ResumeCommand(),
        VolumeUpCommand(),
        VolumeDownCommand(),
        MuteCommand(),
        UnmuteCommand(),
        SeekForwardCommand(),
        SeekBackwardCommand(),
        SkipForwardCommand(),
        SkipBackwardCommand(),
        ScreenshotCommand(),
        TranslateVideoCommand(),
        SubscribeChannelCommand(),
        # CONTENT
        NoteCommand(),
        QuestionCommand(),
        # Reminder — CONTENT, но парсит хвост regex'ом внутри execute().
        ReminderCommand(),
        ListRemindersCommand(),
    ]


def build_default_registry() -> CommandRegistry:
    """Construct the built-in registry without user voice-command config."""
    registry = CommandRegistry(_default_commands())
    logger.info("Command registry built: %d commands", len(registry))
    return registry


def build_configured_registry(
    *,
    config_path=None,
    strict: bool | None = None,
    allow_disable_global: bool | None = None,
) -> CommandRegistry:
    """Construct the registry and apply optional user TOML command overlay."""
    from config import (
        COMMANDS_ALLOW_DISABLE_GLOBAL,
        COMMANDS_STRICT_CONFIG,
        VOICE_COMMANDS_FILE,
    )
    from commands.voice_config import (
        VoiceCommandConfigError,
        apply_voice_commands_config,
    )

    path = config_path if config_path is not None else VOICE_COMMANDS_FILE
    strict_mode = COMMANDS_STRICT_CONFIG if strict is None else strict
    allow_global = (
        COMMANDS_ALLOW_DISABLE_GLOBAL
        if allow_disable_global is None
        else allow_disable_global
    )
    commands = _default_commands()
    try:
        commands, result = apply_voice_commands_config(
            commands,
            config_path=path,
            allow_disable_global=allow_global,
        )
    except VoiceCommandConfigError:
        if strict_mode:
            raise
        logger.exception(
            "Voice command config is invalid; falling back to built-in commands"
        )
        commands = _default_commands()
    else:
        if result.applied:
            logger.info(
                "Voice command config applied: path=%s changed=%s disabled=%s "
                "user_synonyms=%d",
                result.path,
                list(result.changed_commands),
                list(result.disabled_commands),
                result.user_synonym_count,
            )

    registry = CommandRegistry(commands)
    logger.info("Configured command registry built: %d commands", len(registry))
    return registry
