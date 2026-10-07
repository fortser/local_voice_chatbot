from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import sys

import pytest
from PIL import Image

from commands.base import CommandContext
from commands import subscribe_channel_command as command
from system import youtube_subscription as screen_module
from system.youtube_subscription import Box, BrowserWindow, ScreenControlError, YouTubeScreen, is_yandex_youtube, match_templates

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "youtube_subscription"
FIXTURES = ROOT / "tests" / "fixtures" / "youtube_subscription"
CONTROL = Box(1300, 760, 24, 24)
EXIT = Box(1850, 1030, 24, 24)
BUTTON = Box(375, 850, 118, 36)
SUBSCRIBED = Box(375, 850, 170, 36)


@pytest.fixture
def run_command(monkeypatch):
    backend = MagicMock()
    backend.player_control.return_value = ("enter", CONTROL)
    backend.subscription.return_value = ("subscribed", SUBSCRIBED)
    monkeypatch.setattr(command, "YouTubeScreen", lambda _: backend)
    monkeypatch.setattr(command, "_RETRIES", 2)
    monkeypatch.setattr(command.time, "sleep", lambda _: None)
    pipeline = SimpleNamespace(_play_ack=MagicMock())
    ctx = CommandContext(pipeline=pipeline, full_text="подпишись на канал")
    def run():
        assert command.SubscribeChannelCommand().execute(ctx) is True
        return pipeline._play_ack.call_args.args[0]
    return backend, run


def test_subscribe_once_then_confirm(run_command):
    backend, run = run_command
    backend.subscription.side_effect = [("subscribe", BUTTON), ("subscribe", BUTTON), ("subscribe", BUTTON), ("subscribed", SUBSCRIBED)]
    assert run() == "subscribe_channel_after.wav"
    backend.click.assert_called_once_with(BUTTON)
    backend.restore_cursor.assert_called_once()


def test_already_subscribed_never_clicks(run_command):
    backend, run = run_command
    assert run() == "subscribe_channel_already.wav"
    backend.click.assert_not_called()


def test_not_found_never_clicks(run_command):
    backend, run = run_command
    backend.subscription.return_value = None
    assert run() == "subscribe_channel_not_found.wav"
    backend.click.assert_not_called()


def test_unconfirmed_does_not_repeat_click(run_command):
    backend, run = run_command
    backend.subscription.return_value = ("subscribe", BUTTON)
    assert run() == "subscribe_channel_unconfirmed.wav"
    backend.click.assert_called_once_with(BUTTON)


def test_confirmation_must_be_same_author_row(run_command):
    backend, run = run_command
    backend.subscription.side_effect = [("subscribe", BUTTON), ("subscribe", BUTTON),
                                        ("subscribed", Box(700, 950, 170, 36)), None]
    assert run() == "subscribe_channel_unconfirmed.wav"
    backend.click.assert_called_once()


@pytest.mark.parametrize("result", ["success", "missing", "click_error"])
def test_fullscreen_restored_on_success_and_failure(run_command, result):
    backend, run = run_command
    backend.player_control.side_effect = [("exit", EXIT), ("enter", CONTROL), ("enter", CONTROL), ("exit", EXIT)]
    if result == "success":
        backend.subscription.side_effect = [("subscribe", BUTTON), ("subscribe", BUTTON), ("subscribed", SUBSCRIBED)]
        expected = "after"
    elif result == "missing":
        backend.subscription.return_value = None
        expected = "not_found"
    else:
        backend.subscription.return_value = ("subscribe", BUTTON)
        backend.click.side_effect = [RuntimeError("click failed"), None]
        expected = "unconfirmed"
    assert run() == f"subscribe_channel_{expected}.wav"
    backend.exit_fullscreen.assert_called_once()
    assert backend.click.call_args_list[-1].args == (CONTROL,)
    backend.restore_cursor.assert_called_once()


def test_changed_button_is_not_clicked(run_command):
    backend, run = run_command
    backend.subscription.side_effect = [("subscribe", BUTTON), ("subscribed", SUBSCRIBED)]
    assert run() == "subscribe_channel_fail.wav"
    backend.click.assert_not_called()


