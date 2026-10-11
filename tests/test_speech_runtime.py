"""Speech tools without models, audio hardware, network or Qt."""

from pathlib import Path
import queue
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import soundfile as sf

from core.base import TTSProvider
from core.dictation import dictate
from core.speech_runtime import SpeechRuntime, atomic_export, split_text
from core.stt import WhisperSTT, _load_audio_float32
from utils.errors import CancelledError, STTError


class FakeSTT:
    def __init__(self):
        self.is_loaded = False
        self.loads = 0
        self.calls = []

    def load_model(self):
        self.is_loaded = True
        self.loads += 1

    def unload_model(self):
        self.is_loaded = False

    def transcribe(self, path, *, profile="command"):
        self.calls.append((path, profile))
        return "Спасибо"


class FakeTTS(TTSProvider):
    def __init__(self, directory):
        self.directory = directory
        self.is_loaded = False
        self.loads = 0
        self.parts = []

    def load_model(self):
        self.is_loaded = True
        self.loads += 1

    def unload_model(self):
        self.is_loaded = False

    def synthesize(self, text):
        self.parts.append(text)
        path = self.directory / f"part-{len(self.parts)}.wav"
        sf.write(path, np.full(100, len(self.parts) / 100), 16000, subtype="PCM_16")
        return str(path)


@pytest.fixture
def runtime(tmp_path):
    stt, tts = FakeSTT(), FakeTTS(tmp_path)
    result = SpeechRuntime(stt_factory=lambda: stt, tts_factory=lambda: tts, gpu_swap=False)
    yield result
    result.close()


def test_lazy_resources_and_no_llm(runtime, monkeypatch):
    monkeypatch.setattr("core.create_llm_provider", Mock(side_effect=AssertionError("LLM must not be created")))
    assert runtime._stt is runtime._tts is runtime._stream is runtime._player is None
    assert runtime.transcribe("test.wav", threading.Event()) == "Спасибо"
    runtime.transcribe("test.wav", threading.Event())
    assert runtime.stt.loads == 1
    assert runtime.stt.calls[-1][1] == "dictation"
    assert runtime._tts is runtime._stream is runtime._player is None


@pytest.mark.parametrize("text", ["фраза. " * 400, "я" * 1501, "а" * 299 + ". " + "б" * 800])
def test_chunks_preserve_all_characters(text):
    parts = split_text(text)
    assert max(map(len, parts)) <= 300
    assert "".join("".join(parts).split()) == "".join(text.split())


def test_long_synthesis_order_cleanup_and_pcm16(runtime, tmp_path):
    text = "Первое предложение. " * 100
    progress = []
    output = runtime.synthesize(text, threading.Event(), progress=lambda *args: progress.append(args))
    parts = runtime.tts.parts
    assert " ".join(parts) == text.strip()
    data, sr = sf.read(output)
    assert sr == 16000 and len(data) == 100 * len(parts)
    for index in range(len(parts)):
        assert data[index * 100] == pytest.approx((index + 1) / 100, abs=0.0001)
    assert sf.info(output).subtype == "PCM_16"
    assert not list(tmp_path.glob("part-*.wav"))
    assert progress[-1] == (len(parts), len(parts))
    assert runtime._stream is runtime._player is runtime._stt is None


def test_cancel_long_synthesis_removes_partial_audio(runtime, tmp_path):
    cancel = threading.Event()
    with pytest.raises(CancelledError):
        runtime.synthesize("Фраза. " * 200, cancel, progress=lambda *args: cancel.set())
    assert not list(runtime.workspace.glob("*.wav"))
    assert not list(tmp_path.glob("part-*.wav"))


def test_gpu_swap_restores_only_previously_loaded_stt(runtime):
    runtime._gpu_swap = True
    with runtime.tts_session():
        assert runtime.tts.is_loaded
    assert runtime._stt is None
    runtime.ensure_stt()
    with pytest.raises(RuntimeError):
        with runtime.tts_session():
            assert not runtime.stt.is_loaded
            raise RuntimeError("synthesis failed")
    assert runtime.stt.is_loaded and not runtime.tts.is_loaded


