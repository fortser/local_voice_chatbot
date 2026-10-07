"""Note command screenshot timing, settings snapshots, and cancellation."""

from unittest.mock import Mock

import pytest

from commands.base import CommandContext
from commands.note_command import NoteCommand
from config import settings
from system.session_manager import SessionManager
from utils.errors import CancelledError, STTError


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.notes, "html_with_screenshot", True)
    return CommandContext(pipeline=Mock(), full_text="запиши заметку",
                          matched_synonym="запиши заметку",
                          session_manager=SessionManager(tmp_path), ui_callback=Mock())


@pytest.mark.parametrize("inline", [True, False])
def test_capture_before_dictation_and_save_both_formats(context, screenshot_png, monkeypatch, tmp_path, inline):
    events = []

    def capture():
        events.append("capture")
        assert not list(tmp_path.iterdir())
        return screenshot_png

    def dictate(**kwargs):
        events.append("dictate")
        assert events[0] == "capture"
        assert not list(tmp_path.iterdir())
        return "Текст важной новой заметки"

    monkeypatch.setattr("commands.note_command.take_screenshot", capture)
    context.pipeline.dictate.side_effect = dictate
    if inline:
        context.full_text += " текст важной новой заметки"
    assert NoteCommand().execute(context)
    assert events == (["capture"] if inline else ["capture", "dictate"])
    assert len(list(tmp_path.rglob("notes.html"))) == 1
    assert len(list(tmp_path.rglob("notes.txt"))) == 1
    assert len(list(tmp_path.rglob("*.png"))) == 2
    context.pipeline._play_ack.assert_called_once_with(NoteCommand.NOTE_SAVED_ACK)
    context.ui_callback.assert_not_called()


@pytest.mark.parametrize("outcome", ["", "   ", STTError("bad speech"), CancelledError("cancel")])
def test_no_files_on_empty_cancelled_or_failed_dictation(context, screenshot_png, monkeypatch, tmp_path, outcome):
    capture = Mock(return_value=screenshot_png)
    monkeypatch.setattr("commands.note_command.take_screenshot", capture)
    if isinstance(outcome, Exception):
        context.pipeline.dictate.side_effect = outcome
    else:
        context.pipeline.dictate.return_value = outcome
    assert NoteCommand().execute(context)
    capture.assert_called_once()
    assert list(tmp_path.iterdir()) == []
    context.pipeline._play_ack.assert_not_called()


def test_disabled_setting_does_not_capture(context, monkeypatch, tmp_path):
    monkeypatch.setattr(settings.notes, "html_with_screenshot", False)
    capture = Mock()
    monkeypatch.setattr("commands.note_command.take_screenshot", capture)
    context.pipeline.dictate.return_value = "Обычная заметка"
    assert NoteCommand().execute(context)
    capture.assert_not_called()
    assert len(list(tmp_path.rglob("notes.txt"))) == 1
    assert not list(tmp_path.rglob("notes.html"))


def test_toggle_during_dictation_affects_only_next_note(context, screenshot_png, monkeypatch, tmp_path):
    capture = Mock(return_value=screenshot_png)
    monkeypatch.setattr("commands.note_command.take_screenshot", capture)

    def dictate(**kwargs):
        settings.notes.html_with_screenshot = False
        return "Заметка при переключении"

    context.pipeline.dictate.side_effect = dictate
    assert NoteCommand().execute(context)
    assert NoteCommand().execute(context)
    capture.assert_called_once()
    page = next(tmp_path.rglob("notes.html")).read_text(encoding="utf-8")
    assert page.count('<article class="note">') == 1
    assert next(tmp_path.rglob("notes.txt")).read_text(encoding="utf-8").count("Заметка") == 2


def test_capture_failure_preserves_text_and_notifies(context, monkeypatch, tmp_path):
    monkeypatch.setattr("commands.note_command.take_screenshot", Mock(side_effect=OSError("capture failed")))
    context.pipeline.dictate.return_value = "Текст без снимка"
    assert NoteCommand().execute(context)
    assert "Текст без снимка" in next(tmp_path.rglob("notes.html")).read_text(encoding="utf-8")
    assert context.ui_callback.call_args.args[0] == "note_warning"
    assert "скриншот недоступен" in context.ui_callback.call_args.args[1]["message"]
    context.pipeline._play_ack.assert_called_once()


def test_text_write_failure_never_confirms_save(context, screenshot_png, monkeypatch):
    monkeypatch.setattr("commands.note_command.take_screenshot", Mock(return_value=screenshot_png))
    context.pipeline.dictate.return_value = "Не удалось записать"
    context.session_manager.save_note_with_screenshot = Mock(side_effect=PermissionError("read only"))
    assert NoteCommand().execute(context)
    context.pipeline._play_ack.assert_not_called()
    context.pipeline._speak_safely.assert_called_once_with("Не удалось сохранить заметку.")
    context.ui_callback.assert_called_once()
