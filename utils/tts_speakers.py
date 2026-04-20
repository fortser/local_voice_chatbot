"""List built-in XTTS-v2 studio speakers.

Usage:
    python -m utils.tts_speakers

Loads the XTTS model (first run downloads ~1.8 GB), prints every built-in
speaker name. Copy one into ``config.TTS_SPEAKER_NAME``.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    # Auto-accept the CPML license prompt so this runs headlessly.
    os.environ.setdefault("COQUI_TOS_AGREED", "1")

    from bootstrap import bootstrap
    from config import TTS_DEVICE, TTS_MODEL_NAME

    bootstrap(verbose=False)

    try:
        from TTS.api import TTS as CoquiTTS
    except ImportError:
        print("coqui-tts is not installed — run `pip install coqui-tts`")
        return 2

    print(f"Loading {TTS_MODEL_NAME} on {TTS_DEVICE}...")
    model = CoquiTTS(TTS_MODEL_NAME)
    if TTS_DEVICE and TTS_DEVICE != "cpu":
        model = model.to(TTS_DEVICE)

    speakers = getattr(model, "speakers", None)
    if not speakers:
        # XTTS keeps speakers nested under the inner model on some versions.
        speakers = getattr(getattr(model, "synthesizer", None), "tts_model", None)
        speakers = getattr(speakers, "speaker_manager", None)
        speakers = getattr(speakers, "name_to_id", {}) if speakers else {}
        speakers = list(speakers.keys())

    if not speakers:
        print("No built-in speakers found for this model.")
        return 1

    print(f"\nBuilt-in speakers ({len(speakers)}):")
    for name in sorted(speakers):
        print(f"  {name}")
    print(
        "\nSet config.TTS_SPEAKER_NAME to any of the above to use that voice."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
