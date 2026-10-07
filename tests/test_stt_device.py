"""Device validation does not deserialize weights when CUDA is unavailable."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core.stt import WhisperSTT
from utils.errors import STTError


@pytest.mark.parametrize("cuda_version, expected", [
    (None, "без поддержки CUDA"),
    ("12.4", "Проверьте драйвер NVIDIA"),
])
@pytest.mark.parametrize("device", ["cuda", "cuda:0"])
def test_cuda_unavailable_fails_before_loading(monkeypatch, tmp_path, cuda_version, expected, device):
    whisper = SimpleNamespace(load_model=Mock())
    torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        version=SimpleNamespace(cuda=cuda_version), __version__="test-version",
    )
    monkeypatch.setitem(sys.modules, "whisper", whisper)
    monkeypatch.setitem(sys.modules, "torch", torch)
    provider = WhisperSTT(device=device, download_root=tmp_path)
    with pytest.raises(STTError, match=expected) as error:
        provider.load_model()
    assert sys.executable in str(error.value)
    assert "settings.toml" in str(error.value)
    whisper.load_model.assert_not_called()


@pytest.mark.parametrize("device", ["cpu", "cuda", "cuda:0"])
def test_valid_device_is_passed_to_whisper(monkeypatch, tmp_path, device):
    whisper = SimpleNamespace(load_model=Mock())
    torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: device != "cpu"))
    monkeypatch.setitem(sys.modules, "whisper", whisper)
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setattr("core.stt._vram_snapshot", lambda: "test")
    provider = WhisperSTT(device=device, download_root=tmp_path)
    provider.load_model()
    assert whisper.load_model.call_args.kwargs["device"] == device
    provider.load_model()
    whisper.load_model.assert_called_once()
