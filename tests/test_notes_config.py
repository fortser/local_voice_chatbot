"""Defaults and round trips for the optional monthly journal."""

import pytest
from pydantic import ValidationError

from config_model import Settings, load_settings, save_settings


def test_note_journal_default_and_round_trip(tmp_path):
    settings = Settings()
    assert not settings.notes.html_with_screenshot
    settings.notes.html_with_screenshot = True
    path = tmp_path / "settings.toml"
    save_settings(settings, path)
    assert load_settings(path).notes.html_with_screenshot
    assert "[notes]" in path.read_text(encoding="utf-8")
    settings.notes.html_with_screenshot = False
    save_settings(settings, path)
    assert "[notes]" not in path.read_text(encoding="utf-8")
    assert not load_settings(path).notes.html_with_screenshot


def test_note_settings_reject_unknown_fields():
    with pytest.raises(ValidationError):
        Settings.model_validate({"notes": {"html_with_screenhot": True}})
