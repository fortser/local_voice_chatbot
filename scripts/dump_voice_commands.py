"""Print the effective voice command registry after TOML overlay."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from commands.registry import build_configured_registry  # noqa: E402
from config import VOICE_COMMANDS_FILE  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=VOICE_COMMANDS_FILE,
        help="Path to voice_commands.toml",
    )
    args = parser.parse_args()

    registry = build_configured_registry(config_path=args.config)
    for cmd in registry:
        print(f"{cmd.name} [{cmd.command_type.value}]")
        for syn in cmd.synonyms:
            print(f"  - {syn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
