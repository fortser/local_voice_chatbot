"""Audio device discovery — pure information, no pinning.

The app uses whichever input/output the user selected as Windows defaults.
This module exists so users (and future code) can *see* what's picked and
manually pick something else via Windows Sound Settings if needed.

CLI: ``python -m utils.audio_devices`` lists all devices and highlights the
current defaults.
"""

from __future__ import annotations

from dataclasses import dataclass

import sounddevice as sd


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    input_channels: int
    output_channels: int
    hostapi: str


def list_audio_devices() -> list[DeviceInfo]:
    out: list[DeviceInfo] = []
    hostapis = sd.query_hostapis()
    for i, d in enumerate(sd.query_devices()):
        hostapi_idx = d.get("hostapi", -1)
        hostapi_name = (
            str(hostapis[hostapi_idx].get("name", "?"))
            if 0 <= hostapi_idx < len(hostapis)
            else "?"
        )
        out.append(
            DeviceInfo(
                index=i,
                name=str(d.get("name", "")),
                input_channels=int(d.get("max_input_channels", 0)),
                output_channels=int(d.get("max_output_channels", 0)),
                hostapi=hostapi_name,
            )
        )
    return out


def get_current_devices() -> tuple[DeviceInfo | None, DeviceInfo | None]:
    """Return the current system-default input/output as ``DeviceInfo``."""
    devices = list_audio_devices()
    sys_in, sys_out = sd.default.device
    in_info = devices[sys_in] if 0 <= sys_in < len(devices) else None
    out_info = devices[sys_out] if 0 <= sys_out < len(devices) else None
    return in_info, out_info


def _safe(text: str) -> str:
    try:
        enc = getattr(__import__("sys").stdout, "encoding", None) or "utf-8"
        return text.encode(enc, errors="replace").decode(enc, errors="replace")
    except Exception:
        return text.encode("ascii", errors="replace").decode("ascii")


def print_devices() -> None:
    devices = list_audio_devices()
    sys_in, sys_out = sd.default.device
    print(f"{'idx':>3}  {'dir':<3} {'in':>3} {'out':>3}  {'hostapi':<18} name")
    print("-" * 90)
    for d in devices:
        marks = []
        if d.index == sys_in:
            marks.append("IN*")
        if d.index == sys_out:
            marks.append("OUT*")
        direction = (
            "I/O" if d.input_channels and d.output_channels
            else ("IN" if d.input_channels else "OUT")
        )
        print(
            f"{d.index:>3}  {direction:<3} {d.input_channels:>3} {d.output_channels:>3}  "
            f"{d.hostapi:<18} {_safe(d.name)}  {','.join(marks)}"
        )
    print()
    print(f"Системные дефолты (их и использует приложение): вход=#{sys_in}  выход=#{sys_out}")
    print("Сменить устройство — в Windows: Параметры → Система → Звук.")


if __name__ == "__main__":
    print_devices()
