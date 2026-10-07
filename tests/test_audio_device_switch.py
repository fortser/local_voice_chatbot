"""Audio switching contracts; Windows defaults and audio streams are mocked."""

from contextlib import nullcontext
from copy import deepcopy
from enum import Enum
from types import SimpleNamespace
from unittest.mock import Mock
import sys
import threading

import pytest

from system.audio_devices import WindowsAudioDevices, default_endpoints, resolve_wasapi_devices
from utils.audio_devices import DeviceInfo
from utils.errors import AudioError


class Roles(Enum):
    eConsole = 0
    eMultimedia = 1
    eCommunications = 2


def snapshot():
    return {direction: {
        "devices": [{"id": f"{direction}-old", "name": f"{direction} old"},
                    {"id": f"{direction}-new", "name": f"{direction} new"}],
        "default_id": f"{direction}-old",
        "roles": {role.name: f"{direction}-old" for role in Roles},
    } for direction in ("input", "output")}


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr("system.audio_devices.com_context", nullcontext)
    monkeypatch.setitem(sys.modules, "pycaw.constants", SimpleNamespace(ERole=Roles))
    state = snapshot()
    instance = WindowsAudioDevices()
    instance._snapshot = lambda: deepcopy(state)

    def set_default(endpoint_id, roles=None):
        direction = endpoint_id.split("-")[0]
        for role in (roles if roles is not None else Roles):
            state[direction]["roles"][role.name] = endpoint_id
        state[direction]["default_id"] = state[direction]["roles"]["eConsole"]

    instance._set_default = Mock(side_effect=set_default)
    return instance, state


def test_switch_sets_all_roles_and_binds_after_verification(service):
    instance, state = service
    bind = Mock()
    result = instance.switch("input", "input-new", bind)
    assert set(state["input"]["roles"].values()) == {"input-new"}
    assert state["output"]["default_id"] == "output-old"
    bind.assert_called_once_with(result)


@pytest.mark.parametrize("partial_windows_failure", [False, True])
def test_failure_restores_each_original_role(service, partial_windows_failure):
    instance, state = service
    state["output"]["roles"]["eCommunications"] = "output-new"
    original = deepcopy(state)
    bind = Mock(side_effect=AudioError("microphone failed"))
    if partial_windows_failure:
        normal = instance._set_default.side_effect

        def fail_once(endpoint_id, roles=None):
            if roles is None:
                normal(endpoint_id, [Roles.eConsole])
                raise OSError("COM failure")
            normal(endpoint_id, roles)

        instance._set_default.side_effect = fail_once
    with pytest.raises((OSError, AudioError)):
        instance.switch("output", "output-new", bind)
    assert state == original
    if partial_windows_failure:
        bind.assert_not_called()


def test_disconnected_selection_does_not_change_defaults(service):
    instance, _ = service
    with pytest.raises(ValueError, match="недоступно"):
        instance.switch("input", "disconnected", Mock())
    instance._set_default.assert_not_called()


def test_rollback_error_is_explicit(service):
    instance, _ = service
    instance._set_default.side_effect = OSError("access denied")
    with pytest.raises(RuntimeError, match="восстановить defaults"):
        instance.switch("input", "input-new", Mock())


def test_mapping_rejects_wrong_direction_and_duplicate_names(monkeypatch):
    devices = [DeviceInfo(3, "input old", 1, 0, "Windows WASAPI"),
               DeviceInfo(4, "output old", 0, 2, "Windows WASAPI"),
               DeviceInfo(5, "input old", 1, 0, "MME")]
    monkeypatch.setattr("utils.audio_devices.list_audio_devices", lambda: devices)
    endpoints = default_endpoints(snapshot())
    assert resolve_wasapi_devices(endpoints) == {"input": 3, "output": 4}
    devices.append(DeviceInfo(6, "input old", 1, 0, "Windows WASAPI"))
    with pytest.raises(RuntimeError, match="однозначно"):
        resolve_wasapi_devices(endpoints)
    devices[:] = [DeviceInfo(7, "input old", 0, 2, "Windows WASAPI")]
    with pytest.raises(RuntimeError, match="однозначно"):
        resolve_wasapi_devices(endpoints)


