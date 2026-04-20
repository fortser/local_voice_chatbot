"""IPC package — exposes server/client entry points for Stage 6.

The wire protocol is a single JSON object per line over TCP (see ``protocol``).
Orchestration (start/stop server, dispatch to pipeline) lives in ``server``;
external apps import ``client.VoiceAIClient``.
"""

from ipc.client import VoiceAIClient
from ipc.protocol import ErrorCode
from ipc.server import VoiceAIServer

__all__ = ["ErrorCode", "VoiceAIClient", "VoiceAIServer"]
