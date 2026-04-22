"""Command subsystem for the Shurochka assistant.

The router parses post-STT text into a :class:`BaseCommand` and dispatches it.
If no command matches, the caller falls back to the LLM path. See
``MIGRATION_PLAN.md`` (M1) for the design.

Public surface:

* :class:`commands.base.BaseCommand`, :class:`CommandType`,
  :class:`CommandContext` — the ABC and DTOs.
* :class:`commands.registry.CommandRegistry` and
  :func:`build_default_registry` — discovery / wiring of command instances.
* :class:`commands.router.CommandRouter` — text → command dispatch.
"""

from commands.base import BaseCommand, CommandContext, CommandType
from commands.registry import CommandRegistry, build_default_registry
from commands.router import CommandRouter

__all__ = [
    "BaseCommand",
    "CommandContext",
    "CommandType",
    "CommandRegistry",
    "CommandRouter",
    "build_default_registry",
]
