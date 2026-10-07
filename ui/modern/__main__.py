"""Standalone launch keeps the preview independent of audio/ML imports."""

import argparse

from .app import run_ui_modern


def main() -> int:
    parser = argparse.ArgumentParser(description="Шурочка — новый интерфейс")
    parser.add_argument("--preview", action="store_true", help="Открыть только интерфейс, без микрофона и моделей")
    parser.add_argument("--no-ipc", action="store_true")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    options = {"preview": args.preview, "with_ipc": not args.no_ipc}
    if not args.preview:
        from config import IPC_HOST, IPC_PORT
        options.update(ipc_host=args.host or IPC_HOST, ipc_port=args.port if args.port is not None else IPC_PORT)
    return run_ui_modern(**options)


if __name__ == "__main__":
    raise SystemExit(main())
