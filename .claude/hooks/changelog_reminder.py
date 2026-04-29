"""Stop hook: if .py/.md files were changed during the session, remind about CHANGELOG."""
import json
import os
import sys

TMP_FILE = os.path.join(os.environ.get("TEMP", "/tmp"), "claude_shura_changelog_changed.txt")

if not os.path.exists(TMP_FILE):
    sys.exit(0)

try:
    with open(TMP_FILE, encoding="utf-8") as f:
        raw = f.read().strip().splitlines()
finally:
    try:
        os.remove(TMP_FILE)
    except OSError:
        pass

files = list(dict.fromkeys(raw))  # дедуп с сохранением порядка
if not files:
    sys.exit(0)

short_names = [os.path.basename(p) for p in files]
tail = " и ещё..." if len(short_names) > 8 else ""
names_str = ", ".join(short_names[:8]) + tail

msg = (
    f"CHANGELOG.md / PROJECT_INDEX.md — не забудь обновить (или вызови /update-docs). "
    f"Изменены: {names_str}"
)
print(json.dumps({"systemMessage": msg}))
