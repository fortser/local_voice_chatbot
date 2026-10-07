"""Windows endpoint IDs and defaults. COM objects never leave their thread."""

from __future__ import annotations

from contextlib import contextmanager
import threading
from typing import Callable


@contextmanager
def com_context():
    import comtypes

    comtypes.CoInitialize()
    try:
        yield
    finally:
        comtypes.CoUninitialize()


class WindowsAudioDevices:
    def __init__(self) -> None:
        self._lock = threading.RLock()

    def snapshot(self) -> dict:
        with self._lock, com_context():
            return self._snapshot()

    @staticmethod
    def _snapshot() -> dict:
        from pycaw.constants import DEVICE_STATE, EDataFlow, ERole
        from pycaw.pycaw import AudioUtilities

        enumerator = AudioUtilities.GetDeviceEnumerator()
        result = {}
        for direction, flow in (("input", EDataFlow.eCapture), ("output", EDataFlow.eRender)):
            devices = AudioUtilities.GetAllDevices(flow.value, DEVICE_STATE.ACTIVE.value)
            defaults = {}
            for role in ERole:
                if role.name == "ERole_enum_count":
                    continue
                try:
                    defaults[role.name] = enumerator.GetDefaultAudioEndpoint(flow.value, role.value).GetId()
                except OSError:
                    defaults[role.name] = None
            result[direction] = {
                "devices": [{"id": device.id, "name": device.FriendlyName or device.id}
                            for device in devices],
                "default_id": defaults.get("eConsole"),
                "roles": defaults,
            }
        return result

    @staticmethod
    def _set_default(endpoint_id: str, roles=None) -> None:
        from pycaw.constants import ERole
        from pycaw.pycaw import AudioUtilities

        roles = roles if roles is not None else [ERole.eConsole, ERole.eMultimedia, ERole.eCommunications]
        AudioUtilities.SetDefaultDevice(endpoint_id, roles=roles)

    def switch(self, direction: str, endpoint_id: str, bind: Callable[[dict], None]) -> dict:
        """Change all roles, bind app streams, and roll defaults back on failure."""
        if direction not in {"input", "output"}:
            raise ValueError("Неизвестное направление аудио")
        with self._lock, com_context():
            before = self._snapshot()
            if not any(device["id"] == endpoint_id for device in before[direction]["devices"]):
                raise ValueError("Выбранное аудиоустройство больше недоступно")
            try:
                self._set_default(endpoint_id)
                after = self._snapshot()
                if any(value != endpoint_id for value in after[direction]["roles"].values()):
                    raise RuntimeError("Windows не подтвердила смену аудиоустройства")
                bind(after)
                return after
            except Exception as original:
                from pycaw.constants import ERole

                errors = []
                for role, previous_id in before[direction]["roles"].items():
                    if previous_id:
                        try:
                            self._set_default(previous_id, [getattr(ERole, role)])
                        except Exception as rollback:
                            errors.append(str(rollback))
                if errors:
                    raise RuntimeError(f"{original}. Не удалось восстановить defaults Windows: {'; '.join(errors)}") from original
                raise


def default_endpoints(snapshot: dict) -> dict:
    """Resolve defaults to stable IDs and names, allowing a missing direction."""
    result = {}
    for direction in ("input", "output"):
        info = snapshot[direction]
        result[direction] = next((dict(device) for device in info["devices"]
                                  if device["id"] == info["default_id"]), None)
    return result


def resolve_wasapi_devices(endpoints: dict, *, refresh: bool = False) -> dict:
    """Map only unambiguous WASAPI names. Caller must stop all app streams."""
    import sounddevice as sd
    from utils.audio_devices import list_audio_devices

    if refresh:
        # PortAudio caches its Windows endpoints. Re-enumerate only while the
        # pipeline lock is held and both its capture/playback streams are shut.
        sd._terminate()
        sd._initialize()
    devices = list_audio_devices()
    indices = {}
    for direction, channels in (("input", "input_channels"), ("output", "output_channels")):
        endpoint = endpoints.get(direction)
        if endpoint is None:
            indices[direction] = None
            continue
        matches = [device.index for device in devices
                   if "wasapi" in device.hostapi.casefold() and getattr(device, channels) > 0
                   and device.name.strip().casefold() == endpoint["name"].strip().casefold()]
        if len(matches) != 1:
            raise RuntimeError(f"Не удалось однозначно сопоставить устройство WASAPI: {endpoint['name']}")
        indices[direction] = matches[0]
    return indices
