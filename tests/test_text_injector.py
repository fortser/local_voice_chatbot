"""Win32 Unicode input layout and failure behavior, with a fake Windows API."""

import ctypes
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from system import text_injector as injector


def test_unicode_packets_preserve_cyrillic_and_surrogates_without_enter():
    packets = injector.unicode_inputs("Привет\n😀")
    units = b"".join(packet.ki.wScan.to_bytes(2, "little") for packet in packets[::2])
    assert units.decode("utf-16-le") == "Привет 😀"
    assert all(packet.type == 1 and packet.ki.wVk == 0 for packet in packets)
    assert all(packet.ki.dwFlags == 4 for packet in packets[::2])
    assert all(packet.ki.dwFlags == 6 for packet in packets[1::2])
    assert ctypes.sizeof(injector._Input) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)


@pytest.mark.parametrize("mode", ["success", "own", "partial", "missing", "modifier"])
def test_insertion_skips_own_app_and_does_not_retry(monkeypatch, mode):
    api = SimpleNamespace(GetForegroundWindow=Mock(return_value=0 if mode == "missing" else 123),
                          GetWindowThreadProcessId=Mock(), GetAsyncKeyState=Mock(return_value=0),
                          SendInput=Mock())
    def process(window, result):
        result._obj.value = 10 if mode == "own" else 20
        return 1
    api.GetWindowThreadProcessId.side_effect = process
    api.SendInput.side_effect = lambda count, *args: count - 1 if mode == "partial" else count
    if mode == "modifier":
        api.GetAsyncKeyState.return_value = 0x8000
    monkeypatch.setattr(injector, "os", SimpleNamespace(name="nt", getpid=lambda: 10))
    monkeypatch.setattr(injector.ctypes, "WinDLL", lambda *args, **kwargs: api, raising=False)
    if mode in {"partial", "missing", "modifier"}:
        with pytest.raises(RuntimeError):
            injector.inject_text("Текст")
    else:
        assert injector.inject_text("Текст") == (mode == "success")
    assert api.SendInput.call_count == (1 if mode in {"success", "partial"} else 0)
