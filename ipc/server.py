"""TCP server that exposes :class:`main.VoicePipeline` over line-JSON.

Design:

* ``socketserver.ThreadingTCPServer`` — one thread per connection. Handlers
  serialize on ``pipeline.lock`` so mic/model access never overlaps, but the
  socket-level threading means a slow in-flight turn doesn't block
  ``health_check`` from at least *reaching* the handler (it'll still wait its
  turn on the lock; it just gets its error/response faster).

* Each handler processes **one** request per connection, then closes. Keeps
  the protocol stateless and matches the ``client.py`` one-shot style.

* Errors never propagate to the REPL/stdout of the main process — every
  exception a method raises becomes a structured ``error`` response. Log
  everything at WARNING/EXCEPTION so operators can debug.

The server runs in a background thread (``start()`` / ``stop()``); the owning
process (``main.py``) decides whether to block on a REPL or just wait for
Ctrl+C alongside it.
"""

from __future__ import annotations

import logging
import socket
import socketserver
import threading
import traceback
from typing import TYPE_CHECKING, Any, Callable

from pydantic import ValidationError

from config import IPC_HOST, IPC_PORT
from ipc.protocol import (
    DEFAULT_TIMEOUT,
    ErrorCode,
    ProtocolError,
    recv_line,
    send_line,
)
from ipc.schemas import (
    GenerateOnlyParams,
    HealthCheckParams,
    RecalibrateParams,
    RequestEnvelope,
    TranscribeAndRespondParams,
)
from utils.errors import (
    AudioError,
    ConfigError,
    LLMError,
    STTError,
    TTSError,
    VoiceAIError,
)

if TYPE_CHECKING:
    from main import VoicePipeline

logger = logging.getLogger(__name__)


# ---- exception → error-code mapping ----
# Keep this explicit; a catch-all via isinstance ladders is easier to audit
# than chained except blocks in every handler.
_ERROR_MAP: tuple[tuple[type[BaseException], ErrorCode], ...] = (
    (STTError, ErrorCode.STT_ERROR),
    (LLMError, ErrorCode.LLM_ERROR),
    (TTSError, ErrorCode.TTS_ERROR),
    (AudioError, ErrorCode.AUDIO_ERROR),
    (ConfigError, ErrorCode.CONFIG_ERROR),
    (FileNotFoundError, ErrorCode.FILE_NOT_FOUND),
    (VoiceAIError, ErrorCode.INTERNAL_ERROR),
)


def _classify(exc: BaseException) -> ErrorCode:
    for cls, code in _ERROR_MAP:
        if isinstance(exc, cls):
            return code
    return ErrorCode.INTERNAL_ERROR


# ---- dispatch table ----
# Each entry: (params_model, handler(pipeline, params) -> result_dict).

Handler = Callable[["VoicePipeline", Any], dict[str, Any]]


def _handle_health_check(pipeline: "VoicePipeline", _params: HealthCheckParams) -> dict[str, Any]:
    return pipeline.health_check()


def _handle_generate_only(pipeline: "VoicePipeline", params: GenerateOnlyParams) -> dict[str, Any]:
    return pipeline.generate_text(params.text, speak=params.speak)


def _handle_transcribe_and_respond(
    pipeline: "VoicePipeline", params: TranscribeAndRespondParams
) -> dict[str, Any]:
    return pipeline.transcribe_file(params.audio_file, speak=params.speak)


def _handle_recalibrate(pipeline: "VoicePipeline", params: RecalibrateParams) -> dict[str, Any]:
    return pipeline.recalibrate(params.duration)


_METHODS: dict[str, tuple[type, Handler]] = {
    "health_check": (HealthCheckParams, _handle_health_check),
    "generate_only": (GenerateOnlyParams, _handle_generate_only),
    "transcribe_and_respond": (TranscribeAndRespondParams, _handle_transcribe_and_respond),
    "recalibrate": (RecalibrateParams, _handle_recalibrate),
}


# ---- socketserver wiring ----


