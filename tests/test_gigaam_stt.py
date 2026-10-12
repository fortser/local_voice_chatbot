"""Опциональный провайдер GigaAM-v3 — без transformers, torch и скачивания весов."""

from __future__ import annotations

import sys
import types
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from config_model import STTFilterSettings
from core import create_stt_provider
from core.gigaam_stt import INSTALL_HINT, GigaAMSTT, split_audio
from utils.errors import STTError

SR = 16000


def test_split_audio_keeps_all_samples_and_cuts_in_pauses():
    loud = np.full(SR * 10, 0.5, dtype=np.float32)
    pause = np.zeros(SR // 2, dtype=np.float32)
    audio = np.concatenate([loud, pause, loud, pause, loud])  # 31 с
    chunks = split_audio(audio, SR, max_seconds=12.0, search_seconds=4.0)
    assert len(chunks) == 3
    assert all(len(chunk) <= 12 * SR for chunk in chunks)
    assert np.array_equal(np.concatenate(chunks), audio)
    # Разрезы попадают в паузы, а не в середину громкого звука.
    assert np.abs(chunks[0][-10:]).max() == 0 and np.abs(chunks[1][:10]).max() == 0
    short = split_audio(audio[:SR], SR, max_seconds=12.0)
    assert len(short) == 1 and np.array_equal(short[0], audio[:SR])
    assert split_audio(np.zeros(0, dtype=np.float32), SR) == []


def test_factory_registers_gigaam_without_heavy_imports(monkeypatch):
    monkeypatch.setitem(sys.modules, "transformers", None)  # импорт упал бы
    provider = create_stt_provider("gigaam")
    assert isinstance(provider, GigaAMSTT)
    assert not provider.is_loaded
    assert provider.model_name == "GigaAM-v3 e2e_rnnt"


@pytest.fixture
def fake_stack(monkeypatch):
    """Поддельные torch, transformers и модуль модели с load_audio через ffmpeg."""
    calls = SimpleNamespace(loaded=[], pretrained=None, ffmpeg=0, moved_to=None)

    torch = types.ModuleType("torch")
    torch.__version__ = "fake"
    torch.Tensor = type("Tensor", (), {})
    torch.cuda = SimpleNamespace(is_available=lambda: True, empty_cache=lambda: None)
    torch.from_numpy = lambda array: array
    torch.inference_mode = nullcontext
    monkeypatch.setitem(sys.modules, "torch", torch)

    modeling = types.ModuleType("transformers_modules.fake_gigaam")

    def ffmpeg_load_audio(path, sample_rate=SR):
        calls.ffmpeg += 1
        raise RuntimeError("ffmpeg is not installed")

    modeling.load_audio = ffmpeg_load_audio

    class FakeGigaAM:
        def to(self, device):
            calls.moved_to = device
            return self

        def eval(self):
            return self

        def transcribe(self, wav_file):
            audio = modeling.load_audio(wav_file)
            calls.loaded.append(len(audio))
            return SimpleNamespace(text=f"часть {len(calls.loaded)}")

    FakeGigaAM.__module__ = modeling.__name__
    modeling.FakeGigaAM = FakeGigaAM
    monkeypatch.setitem(sys.modules, modeling.__name__, modeling)

    def from_pretrained(model_id, **kwargs):
        calls.pretrained = (model_id, kwargs)
        return FakeGigaAM()

    transformers = types.ModuleType("transformers")
    transformers.AutoModel = SimpleNamespace(from_pretrained=from_pretrained)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monkeypatch.setattr("core.gigaam_stt._vram_snapshot", lambda: "test")
    return calls


def test_load_and_transcribe_long_audio_without_ffmpeg(fake_stack, tmp_path):
    path = tmp_path / "long.wav"
    sf.write(path, np.full(SR * 30, 0.1, dtype=np.float32), SR, subtype="PCM_16")
    provider = GigaAMSTT(model_id="ai-sage/GigaAM-v3", revision="e2e_ctc", device="cuda",
                         download_root=tmp_path / "models", max_chunk_s=12.0,
                         filter_settings=STTFilterSettings())
    provider.load_model()
    model_id, kwargs = fake_stack.pretrained
    assert model_id == "ai-sage/GigaAM-v3"
    assert kwargs["revision"] == "e2e_ctc" and kwargs["trust_remote_code"] is True
    assert fake_stack.moved_to == "cuda"
    assert provider.transcribe(str(path), profile="dictation") == "часть 1 часть 2 часть 3"
    assert fake_stack.ffmpeg == 0
    assert all(length <= 12 * SR for length in fake_stack.loaded)
    assert sum(fake_stack.loaded) == 30 * SR
    provider.unload_model()
    assert not provider.is_loaded


def test_transcript_filter_applies_to_gigaam(fake_stack, tmp_path, monkeypatch):
    path = tmp_path / "a.wav"
    sf.write(path, np.full(SR, 0.1, dtype=np.float32), SR, subtype="PCM_16")
    provider = GigaAMSTT(model_id="m", revision="e2e_rnnt", device="cpu", download_root=tmp_path,
                         max_chunk_s=22.0, filter_settings=STTFilterSettings())
    provider.load_model()
    monkeypatch.setattr(provider._model, "transcribe",
                        lambda wav: "Купить хлеб. Продолжение следует.", raising=False)
    assert provider.transcribe(str(path), profile="dictation") == "Купить хлеб."


def test_missing_dependencies_and_cuda_are_reported(fake_stack, monkeypatch, tmp_path):
    provider = GigaAMSTT(model_id="m", revision="e2e_rnnt", device="cuda", download_root=tmp_path,
                         max_chunk_s=22.0)
    sys.modules["torch"].cuda.is_available = lambda: False
    with pytest.raises(STTError, match="CUDA недоступна"):
        provider.load_model()
    monkeypatch.setitem(sys.modules, "transformers", None)
    with pytest.raises(STTError) as error:
        provider.load_model()
    assert INSTALL_HINT in str(error.value)
    with pytest.raises(STTError, match="not loaded"):
        provider.transcribe(str(tmp_path / "missing.wav"))
