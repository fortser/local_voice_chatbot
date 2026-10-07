from types import SimpleNamespace

import pytest

from core.stt import WhisperSTT
from core.silero_tts import SileroTTS
from core.tts import XTSTTTS


@pytest.mark.parametrize("device", ["cpu", "cuda:0"])
def test_metadata_does_not_load_models(tmp_path, device):
    stt = WhisperSTT(model_size="small", device=device, download_root=tmp_path)
    silero = SileroTTS(model_id="v5_ru", device=device)
    xtts = XTSTTTS(model_name="xtts_v2", device=device, speaker_name="test")
    assert stt.model_name == "small" and stt.device == device
    assert silero.model_name == "v5_ru" and silero.device == device
    assert xtts.model_name == "xtts_v2" and xtts.device == device
    assert not any(provider.is_loaded for provider in (stt, silero, xtts))
    stt._model = SimpleNamespace(device="cuda:1")
    silero._model = SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device="cuda:2")]))
    xtts._model = SimpleNamespace(synthesizer=SimpleNamespace(tts_model=SimpleNamespace(device="cuda:3")))
    assert stt.device == "cuda:1" and silero.device == "cuda:2" and xtts.device == "cuda:3"
