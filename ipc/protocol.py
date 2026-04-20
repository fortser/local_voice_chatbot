"""Wire-level framing for the Voice AI IPC.

One request = one JSON object = one line terminated by ``\\n``. Replies use the
same framing. Keeps the server trivially parseable — no length prefixes, no
framing state machine, Wireshark/netcat-friendly for debugging.

Why a ceiling on line size: a buggy or malicious client could stream megabytes
of garbage before the newline and pin the server's memory. ``MAX_LINE_BYTES``
caps a single message at 1 MiB, which is generous for base64-encoded short
audio references or text responses.
"""

from __future__ import annotations

import json
import socket
from enum import Enum
from typing import Any

# Newline-delimited JSON frames. 1 MiB is well past any realistic text/path
# payload but still bounded against unbounded client streams.
MAX_LINE_BYTES = 1 * 1024 * 1024
LINE_DELIMITER = b"\n"

# Default socket timeout for receiving a full line — kept generous so a slow
# LLM turn (thinking model + long prompt) doesn't trip it; IPC clients usually
# care about completion, not latency.
DEFAULT_TIMEOUT = 180.0


class ErrorCode(str, Enum):
    """Server-side error taxonomy. Strings so the wire stays human-readable."""

    INVALID_REQUEST = "INVALID_REQUEST"       # malformed JSON / missing fields
    UNKNOWN_METHOD = "UNKNOWN_METHOD"         # method not registered
    FILE_NOT_FOUND = "FILE_NOT_FOUND"         # audio_file path doesn't exist
    STT_ERROR = "STT_ERROR"
    LLM_ERROR = "LLM_ERROR"
    TTS_ERROR = "TTS_ERROR"
    AUDIO_ERROR = "AUDIO_ERROR"               # mic / stream / VAD
    CONFIG_ERROR = "CONFIG_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"         # everything we didn't anticipate


class ProtocolError(Exception):
    """Raised by the framing layer for malformed or oversized frames."""


def send_line(sock: socket.socket, payload: dict[str, Any]) -> None:
    """Serialize ``payload`` to JSON and send as a single framed line.

    ``ensure_ascii=False`` so Cyrillic stays readable on the wire — the stream
    is UTF-8 end-to-end.
    """
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if LINE_DELIMITER in data:
        # Our framing assumes JSON is flat (no literal newlines); json.dumps
        # without indent honours that by default, but guard anyway.
        raise ProtocolError("Payload contains a literal newline — framing broken")
    if len(data) + 1 > MAX_LINE_BYTES:
        raise ProtocolError(
            f"Payload too large: {len(data)} bytes > {MAX_LINE_BYTES}"
        )
    sock.sendall(data + LINE_DELIMITER)


def recv_line(sock: socket.socket) -> dict[str, Any]:
    """Read one framed JSON line and decode it.

    Blocks until a full line is available. Raises ``ProtocolError`` on bad JSON,
    oversized frames, or a closed connection mid-frame.
    """
    buf = bytearray()
    while True:
        try:
            chunk = sock.recv(4096)
        except socket.timeout as exc:
            raise ProtocolError(f"Timed out waiting for frame: {exc}") from exc
        if not chunk:
            if buf:
                raise ProtocolError(
                    f"Connection closed mid-frame after {len(buf)} bytes"
                )
            raise ProtocolError("Connection closed by peer")
        buf.extend(chunk)
        if len(buf) > MAX_LINE_BYTES:
            raise ProtocolError(
                f"Frame exceeds {MAX_LINE_BYTES} bytes — aborting"
            )
        idx = buf.find(LINE_DELIMITER)
        if idx >= 0:
            line = bytes(buf[:idx])
            # Everything after the newline in the first recv() is a leftover
            # from the next frame; for our one-shot client/handler model we
            # don't expect pipelined frames, but if we see any, flag it.
            leftover = len(buf) - idx - 1
            if leftover:
                raise ProtocolError(
                    f"Extra bytes past frame boundary: {leftover} — "
                    "pipelined requests are not supported"
                )
            break
    try:
        text = line.decode("utf-8")
        return json.loads(text)
    except UnicodeDecodeError as exc:
        raise ProtocolError(f"Frame is not valid UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"Frame is not valid JSON: {exc}") from exc
