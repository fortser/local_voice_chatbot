"""Validate config/voice_commands.toml without starting the assistant."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from commands.registry import build_configured_registry  # noqa: E402
from commands.voice_config import VoiceCommandConfigError  # noqa: E402
from config import VOICE_COMMANDS_FILE  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=VOICE_COMMANDS_FILE,
        help="Path to voice_commands.toml",
    )
    parser.add_argument(
        "--allow-disable-global",
        action="store_true",
        help="Allow disabling GLOBAL commands during validation",
    )
    args = parser.parse_args()

    try:
        registry = build_configured_registry(
            config_path=args.path,
            strict=True,
            allow_disable_global=args.allow_disable_global,
        )
    except VoiceCommandConfigError as exc:
        print(f"ERROR: {exc}")
        return 1

    synonym_count = sum(len(cmd.synonyms) for cmd in registry)
    print(
        f"OK: {args.path} -> {len(registry)} commands, "
        f"{synonym_count} synonyms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
