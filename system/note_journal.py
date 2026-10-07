"""Offline HTML rendering for the monthly note journal."""

from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from PIL import Image

from utils.file_io import atomic_write_bytes

JOURNAL_FILE = "notes.html"
_END_ENTRIES = "<!-- SHURA:END_ENTRIES -->"

_PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Заметки — MONTH</title>
<style>
* { box-sizing: border-box; }
body { margin: 0; background: #f3f5f7; color: #202932; font: 16px/1.6 system-ui, sans-serif; }
main { max-width: 1050px; margin: auto; padding: 28px 20px; }
h1 { margin: 0 0 8px; font-size: 28px; }
.intro, time, .missing { color: #586774; }
.note { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 24px;
        background: white; padding: 24px; margin: 20px 0; border-radius: 12px;
        box-shadow: 0 2px 8px #2030400c; }
.text { white-space: pre-wrap; overflow-wrap: anywhere; margin-top: 12px; }
.screenshot { display: block; align-self: center; }
.screenshot img { display: block; width: auto; max-width: 100%; height: auto; border-radius: 6px; }
.capture { display: block; font-size: 12px; margin-top: 5px; }
dialog { width: 94vw; max-width: 1600px; max-height: 94vh; padding: 18px;
         border: 0; border-radius: 12px; color: #202932; }
dialog::backdrop { background: #000b; }
.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 12px; }
.toolbar strong { flex: 1; }
button { font: inherit; cursor: pointer; padding: 6px 14px; border: 1px solid #9aabb8;
         border-radius: 6px; background: #f3f5f7; }
.viewer { overflow: auto; max-height: 75vh; }
.viewer img { display: block; margin: auto; max-width: 100%; max-height: 75vh; width: auto; height: auto; }
.viewer.native img { max-width: none; max-height: none; margin: 0; }
@media (max-width: 650px) { .note { grid-template-columns: minmax(0, 1fr); gap: 16px; padding: 18px; } }
</style>
</head>
<body>
<main>
<h1>Заметки — MONTH</h1>
<p class="intro">Нажмите на миниатюру, чтобы открыть полный снимок экрана.</p>
<!-- SHURA:END_ENTRIES -->
</main>
<dialog aria-labelledby="viewer-title">
<div class="toolbar">
<strong id="viewer-title">Снимок экрана</strong>
<button type="button" id="zoom" aria-pressed="false">Масштаб 100%</button>
<button type="button" id="close">Закрыть</button>
</div>
<div class="viewer"><img alt="Полный снимок экрана"></div>
</dialog>
<script>
const dialog = document.querySelector('dialog');
const viewer = document.querySelector('.viewer');
const fullImage = viewer.querySelector('img');
const zoom = document.getElementById('zoom');
document.addEventListener('click', event => {
  const link = event.target.closest('a[data-screenshot]');
  if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
  event.preventDefault();
  fullImage.src = link.href;
  dialog.showModal();
});
document.getElementById('close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
zoom.addEventListener('click', () => {
  const native = viewer.classList.toggle('native');
  zoom.setAttribute('aria-pressed', String(native));
  zoom.textContent = native ? 'Вписать в окно' : 'Масштаб 100%';
});
dialog.addEventListener('close', () => {
  viewer.classList.remove('native');
  viewer.scrollTo(0, 0);
  zoom.setAttribute('aria-pressed', 'false');
  zoom.textContent = 'Масштаб 100%';
  fullImage.removeAttribute('src');
});
</script>
</body>
</html>
"""


def make_thumbnail(png_data: bytes) -> bytes:
    with Image.open(BytesIO(png_data)) as source:
        source.thumbnail((320, 180), Image.Resampling.LANCZOS)
        output = BytesIO()
        source.save(output, format="PNG")
        return output.getvalue()


def append_entry(path: Path, text: str, stamp: str, *, saved_at: datetime,
                 screenshot: Path | None = None, thumbnail: Path | None = None,
                 captured_at: datetime | None = None) -> None:
    """Keep a complete HTML document and never replace a damaged journal."""
    if path.exists():
        page = path.read_text(encoding="utf-8")
    else:
        page = _PAGE.replace("MONTH", saved_at.strftime("%Y-%m"))
    if page.count(_END_ENTRIES) != 1:
        raise ValueError("В HTML-журнале отсутствует маркер добавления заметок")
    visual = '<p class="missing">Скриншот недоступен</p>'
    if screenshot is not None and thumbnail is not None:
        original_url = escape(quote(screenshot.relative_to(path.parent).as_posix()), quote=True)
        thumb_url = escape(quote(thumbnail.relative_to(path.parent).as_posix()), quote=True)
        visual = (f'<a class="screenshot" data-screenshot href="{original_url}" '
                  f'target="_blank" rel="noopener"><img src="{thumb_url}" '
                  'alt="Миниатюра снимка экрана" loading="lazy"></a>')
        if captured_at is not None:
            visual = (f'<div>{visual}<time class="capture" '
                      f'datetime="{captured_at.isoformat()}">'
                      f'Снимок: {captured_at:%Y-%m-%d %H:%M:%S}</time></div>')
    entry = (f'<article class="note"><div><time datetime="{saved_at.isoformat()}">'
             f'{escape(stamp)}</time><div class="text">{escape(text)}</div></div>'
             f'{visual}</article>\n')
    page = page.replace(_END_ENTRIES, entry + _END_ENTRIES)
    atomic_write_bytes(path, page.encode("utf-8"))
