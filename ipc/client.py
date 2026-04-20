"""Blocking TCP client for the Voice AI IPC.

Each method opens a fresh connection, sends one request, reads one response,
closes. Matches the server's one-shot handler design — simpler than keeping a
persistent socket around, and an IPC call is rare enough that the connect
overhead (~1 ms on loopback) doesn't matter.

Errors from the server (``status == "error"``) surface as :class:`IPCError`;
the wire ``code`` is available on the exception so callers can switch on it.
"""

from __future__ import annotations

import logging
import socket
import uuid
from typing import Any

from config import IPC_HOST, IPC_PORT
from ipc.protocol import (
    DEFAULT_TIMEOUT,
    ErrorCode,
    ProtocolError,
    recv_line,
    send_line,
)
from utils.errors import IPCError

logger = logging.getLogger(__name__)


class IPCRemoteError(IPCError):
    """Raised when the server replies with ``status == "error"``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class VoiceAIClient:
    """Synchronous client for :class:`ipc.server.VoiceAIServer`.

    Keeps no state between calls. Safe to create once per process and reuse
    across threads (each call opens its own socket), though a single call
    itself is not thread-safe on the same instance — that'd share nothing
    useful anyway.
    """

    def __init__(
        self,
        host: str = IPC_HOST,
        port: int = IPC_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout

    # ---- public API ----

    def health_check(self) -> dict[str, Any]:
        return self._call("health_check", {})

    def generate_only(self, text: str, *, speak: bool = True) -> dict[str, Any]:
        return self._call("generate_only", {"text": text, "speak": speak})

    def transcribe_and_respond(
        self, audio_file: str, *, speak: bool = True
    ) -> dict[str, Any]:
        return self._call(
            "transcribe_and_respond",
            {"audio_file": audio_file, "speak": speak},
        )

    def recalibrate(self, duration: float | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if duration is not None:
            params["duration"] = duration
        return self._call("recalibrate", params)

    # ---- low-level ----

    def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        req_id = uuid.uuid4().hex
        request = {"id": req_id, "method": method, "params": params}

        try:
            with socket.create_connection(
                (self._host, self._port), timeout=self._timeout
            ) as sock:
                sock.settimeout(self._timeout)
                send_line(sock, request)
                reply = recv_line(sock)
        except ConnectionRefusedError as exc:
            raise IPCError(
                f"Voice AI server not listening on {self._host}:{self._port} "
                f"— is main.py running? ({exc})"
            ) from exc
        except ProtocolError as exc:
            raise IPCError(f"Protocol error talking to IPC: {exc}") from exc
        except OSError as exc:
            raise IPCError(f"IPC socket error: {exc}") from exc

        status = reply.get("status")
        if status == "ok":
            return reply.get("result") or {}
        if status == "error":
            err = reply.get("error") or {}
            raise IPCRemoteError(
                code=str(err.get("code", ErrorCode.INTERNAL_ERROR.value)),
                message=str(err.get("message", "(no message)")),
            )
        raise IPCError(f"Server reply has unknown status: {status!r}")


__all__ = ["IPCRemoteError", "VoiceAIClient"]