class _RequestHandler(socketserver.BaseRequestHandler):
    """One connection, one request, one response. Then close."""

    # These are injected by ``VoiceAIServer`` via the server's attribute bag.
    server: "_Server"  # type: ignore[assignment]

    def handle(self) -> None:  # noqa: C901 — straight-line dispatch, not worth splitting
        sock: socket.socket = self.request
        sock.settimeout(DEFAULT_TIMEOUT)
        pipeline = self.server.pipeline
        req_id: str | None = None

        try:
            try:
                raw = recv_line(sock)
            except ProtocolError as exc:
                logger.warning("Bad frame from %s: %s", self.client_address, exc)
                self._send_error(sock, req_id, ErrorCode.INVALID_REQUEST, str(exc))
                return

            try:
                envelope = RequestEnvelope.model_validate(raw)
            except ValidationError as exc:
                logger.warning("Bad envelope from %s: %s", self.client_address, exc)
                self._send_error(
                    sock,
                    raw.get("id") if isinstance(raw, dict) else None,
                    ErrorCode.INVALID_REQUEST,
                    f"invalid envelope: {exc.errors()[0]['msg'] if exc.errors() else exc}",
                )
                return

            req_id = envelope.id
            method_entry = _METHODS.get(envelope.method)
            if method_entry is None:
                logger.warning(
                    "Unknown method %r from %s", envelope.method, self.client_address
                )
                self._send_error(
                    sock,
                    req_id,
                    ErrorCode.UNKNOWN_METHOD,
                    f"unknown method: {envelope.method!r}. "
                    f"available: {sorted(_METHODS)}",
                )
                return

            params_model, handler = method_entry
            try:
                params = params_model.model_validate(envelope.params)
            except ValidationError as exc:
                logger.warning(
                    "Bad params for %s from %s: %s",
                    envelope.method, self.client_address, exc,
                )
                self._send_error(
                    sock, req_id, ErrorCode.INVALID_REQUEST,
                    f"invalid params: {exc.errors()[0]['msg'] if exc.errors() else exc}",
                )
                return

            logger.info(
                "IPC %s from %s (id=%s)",
                envelope.method, self.client_address, req_id,
            )
            try:
                result = handler(pipeline, params)
            except Exception as exc:  # noqa: BLE001 — convert anything to an error reply
                code = _classify(exc)
                logger.exception(
                    "Handler %s raised %s: %s", envelope.method, type(exc).__name__, exc
                )
                self._send_error(sock, req_id, code, f"{type(exc).__name__}: {exc}")
                return

            send_line(sock, {"id": req_id, "status": "ok", "result": result})
        except ProtocolError as exc:
            # Raised by send_line when the response itself is too big / bad;
            # the client may not get a reply. Log and move on.
            logger.error("Protocol error on send: %s", exc)
        except Exception:  # noqa: BLE001 — last-resort guard so one bad client can't kill the thread
            logger.error(
                "Unhandled exception in IPC handler:\n%s", traceback.format_exc()
            )

    def _send_error(
        self,
        sock: socket.socket,
        req_id: str | None,
        code: ErrorCode,
        message: str,
    ) -> None:
        try:
            send_line(
                sock,
                {
                    "id": req_id,
                    "status": "error",
                    "error": {"code": code.value, "message": message},
                },
            )
        except (ProtocolError, OSError) as exc:
            logger.warning("Couldn't deliver error response: %s", exc)


class _Server(socketserver.ThreadingTCPServer):
    """Stash the pipeline reference on the server so handlers can reach it."""

    # Re-bind the port immediately after a previous process exits — otherwise
    # TIME_WAIT can block restarts for minutes on some OSes.
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        pipeline: "VoicePipeline",
    ) -> None:
        super().__init__(server_address, _RequestHandler)
        self.pipeline = pipeline


class VoiceAIServer:
    """Manages the background TCP server lifetime.

    Typical use::

        server = VoiceAIServer(pipeline)
        server.start()
        try:
            ...  # REPL or .wait()
        finally:
            server.stop()
    """

    def __init__(
        self,
        pipeline: "VoicePipeline",
        host: str = IPC_HOST,
        port: int = IPC_PORT,
    ) -> None:
        self._pipeline = pipeline
        self._host = host
        self._port = port
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        return (self._host, self._port)

    def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("Server already started")
        try:
            self._server = _Server((self._host, self._port), self._pipeline)
        except OSError as exc:
            raise RuntimeError(
                f"Cannot bind IPC on {self._host}:{self._port}: {exc}. "
                "Another instance may be running."
            ) from exc
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="ipc-server",
            daemon=True,
        )
        self._thread.start()
        logger.info("IPC server listening on %s:%d", self._host, self._port)

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is None:
            return
        logger.info("IPC server stopping")
        server.shutdown()
        server.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        logger.info("IPC server stopped")
