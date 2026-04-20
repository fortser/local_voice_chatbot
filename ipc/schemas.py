"""Pydantic schemas for IPC requests and responses.

Request envelope:
    {"id": "<opaque>", "method": "<name>", "params": {...}}

Response envelope (one of):
    {"id": "<echoed>", "status": "ok",    "result": {...}}
    {"id": "<echoed>", "status": "error", "error":  {"code": "...", "message": "..."}}

``id`` is purely an echo tag for the caller — the server doesn't interpret it.
Per-method param classes double as documentation: the set of accepted fields
lives in one place, Pydantic rejects unknown keys so typos surface early.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ipc.protocol import ErrorCode

# ---- envelope ----


class RequestEnvelope(BaseModel):
    """Top-level wire request."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class ErrorBody(BaseModel):
    code: ErrorCode
    message: str


class ResponseEnvelope(BaseModel):
    """Top-level wire response. Exactly one of ``result`` / ``error`` is set."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    status: Literal["ok", "error"]
    result: dict[str, Any] | None = None
    error: ErrorBody | None = None


# ---- per-method params ----


class HealthCheckParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GenerateOnlyParams(BaseModel):
    """Run LLM → TTS on a supplied user text."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, description="Prompt to send to the LLM.")
    speak: bool = Field(
        default=True,
        description="If false, skip TTS — returns text only, audio_file is null.",
    )


class TranscribeAndRespondParams(BaseModel):
    """Run STT → LLM → TTS on a pre-recorded WAV."""

    model_config = ConfigDict(extra="forbid")

    audio_file: str = Field(description="Path to a 16 kHz mono PCM16 WAV file.")
    speak: bool = Field(
        default=True,
        description="If false, skip TTS — returns transcription + LLM text only.",
    )


class RecalibrateParams(BaseModel):
    """Re-run the VAD calibration (2 sec of silence expected)."""

    model_config = ConfigDict(extra="forbid")

    duration: float | None = Field(
        default=None,
        gt=0.0,
        le=10.0,
        description="Seconds of silence to sample. Defaults to config.CALIBRATION_DURATION.",
    )


# ---- per-method result shapes (documentation only; server returns plain dicts) ----


class HealthCheckResult(BaseModel):
    stt: dict[str, Any]
    llm: dict[str, Any]
    tts: dict[str, Any]
    audio: dict[str, Any]


class GenerateOnlyResult(BaseModel):
    input_text: str
    output_text: str
    audio_file: str | None
    processing_time: float


class TranscribeAndRespondResult(BaseModel):
    input_text: str
    output_text: str
    audio_file: str | None
    processing_time: float


class RecalibrateResult(BaseModel):
    noise_rms: float
    threshold: float
    duration: float