def make_pipeline(monkeypatch):
    from main import VoicePipeline

    pipeline = VoicePipeline.__new__(VoicePipeline)
    pipeline._lock = threading.RLock()
    stream = SimpleNamespace(is_running=True, device=3, level_queue=None)
    stream.stop = Mock(side_effect=lambda: setattr(stream, "is_running", False))
    stream.start = Mock(side_effect=lambda: setattr(stream, "is_running", True))
    stream.set_device = Mock(side_effect=lambda index: setattr(stream, "device", index))
    pipeline._stream = stream
    player = SimpleNamespace(device=4, stop=Mock())
    player.set_device = Mock(side_effect=lambda index: setattr(player, "device", index))
    pipeline._player = player
    pipeline._vad = SimpleNamespace(calibrate=Mock())
    pipeline._audio_devices = default_endpoints(snapshot())
    resolver = Mock(side_effect=lambda devices, **kwargs: {
        "input": 30 if devices["input"]["id"].endswith("new") else 3, "output": 4})
    monkeypatch.setattr("system.audio_devices.resolve_wasapi_devices", resolver)
    return pipeline, resolver


def test_pipeline_keeps_stream_and_calibrates_new_input(monkeypatch):
    pipeline, resolver = make_pipeline(monkeypatch)
    stream = pipeline.stream
    target = default_endpoints(snapshot())
    target["input"] = {"id": "input-new", "name": "input new"}
    pipeline.configure_audio_devices(target)
    assert pipeline.stream is stream
    assert stream.device == 30 and stream.is_running
    pipeline.vad.calibrate.assert_called_once()
    assert pipeline.audio_devices == target
    resolver.assert_called_once_with(target, refresh=True)


def test_failed_calibration_restores_previous_stream(monkeypatch):
    pipeline, resolver = make_pipeline(monkeypatch)
    previous = pipeline.audio_devices
    target = {**previous, "input": {"id": "input-new", "name": "input new"}}
    pipeline.vad.calibrate.side_effect = AudioError("no samples")
    with pytest.raises(AudioError, match="no samples"):
        pipeline.configure_audio_devices(target)
    assert pipeline.audio_devices == previous
    assert pipeline.stream.device == 3 and pipeline.stream.is_running
    assert resolver.call_count == 2


def test_failed_stream_recovery_reports_unavailable(monkeypatch):
    pipeline, resolver = make_pipeline(monkeypatch)
    resolver.side_effect = AudioError("disconnected")
    with pytest.raises(AudioError, match="восстановление не удалось"):
        pipeline.configure_audio_devices(pipeline.audio_devices)
    assert pipeline.audio_devices["input"] is None
    assert not pipeline.stream.is_running


def test_wasapi_capture_and_playback_use_system_conversion(monkeypatch):
    import numpy as np
    import sounddevice as sd
    from core.audio_stream import AudioStream
    from core.audio_output import AudioPlayer
    from utils.audio_devices import wasapi_extra_settings

    monkeypatch.setattr(sd, "query_devices", lambda device: {"hostapi": 0})
    monkeypatch.setattr(sd, "query_hostapis", lambda api: {"name": "Windows WASAPI"})
    settings = Mock()
    constructor = Mock(return_value=settings)
    monkeypatch.setattr(sd, "WasapiSettings", constructor)
    assert wasapi_extra_settings(3) is settings
    constructor.assert_called_once_with(auto_convert=True)
    thread = Mock()
    monkeypatch.setattr("core.audio_stream.threading.Thread", Mock(return_value=thread))
    raw_stream = Mock()
    open_stream = Mock(return_value=raw_stream)
    monkeypatch.setattr(sd, "RawInputStream", open_stream)
    stream = AudioStream(device=3)
    stream.start()
    assert open_stream.call_args.kwargs["extra_settings"] is settings
    thread.is_alive.return_value = False
    stream.stop()
    raw_stream.abort.assert_called_once()
    play = Mock()
    monkeypatch.setattr(sd, "play", play)
    AudioPlayer(device=4).play_array(np.ones(100), 24000, blocking=False)
    assert play.call_args.kwargs["extra_settings"] is settings
