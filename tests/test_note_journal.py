"""Monthly persistence and failure recovery, without real screen capture."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pytest
from PIL import Image

import system.session_manager as session_module
from system.session_manager import SessionManager


class ImageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "data-screenshot" in attrs:
            self.paths.append(attrs["href"])
        elif tag == "img" and "src" in attrs:
            self.paths.append(attrs["src"])


@pytest.fixture
def clock(monkeypatch):
    current = [datetime(2026, 10, 31, 23, 59, 59)]
    monkeypatch.setattr(session_module, "datetime", SimpleNamespace(now=lambda: current[0]))
    return current


def test_journal_appends_after_restart_with_unique_images(tmp_path, screenshot_png, clock):
    base = tmp_path / "Заметки с пробелами"
    first = SessionManager(base).save_note_with_screenshot("Первая заметка", screenshot_png)
    second = SessionManager(base).save_note_with_screenshot("Вторая заметка", screenshot_png)
    assert first.html_path == second.html_path == base / "2026-10" / "notes.html"
    assert first.screenshot_path != second.screenshot_path
    assert second.screenshot_path.stem.endswith("_2")
    page = first.html_path.read_text(encoding="utf-8")
    assert page.count('<article class="note">') == 2
    assert page.index("Первая заметка") < page.index("Вторая заметка")
    assert page.count("<!doctype html>") == page.count("</html>") == 1
    assert first.text_path.read_text(encoding="utf-8").count("заметка") == 2
    assert first.screenshot_path.read_bytes() == screenshot_png
    with Image.open(first.thumbnail_path) as thumbnail:
        assert thumbnail.size == (320, 180)
    links = ImageLinks()
    links.feed(page)
    assert len(links.paths) == 4
    assert all((first.html_path.parent / unquote(path)).is_file() for path in links.paths)
    assert all(not Path(path).is_absolute() for path in links.paths)


def test_save_month_is_shared_by_txt_html_and_images(tmp_path, screenshot_png, clock):
    manager = SessionManager(tmp_path)
    first = manager.save_note_with_screenshot("Октябрь", screenshot_png)
    clock[0] = datetime(2026, 11, 1, 0, 0, 1)
    second = manager.save_note_with_screenshot("Ноябрь", screenshot_png,
                                               captured_at=datetime(2026, 10, 31, 23, 59, 50))
    assert first.html_path.parent.name == "2026-10"
    assert second.html_path.parent.name == "2026-11"
    assert second.text_path.parent == second.screenshot_path.parent == second.html_path.parent
    assert "Ноябрь" not in first.html_path.read_text(encoding="utf-8")
    assert "Снимок: 2026-10-31 23:59:50" in second.html_path.read_text(encoding="utf-8")


def test_journal_is_monthly_in_per_session_layout(tmp_path, screenshot_png, clock):
    first = SessionManager(tmp_path, layout="per_session").save_note_with_screenshot("Один", screenshot_png)
    second = SessionManager(tmp_path, layout="per_session").save_note_with_screenshot("Два", screenshot_png)
    assert first.text_path.parent != second.text_path.parent
    assert first.html_path == second.html_path == tmp_path / "2026-10" / "notes.html"


def test_escape_text_and_preserve_line_breaks(tmp_path, clock):
    text = 'Кириллица & <script>alert("x")</script>\n<!-- SHURA:END_ENTRIES -->'
    result = SessionManager(tmp_path).save_note_with_screenshot(text)
    page = result.html_path.read_text(encoding="utf-8")
    assert '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;\n' in page
    assert '<script>alert' not in page
    assert page.count("<!-- SHURA:END_ENTRIES -->") == 1
    assert "Скриншот недоступен" in page
    assert result.warnings


@pytest.mark.parametrize("png", [None, b"broken png"])
def test_missing_or_invalid_image_keeps_text_in_both_formats(tmp_path, clock, png):
    result = SessionManager(tmp_path).save_note_with_screenshot("Важная заметка", png)
    assert "Важная заметка" in result.text_path.read_text(encoding="utf-8")
    assert "Важная заметка" in result.html_path.read_text(encoding="utf-8")
    assert "Скриншот недоступен" in result.html_path.read_text(encoding="utf-8")
    assert result.screenshot_path is None and result.warnings


@pytest.mark.parametrize("failure", ["image", "thumbnail"])
def test_image_write_failure_keeps_note(tmp_path, screenshot_png, monkeypatch, clock, failure):
    if failure == "image":
        def fail_image(*args):
            raise OSError("disk full")

        monkeypatch.setattr(SessionManager, "_save_png_locked", fail_image)
    else:
        original = Path.replace

        def fail_thumbnail(path, target):
            if Path(target).parent.name == "thumbnails":
                raise OSError("disk full")
            return original(path, target)

        monkeypatch.setattr(Path, "replace", fail_thumbnail)
    result = SessionManager(tmp_path).save_note_with_screenshot("Текст сохранён", screenshot_png)
    assert result.text_path.is_file() and result.html_path.is_file()
    assert result.thumbnail_path is None and result.warnings
    assert "Скриншот недоступен" in result.html_path.read_text(encoding="utf-8")


def test_atomic_html_failure_keeps_previous_journal_and_new_txt(tmp_path, screenshot_png, monkeypatch, clock):
    manager = SessionManager(tmp_path)
    first = manager.save_note_with_screenshot("Предыдущая", screenshot_png)
    previous = first.html_path.read_bytes()
    original = Path.replace

    def fail_html(path, target):
        if Path(target).suffix == ".html":
            raise PermissionError("journal locked")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", fail_html)
    result = manager.save_note_with_screenshot("Новая", screenshot_png)
    assert result.html_path is None
    assert first.html_path.read_bytes() == previous
    assert "Новая" in result.text_path.read_text(encoding="utf-8")
    assert any("журнал не обновлён" in warning for warning in result.warnings)
    assert not list(tmp_path.rglob("*.tmp"))


def test_damaged_journal_is_not_overwritten(tmp_path, clock):
    journal = tmp_path / "2026-10" / "notes.html"
    journal.parent.mkdir()
    journal.write_text("Существующие данные", encoding="utf-8")
    result = SessionManager(tmp_path).save_note_with_screenshot("Новая заметка")
    assert result.html_path is None and result.warnings
    assert journal.read_text(encoding="utf-8") == "Существующие данные"


def test_txt_failure_does_not_create_journal_or_images(tmp_path, screenshot_png, clock):
    blocked = tmp_path / "2026-10" / "notes.txt"
    blocked.mkdir(parents=True)
    with pytest.raises(OSError):
        SessionManager(tmp_path).save_note_with_screenshot("Текст", screenshot_png)
    assert not list(tmp_path.rglob("*.html")) and not list(tmp_path.rglob("*.png"))


def test_concurrent_saves_do_not_lose_entries(tmp_path, screenshot_png, clock):
    manager = SessionManager(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda i: manager.save_note_with_screenshot(f"Запись {i}", screenshot_png), range(8)))
    assert not any(result.warnings for result in results)
    page = results[0].html_path.read_text(encoding="utf-8")
    assert page.count('<article class="note">') == 8
    assert len({result.screenshot_path for result in results}) == 8


def test_plain_note_has_no_html_or_images_and_empty_note_creates_nothing(tmp_path, clock):
    manager = SessionManager(tmp_path)
    with pytest.raises(ValueError):
        manager.save_note_with_screenshot("  ")
    assert list(tmp_path.iterdir()) == []
    path = manager.save_note("Обычная заметка")
    assert path.name == "notes.txt"
    assert not list(tmp_path.rglob("*.html")) and not list(tmp_path.rglob("*.png"))
