from __future__ import annotations

from pathlib import Path

import pytest

from commands.hint_provider import load_hint_lines
from commands.registry import build_configured_registry, build_default_registry
from commands.voice_config import VoiceCommandConfigError


def _write(path: Path, text: str) -> Path:
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def test_missing_voice_commands_config_keeps_defaults(tmp_path: Path) -> None:
    default = build_default_registry()
    configured = build_configured_registry(config_path=tmp_path / "missing.toml")

    assert configured.names() == default.names()
    assert configured.get("pause").synonyms == default.get("pause").synonyms


def test_extend_synonyms_and_hint_metadata(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path / "voice_commands.toml",
        """
        version = 1

        [commands.pause]
        mode = "extend"
        synonyms = ["поставь фильм на паузу"]
        hint = "моя пауза"
        show_in_hints = true
        order = 1
        """,
    )

    registry = build_configured_registry(config_path=config_path)
    pause = registry.get("pause")

    assert "поставь фильм на паузу" in pause.synonyms
    lines = load_hint_lines(
        registry,
        hints_file=tmp_path / "missing_wake_hints.json",
        max_items=3,
    )
    assert lines[0] == "моя пауза"


def test_replace_synonyms_and_disable_command(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path / "voice_commands.toml",
        """
        version = 1

        [commands.pause]
        mode = "replace"
        synonyms = ["замри видео"]

        [commands.mute]
        enabled = false
        """,
    )

    registry = build_configured_registry(config_path=config_path)

    assert registry.get("pause").synonyms == ("замри видео",)
    assert registry.get("mute") is None


def test_rejects_one_word_synonym(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path / "voice_commands.toml",
        """
        version = 1

        [commands.pause]
        synonyms = ["пауза"]
        """,
    )

    with pytest.raises(VoiceCommandConfigError, match="at least 2 words"):
        build_configured_registry(config_path=config_path)


def test_rejects_cross_command_duplicate(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path / "voice_commands.toml",
        """
        version = 1

        [commands.pause]
        synonyms = ["сними паузу"]
        """,
    )

    with pytest.raises(VoiceCommandConfigError, match="conflicts"):
        build_configured_registry(config_path=config_path)


def test_rejects_unknown_command_name(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path / "voice_commands.toml",
        """
        version = 1

        [commands.unknown_command]
        synonyms = ["какая то команда"]
        """,
    )

    with pytest.raises(VoiceCommandConfigError, match="unknown command"):
        build_configured_registry(config_path=config_path)


def test_protects_global_command_from_disable(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path / "voice_commands.toml",
        """
        version = 1

        [commands.stop]
        enabled = false
        """,
    )

    with pytest.raises(VoiceCommandConfigError, match="GLOBAL"):
        build_configured_registry(config_path=config_path)


def test_toml_hint_metadata_overrides_legacy_wake_hints_json(
    tmp_path: Path,
) -> None:
    config_path = _write(
        tmp_path / "voice_commands.toml",
        """
        version = 1

        [commands.pause]
        hint = "toml пауза"
        show_in_hints = true
        order = 1
        """,
    )
    hints_path = tmp_path / "wake_hints.json"
    hints_path.write_text(
        '{"version": 1, "items": ['
        '{"command": "pause", "label": "json пауза", "show": false, "order": 1}'
        ']}',
        encoding="utf-8",
    )

    registry = build_configured_registry(config_path=config_path)
    lines = load_hint_lines(registry, hints_file=hints_path, max_items=1)

    assert lines == ["toml пауза"]


def test_example_voice_commands_config_is_valid() -> None:
    registry = build_configured_registry(
        config_path=Path("config/voice_commands.example.toml")
    )

    assert registry.get("pause") is not None
    assert registry.get("translate_video") is not None