def test_export_failure_and_cancel_preserve_files(runtime, tmp_path, monkeypatch):
    original = Path(runtime.synthesize("Текст", threading.Event()))
    target = tmp_path / "saved.wav"
    target.write_bytes(b"old")
    monkeypatch.setattr("core.speech_runtime.os.replace", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError):
        atomic_export(original, target, threading.Event())
    assert original.exists() and target.read_bytes() == b"old"
    assert not list(tmp_path.glob(".shura-*"))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(CancelledError):
        atomic_export(original, target, cancel)


@pytest.mark.parametrize("extension", ["wav", "flac"])
def test_audio_file_stereo_resampling_and_neutral_profile(tmp_path, extension):
    path = tmp_path / f"audio.{extension}"
    sf.write(path, np.ones((8000, 2)) * 0.1, 8000)
    audio = _load_audio_float32(path)
    assert audio.shape == (16000,) and audio.dtype == np.float32
    provider = WhisperSTT(device="cpu", download_root=tmp_path)
    provider._model = Mock()
    provider._model.transcribe.return_value = {"text": "Спасибо за внимание"}
    assert provider.transcribe(str(path), profile="dictation") == "Спасибо за внимание"
    assert provider._model.transcribe.call_args.kwargs["initial_prompt"] is None
    assert provider.transcribe(str(path)) == ""
    assert "Шурочка" in provider._model.transcribe.call_args.kwargs["initial_prompt"]


@pytest.mark.parametrize("contents", [b"", b"not audio"])
def test_bad_audio_fails_without_result(tmp_path, contents):
    path = tmp_path / "bad.wav"
    path.write_bytes(contents)
    provider = WhisperSTT(device="cpu", download_root=tmp_path)
    provider._model = Mock()
    with pytest.raises(STTError):
        provider.transcribe(str(path), profile="dictation")
    provider._model.transcribe.assert_not_called()


class CaptureStream:
    sample_rate = 100
    chunk_size = 2
    is_running = True

    def __init__(self):
        self.chunk_queue = queue.Queue()
        self.started = threading.Event()
        self.start_count = 0

    def start_recording(self):
        self.start_count += 1
        self.started.set()

    def stop_recording(self):
        pass

    def set_speech_active(self, active):
        pass

    def phrase(self):
        self.chunk_queue.put((np.array([500, 500], dtype=np.int16), 500))
        self.chunk_queue.put((np.zeros(2, dtype=np.int16), 0))


@pytest.mark.parametrize("mode", ["stop", "cancel", "overflow"])
def test_continuous_capture_while_recognizer_is_busy(tmp_path, mode):
    stream = CaptureStream()
    entered, release = threading.Event(), threading.Event()
    stop, cancel = threading.Event(), threading.Event()
    texts, errors, stages = [], [], []
    vad = SimpleNamespace(reset_threshold=lambda: None, threshold=100)
    calls = []

    def transcribe(path, cancel, stage):
        calls.append(path)
        entered.set()
        assert release.wait(3)
        check = CancelledError("cancelled") if cancel.is_set() else None
        if check:
            raise check
        return str(len(calls))

    runtime = SimpleNamespace(ensure_stt=lambda stage: None, ensure_microphone=lambda stage: None,
                              vad=vad, stream=stream, workspace=tmp_path, transcribe=transcribe)

    def run():
        try:
            dictate(runtime, stop, cancel, texts.append, stages.append,
                    pause=0.02, queue_size=1 if mode == "overflow" else 10)
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert stream.started.wait(3)
        stream.phrase()
        assert entered.wait(3)
        if mode == "overflow":
            stream.phrase()
            stream.phrase()
            assert stop.wait(3)
        else:
            # The final segment has speech but no trailing pause: Stop must flush it.
            stream.chunk_queue.put((np.array([500, 500], dtype=np.int16), 500))
            (cancel if mode == "cancel" else stop).set()
    finally:
        release.set()
        worker.join(4)
        if worker.is_alive():
            cancel.set()
            worker.join(2)
    assert not worker.is_alive()
    assert stream.start_count == 1
    assert not list(tmp_path.iterdir())
    if mode == "stop":
        assert texts == ["1", "2"] and not errors
    elif mode == "cancel":
        assert not texts and isinstance(errors[0], CancelledError)
    else:
        assert texts == ["1", "2", "3"]
        assert "не успевает" in str(errors[0])