def test_cursor_restored_when_fullscreen_restore_fails(run_command):
    backend, run = run_command
    backend.player_control.side_effect = [("exit", EXIT), ("enter", CONTROL), ScreenControlError("ambiguous controls")]
    assert run() == "subscribe_channel_already.wav"
    backend.restore_cursor.assert_called_once()


def test_escape_failure_never_clicks_subscription(run_command):
    backend, run = run_command
    backend.player_control.return_value = ("exit", EXIT)
    backend.exit_fullscreen.side_effect = RuntimeError("input failed")
    assert run() == "subscribe_channel_fail.wav"
    backend.click.assert_not_called()
    backend.restore_cursor.assert_called_once()


def test_focus_change_aborts_and_skips_restoration(run_command):
    backend, run = run_command
    backend.subscription.side_effect = ScreenControlError("focus changed")
    backend.check_target.side_effect = ScreenControlError("focus changed")
    assert run() == "subscribe_channel_fail.wav"
    backend.click.assert_not_called()
    backend.restore_cursor.assert_not_called()


def test_missing_backend_is_handled_without_llm(monkeypatch):
    monkeypatch.setattr(command, "YouTubeScreen", MagicMock(side_effect=ImportError("pyautogui missing")))
    pipeline = SimpleNamespace(_play_ack=MagicMock())
    assert command.SubscribeChannelCommand().execute(CommandContext(pipeline, "подпишись на канал"))
    pipeline._play_ack.assert_called_once_with("subscribe_channel_fail.wav")


def test_failsafe_does_not_move_mouse_again(run_command):
    backend, run = run_command
    class FailSafeException(Exception):
        pass
    backend.move_over_player.side_effect = FailSafeException()
    assert run() == "subscribe_channel_fail.wav"
    backend.restore_cursor.assert_not_called()


def test_busy_command_does_not_touch_screen(run_command):
    backend, run = run_command
    command._SCREEN_LOCK.acquire()
    try:
        assert run() == "subscribe_channel_fail.wav"
        backend.move_over_player.assert_not_called()
    finally:
        command._SCREEN_LOCK.release()


@pytest.fixture
def desktop(monkeypatch):
    window = BrowserWindow(100, 12, "Video - YouTube - Яндекс", r"C:\Users\Example\AppData\Local\Yandex\YandexBrowser\Application\browser.exe", Box(0, 0, 1920, 1080))
    foreground = MagicMock(return_value=window)
    monkeypatch.setattr(screen_module, "foreground_window", foreground)
    gui = MagicMock()
    gui.position.return_value = (123, 456)
    gui.size.return_value = (1920, 1080)
    monkeypatch.setitem(sys.modules, "pyautogui", gui)
    monkeypatch.setattr(screen_module.time, "sleep", lambda _: None)
    return window, foreground, gui


@pytest.mark.parametrize("title,path,valid", [
    ("Video - YouTube", r"C:\Yandex\Application\browser.exe", True),
    ("Video - YouTube", r"C:\Chrome\browser.exe", False),
    ("Other page", r"C:\Yandex\Application\browser.exe", False),
])
def test_browser_identity(title, path, valid):
    assert is_yandex_youtube(BrowserWindow(1, 1, title, path, CONTROL)) is valid


def test_no_templates_does_not_move_or_click(desktop, tmp_path):
    _, _, gui = desktop
    with pytest.raises(ScreenControlError, match="templates"):
        YouTubeScreen(tmp_path)
    gui.click.assert_not_called()
    gui.moveTo.assert_not_called()


def test_switching_window_prevents_click(desktop):
    _, foreground, gui = desktop
    backend = YouTubeScreen(ASSETS)
    foreground.return_value = None
    with pytest.raises(ScreenControlError):
        backend.click(BUTTON)
    gui.click.assert_not_called()
    with pytest.raises(ScreenControlError):
        backend.exit_fullscreen()
    gui.press.assert_not_called()


def test_exit_uses_escape(desktop):
    _, _, gui = desktop
    YouTubeScreen(ASSETS).exit_fullscreen()
    gui.press.assert_called_once_with("esc")
    gui.click.assert_not_called()


