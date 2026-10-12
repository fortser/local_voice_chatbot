"""Фильтр речи Silero VAD + очистка галлюцинаций — ручная приёмка на реальных моделях.

Автотесты (tests/test_speech_filters.py, tests/test_gigaam_stt.py) проверяют
логику без моделей. Этот скрипт проверяет то, что можно увидеть только на
вашем железе: Silero VAD загружается, тишина и щелчки не доходят до
Whisper, а настоящая речь распознаётся без потерь.

Запуск из корня проекта:
    python stage_test/check_stage_speech_filters.py            # Whisper
    python stage_test/check_stage_speech_filters.py --gigaam   # + сравнение с GigaAM-v3
    python stage_test/check_stage_speech_filters.py --list-devices
    python stage_test/check_stage_speech_filters.py --device 12  # другой микрофон

Что делает:
  1. Синтетика без микрофона: 4 с тишины, 4 с слабого шума, щелчки.
     Для каждого файла печатает «сырой» Whisper (без фильтров) и результат
     с фильтрами. Ожидание: сырой Whisper может выдумать фразу, с фильтрами
     текст пустой.
     Затем ваша запись речи с этапа 9 (logs/stage9/take1_raw.wav, если есть):
     фильтр должен её пропустить.
  2. Запись с микрофона — того же, что выбран в программе, или указанного
     через --device (список: --list-devices). Каждый дубль пишется ровно
     5 секунд с обратным отсчётом после Enter:
       • дубль 1 — скажите обычную фразу, например «купить хлеб и молоко»;
       • дубль 2 — помолчите;
       • дубль 3 — постучите по столу / пощёлкайте мышью.
     Для каждого дубля печатаются уровень сигнала, решение фильтра речи
     (сколько мс речи), сырой текст и очищенный текст. WAV-файлы — в
     logs/stage_speech_filters/.
  3. Вопрос о приёмке y/n.

Критерии приёмки:
  [ ] В начале вывода «Silero VAD: загружен» (иначе: pip install silero-vad)
  [ ] Синтетическая тишина/шум/щелчки: очищенный текст пустой
  [ ] Эталон logs/stage9/take1_raw.wav: речь найдена, текст с фильтрами совпадает с сырым
  [ ] Молчание и стук с микрофона: «речи нет» или пустой текст
  [ ] Обычная фраза распознана целиком, слова не потеряны
  [ ] (--gigaam) GigaAM загружается и распознаёт ту же фразу

ПРИМЕЧАНИЕ: скрипт временный, удаляется после приёмки этапа.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bootstrap import bootstrap  # noqa: E402

bootstrap()

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from config import settings  # noqa: E402
from config_model import STTFilterSettings  # noqa: E402
from core.speech_gate import SpeechGate, discard  # noqa: E402

OUT_DIR = REPO_ROOT / "logs" / "stage_speech_filters"
SR = 16000


def banner(title: str) -> None:
    print("\n" + "=" * 64 + f"\n  {title}\n" + "=" * 64)


def synthetic_files() -> list[tuple[str, Path]]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    silence = np.zeros(SR * 4, dtype=np.float32)
    noise = (rng.standard_normal(SR * 4) * 0.003).astype(np.float32)
    clicks = noise.copy()
    for start in range(SR // 2, len(clicks), SR // 2):
        clicks[start:start + 80] += 0.6 * np.hanning(80).astype(np.float32)
    result = []
    for name, audio in (("тишина", silence), ("слабый шум", noise), ("щелчки", clicks)):
        path = OUT_DIR / f"synthetic_{len(result)}.wav"
        sf.write(path, audio, SR, subtype="PCM_16")
        result.append((name, path))
    return result


def list_microphones() -> None:
    from utils.audio_devices import list_audio_devices

    print("  Микрофоны (номер — имя [интерфейс]); для проверки нужен вариант с WASAPI:")
    for device in list_audio_devices():
        if device.input_channels > 0:
            print(f"    #{device.index:<3} {device.name} [{device.hostapi}]")


def record_fixed(stream, seconds: float, path: Path) -> Path:
    """Записать ровно ``seconds`` секунд — без энергетического порога и таймингов."""
    import queue

    while True:  # выбросить звук, накопленный до начала дубля
        try:
            stream.chunk_queue.get_nowait()
        except queue.Empty:
            break
    chunks = []
    stream.start_recording()
    try:
        started = time.monotonic()
        shown = -1
        while (elapsed := time.monotonic() - started) < seconds:
            left = int(seconds - elapsed) + 1
            if left != shown:
                print(f"\r  🎤 Запись… осталось {left} с ", end="", flush=True)
                shown = left
            try:
                samples, _rms = stream.chunk_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            chunks.append(samples)
    finally:
        stream.stop_recording()
    print("\r  🎤 Запись закончена.          ")
    audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
    sf.write(str(path), audio, stream.sample_rate, subtype="PCM_16")
    return path


def select_microphone(stream, device: int | None = None) -> str:
    if device is not None:
        from utils.audio_devices import list_audio_devices

        info = next((d for d in list_audio_devices() if d.index == device), None)
        stream.set_device(device)
        return f"{info.name if info else '?'} (#{device}, указан вручную)"
    return _select_app_microphone(stream)


def _select_app_microphone(stream) -> str:
    """Тот же микрофон, что в программе: выбор из Modern UI, иначе устройство Windows."""
    try:
        from system.audio_devices import WindowsAudioDevices, default_endpoints, resolve_wasapi_devices

        snapshot = WindowsAudioDevices().snapshot()
        endpoint = default_endpoints(snapshot).get("input")
        source = "микрофон Windows по умолчанию"
        preferred = ""
        try:
            from PySide6.QtCore import QSettings

            preferred = str(QSettings("Shura", "ModernUI").value("audio/input", "") or "")
        except Exception:
            pass
        if preferred:
            chosen = next((d for d in snapshot["input"]["devices"] if d["id"] == preferred), None)
            if chosen is not None:
                endpoint, source = chosen, "микрофон, выбранный в программе"
        if endpoint is None:
            return "не найден активный микрофон — проверьте настройки звука Windows"
        index = resolve_wasapi_devices({"input": endpoint}, refresh=True)["input"]
        stream.set_device(index)
        return f"{endpoint['name']} ({source}, WASAPI #{index})"
    except Exception as exc:
        return f"устройство PortAudio по умолчанию — не удалось выбрать как в программе: {exc}"


def describe_level(path: Path, threshold: float) -> str:
    audio, _ = sf.read(str(path), dtype="int16", always_2d=False)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    audio = audio.astype(np.float64)
    frame = 800  # 50 мс
    frames = len(audio) // frame
    rms = np.sqrt((audio[:frames * frame].reshape(frames, frame) ** 2).mean(axis=1)) if frames else np.zeros(1)
    loud = (rms > max(threshold, 1.0) * 2).sum() * 50
    hint = "" if rms.max() > 1500 else "  ← очень тихо: голос почти не слышен микрофону"
    return (f"  Уровень: пик {np.abs(audio).max():.0f}, макс. RMS {rms.max():.0f} "
            f"(порог {threshold:.0f}), громких участков {loud} мс{hint}")


def recognise(stt, gate: SpeechGate, raw_filter: STTFilterSettings, path: Path) -> None:
    stt._filter_settings = raw_filter
    raw = stt.transcribe(str(path), profile="dictation")
    stt._filter_settings = None  # настройки [stt.filter]
    decision = gate.filter_file(path, purpose="проверка")
    if decision.has_speech:
        try:
            clean = stt.transcribe(decision.path, profile="dictation")
        finally:
            discard(decision)
    else:
        clean = ""
    print(f"  Фильтр речи: {decision.reason}, речи {decision.speech_ms:.0f} мс из {decision.duration_ms:.0f} мс")
    print(f"  Сырой текст:     «{raw}»")
    print(f"  С фильтрами:     «{clean}»")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gigaam", action="store_true", help="дополнительно проверить GigaAM-v3")
    parser.add_argument("--takes", type=int, default=3, help="число дублей с микрофона")
    parser.add_argument("--seconds", type=float, default=5.0, help="длина каждого дубля, с")
    parser.add_argument("--device", type=int, default=None,
                        help="номер микрофона из --list-devices вместо выбранного в программе")
    parser.add_argument("--list-devices", action="store_true", help="показать микрофоны и выйти")
    args = parser.parse_args()
    if args.list_devices:
        list_microphones()
        return 0

    banner("Загрузка")
    gate = SpeechGate(settings.speech_gate)
    print("  Silero VAD:", "загружен" if gate.preload() else f"НЕ загружен ({gate.unavailable_reason})")
    from core.stt import WhisperSTT

    whisper = WhisperSTT()
    whisper.load_model()
    providers = [("Whisper", whisper)]
    if args.gigaam:
        from core.gigaam_stt import GigaAMSTT

        gigaam = GigaAMSTT()
        gigaam.load_model()
        providers.append(("GigaAM-v3", gigaam))
    raw_filter = STTFilterSettings(enabled=False)

    banner("1. Синтетика без микрофона и эталонная речь")
    for name, path in synthetic_files():
        for title, stt in providers:
            print(f"\n  [{name}] {title}")
            recognise(stt, gate, raw_filter, path)
    sample = REPO_ROOT / "logs" / "stage9" / "take1_raw.wav"  # ваша запись речи (этап 9)
    if sample.is_file():
        for title, stt in providers:
            print(f"\n  [эталон: ваша запись речи logs/stage9/take1_raw.wav] {title}")
            print("  Ожидание: фильтр находит речь, текст с фильтрами совпадает с сырым.")
            recognise(stt, gate, raw_filter, sample)

    banner("2. Запись с микрофона")
    from core.audio_stream import AudioStream
    from core.vad import VoiceActivityDetector

    stream = AudioStream()
    microphone = select_microphone(stream, args.device)
    print("\n  >>> Микрофон:", microphone)
    print("  Если это не тот микрофон, в который вы говорите: посмотрите список")
    print("  python stage_test/check_stage_speech_filters.py --list-devices")
    print("  и запустите с --device <номер>.")
    stream.start()
    try:
        vad = VoiceActivityDetector(stream)
        print("  Калибровка шума — помолчите 2 секунды…")
        noise, threshold = vad.calibrate()
        print(f"  Фоновый шум RMS {noise:.0f}, порог {threshold:.0f}")
        plan = ["скажите обычную фразу, например «купить хлеб и молоко»",
                "помолчите",
                "постучите по столу или пощёлкайте мышью"]
        for take in range(1, args.takes + 1):
            task = plan[(take - 1) % len(plan)]
            input(f"\n  ⏎ Enter — дубль {take} ({args.seconds:.0f} с): {task} … ")
            time.sleep(0.3)  # щелчок Enter не попадает в запись
            wav = record_fixed(stream, args.seconds, OUT_DIR / f"take{take}.wav")
            print(describe_level(wav, threshold))
            for title, stt in providers:
                print(f"\n  [дубль {take}] {title}")
                recognise(stt, gate, raw_filter, wav)
    finally:
        stream.stop()

    answer = input("\nФильтры работают как ожидалось? [y/n] ").strip().lower()
    print("Принято." if answer == "y" else "Не принято — пришлите вывод и logs/voice_ai.log.")
    return 0 if answer == "y" else 1


if __name__ == "__main__":
    raise SystemExit(main())
