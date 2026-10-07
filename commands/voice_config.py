"""User-editable voice command overlay.

The executable command behavior stays in Python command classes. This module
loads an optional TOML overlay that can extend/replace synonyms, disable
commands, and provide wake-hint metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

try:  # Python 3.11+
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from commands.base import BaseCommand, CommandType
from commands.router import normalize


class VoiceCommandConfigError(ValueError):
    """Raised when the voice command overlay is invalid."""


class CommandOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    mode: Literal["extend", "replace"] = "extend"
    synonyms: list[str] = Field(default_factory=list)
    hint: str | None = None
    show_in_hints: bool | None = None
    order: int | None = None


class VoiceCommandsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    commands: dict[str, CommandOverride] = Field(default_factory=dict)


@dataclass(frozen=True)
class VoiceCommandConfigResult:
    path: Path
    applied: bool
    changed_commands: tuple[str, ...] = ()
    disabled_commands: tuple[str, ...] = ()
    user_synonym_count: int = 0


def load_voice_commands_config(path: Path | str) -> VoiceCommandsConfig | None:
    """Load TOML config or return None when the file does not exist."""
    path = Path(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except tomllib.TOMLDecodeError as exc:
        raise VoiceCommandConfigError(f"{path}: TOML parse error: {exc}") from exc
    except OSError as exc:
        raise VoiceCommandConfigError(f"{path}: cannot read file: {exc}") from exc
    try:
        config = VoiceCommandsConfig.model_validate(raw)
    except ValidationError as exc:
        raise VoiceCommandConfigError(f"{path}: invalid schema: {exc}") from exc
    if config.version != 1:
        raise VoiceCommandConfigError(
            f"{path}: unsupported version {config.version!r}; expected 1"
        )
    return config


def apply_voice_commands_config(
    commands: Sequence[BaseCommand],
    *,
    config_path: Path | str,
    allow_disable_global: bool = False,
) -> tuple[list[BaseCommand], VoiceCommandConfigResult]:
    """Apply user TOML overlay to command instances and return active commands."""
    path = Path(config_path)
    config = load_voice_commands_config(path)
    if config is None:
        return list(commands), VoiceCommandConfigResult(path=path, applied=False)

    by_name = {cmd.name: cmd for cmd in commands}
    changed: list[str] = []
    disabled: list[str] = []
    user_synonym_count = 0

    for name in config.commands:
        if name not in by_name:
            raise VoiceCommandConfigError(
                f"{path}: unknown command {name!r}; expected one of "
                f"{', '.join(sorted(by_name))}"
            )

    active: list[BaseCommand] = []
    for cmd in commands:
        override = config.commands.get(cmd.name)
        if override is None:
            active.append(cmd)
            continue

        if not override.enabled:
            if cmd.command_type is CommandType.GLOBAL and not allow_disable_global:
                raise VoiceCommandConfigError(
                    f"{path}: command {cmd.name!r} is GLOBAL and cannot be "
                    "disabled unless commands.allow_disable_global=true"
                )
            disabled.append(cmd.name)
            changed.append(cmd.name)
            continue

        synonyms = _merge_synonyms(cmd, override, path)
        cmd.synonyms = tuple(synonyms)
        _apply_hint_metadata(cmd, override)
        active.append(cmd)
        if _override_changes_runtime(override):
            changed.append(cmd.name)
        user_synonym_count += len(override.synonyms)

    _validate_no_cross_command_duplicates(active, path)
    return active, VoiceCommandConfigResult(
        path=path,
        applied=True,
        changed_commands=tuple(changed),
        disabled_commands=tuple(disabled),
        user_synonym_count=user_synonym_count,
    )


def _merge_synonyms(
    cmd: BaseCommand,
    override: CommandOverride,
    path: Path,
) -> list[str]:
    base = [] if override.mode == "replace" else list(cmd.synonyms)
    merged = [*base, *override.synonyms]
    if not merged:
        raise VoiceCommandConfigError(
            f"{path}: command {cmd.name!r} has no synonyms after {override.mode}"
        )

    out: list[str] = []
    seen: dict[str, str] = {}
    for syn in merged:
        if not isinstance(syn, str) or not syn.strip():
            raise VoiceCommandConfigError(
                f"{path}: command {cmd.name!r} has an empty synonym"
            )
        normalized = normalize(syn)
        if len(normalized.split()) < 2:
            raise VoiceCommandConfigError(
                f"{path}: command {cmd.name!r}: synonym {syn!r} must contain "
                "at least 2 words"
            )
        if normalized in seen:
            raise VoiceCommandConfigError(
                f"{path}: command {cmd.name!r}: duplicate synonym {syn!r} "
                f"conflicts with {seen[normalized]!r}"
            )
        seen[normalized] = syn
        out.append(syn.strip())
    return out


def _apply_hint_metadata(cmd: BaseCommand, override: CommandOverride) -> None:
    if override.hint is not None:
        hint = override.hint.strip()
        if hint:
            setattr(cmd, "_hint_label", hint)
    if override.show_in_hints is not None:
        setattr(cmd, "_hint_show", bool(override.show_in_hints))
    if override.order is not None:
        setattr(cmd, "_hint_order", int(override.order))


def _override_changes_runtime(override: CommandOverride) -> bool:
    return (
        override.mode != "extend"
        or bool(override.synonyms)
        or override.hint is not None
        or override.show_in_hints is not None
        or override.order is not None
    )


def _validate_no_cross_command_duplicates(
    commands: Sequence[BaseCommand],
    path: Path,
) -> None:
    seen: dict[str, tuple[str, str]] = {}
    for cmd in commands:
        for syn in cmd.synonyms:
            normalized = normalize(syn)
            if normalized in seen:
                other_cmd, other_syn = seen[normalized]
                raise VoiceCommandConfigError(
                    f"{path}: synonym {syn!r} for command {cmd.name!r} "
                    f"conflicts with {other_syn!r} from command {other_cmd!r}"
                )
            seen[normalized] = (cmd.name, syn)


__all__ = [
    "CommandOverride",
    "VoiceCommandConfigError",
    "VoiceCommandConfigResult",
    "VoiceCommandsConfig",
    "apply_voice_commands_config",
    "load_voice_commands_config",
]