def test_secondary_monitor_rejected(desktop):
    window, foreground, gui = desktop
    from dataclasses import replace
    foreground.return_value = replace(window, bounds=Box(1920, 0, 1920, 1080))
    with pytest.raises(ScreenControlError, match="primary monitor"):
        YouTubeScreen(ASSETS)
    gui.click.assert_not_called()


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("state", ["subscribe", "subscribed"])
def test_real_button_reference(theme, state):
    with Image.open(FIXTURES / f"{state}_{theme}.png") as image:
        hits = match_templates(image, sorted(ASSETS.glob(f"{state}_*.png")))
    assert len(hits) == 1
    assert hits[0].top > 800


def test_multiple_matches_rejected_in_author_strip(desktop, monkeypatch):
    _, _, gui = desktop
    gui.screenshot.return_value = Image.new("RGB", (1920, 1080), "white")
    backend = YouTubeScreen(ASSETS)
    monkeypatch.setattr(screen_module, "match_templates", lambda *a, **k: [Box(10, 10, 100, 36), Box(300, 10, 100, 36)])
    with pytest.raises(ScreenControlError, match="Ambiguous subscription"):
        backend.subscription(CONTROL)
    gui.click.assert_not_called()


def test_video_and_sidebar_buttons_are_not_targets(desktop):
    _, _, gui = desktop
    image = Image.new("RGB", (1920, 1080), "white")
    with Image.open(ASSETS / "subscribe_light.png") as button:
        image.paste(button, (300, 300))  # Video content.
        image.paste(button, (1600, 860))  # Suggestions, outside the player width.
    gui.screenshot.return_value = image
    assert YouTubeScreen(ASSETS).subscription(CONTROL) is None


def test_route_and_config():
    from commands.registry import build_configured_registry
    from commands.router import CommandRouter
    registry = build_configured_registry(config_path=ROOT / "config" / "voice_commands.example.toml")
    router = CommandRouter(registry, wake_words=("шурочка",))
    for phrase in ("Шурочка, подпишись на канал", "подпиши меня на канал", "подпишись на этот канал"):
        assert router.parse(phrase)[0].name == "subscribe_channel"
    assert router.parse("подписывайтесь на канал") is None


def test_recorded_button_found_in_author_strip(desktop):
    _, _, gui = desktop
    with Image.open(FIXTURES / "subscribe_light.png") as image:
        gui.screenshot.return_value = image.copy()
    result = YouTubeScreen(ASSETS).subscription(Box(1320, 784, 24, 24))
    assert result is not None and result[0] == "subscribe"


@pytest.mark.parametrize("state,location", [("enter", (1320, 784)), ("exit", (1850, 1030))])
def test_native_player_glyphs(desktop, state, location):
    _, _, gui = desktop
    image = Image.new("RGB", (1920, 1080), "black")
    with Image.open(ASSETS / f"{state}_player.png") as icon:
        image.paste(icon, location)
    gui.screenshot.return_value = image
    result = YouTubeScreen(ASSETS).player_control()
    assert result is not None and result[0] == state
    assert result[1].left == location[0]


def test_tab_change_and_resize_prevent_input(desktop):
    from dataclasses import replace
    window, foreground, gui = desktop
    backend = YouTubeScreen(ASSETS)
    for current in (replace(window, title="Other - YouTube"), replace(window, bounds=Box(0, 0, 1280, 720))):
        foreground.return_value = current
        with pytest.raises(ScreenControlError):
            backend.click(BUTTON)
    gui.click.assert_not_called()


def test_owned_fullscreen_geometry_change(desktop):
    from dataclasses import replace
    window, foreground, _ = desktop
    backend = YouTubeScreen(ASSETS)
    foreground.return_value = replace(window, bounds=Box(100, 80, 1400, 900))
    backend.refresh_geometry()
    backend.check_target()
    assert backend.region == Box(100, 80, 1400, 900)


def test_ack_files_packaged():
    import wave
    from utils.generate_ack_phrases import ACK_PHRASES, _enumerate_targets
    assert len([row for row in _enumerate_targets() if row[0] == "subscribe_channel"]) == 5
    for phase in ACK_PHRASES["subscribe_channel"]:
        with wave.open(str(ROOT / "assets" / "ack" / f"subscribe_channel_{phase}.wav")) as wav:
            assert wav.getnframes() > 0
