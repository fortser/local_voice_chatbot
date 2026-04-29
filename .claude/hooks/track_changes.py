"""PostToolUse hook: tracks changed .py and .md files for end-of-session reminder."""
import json
import os
import re
import sys

# Файлы, изменения которых не должны триггерить напоминание о CHANGELOG.
SKIP_PATTERNS = [
    "CHANGELOG",
    "PROJECT_INDEX",
    "LLM_report",
    "MIGRATION_PLAN",
    "VOICE_AI_PROJECT_SPECIFICATION",
    "soft-sniffing-allen",
    "README",
    "CLAUDE.md",
    ".claude/projects/",
    "__pycache__",
    "logs/",
    "models/",
]

TMP_FILE = os.path.join(os.environ.get("TEMP", "/tmp"), "claude_shura_changelog_changed.txt")

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

fp = data.get("tool_input", {}).get("file_path", "")
if not fp:
    sys.exit(0)

# Нормализуем разделители для match'а скип-паттернов.
fp_norm = fp.replace("\\", "/")

if any(p in fp_norm for p in SKIP_PATTERNS):
    sys.exit(0)

is_py = bool(re.search(r"\.py$", fp_norm))
is_md = bool(re.search(r"\.md$", fp_norm))

if is_py or is_md:
    with open(TMP_FILE, "a", encoding="utf-8") as f:
        f.write(fp + "\n")
