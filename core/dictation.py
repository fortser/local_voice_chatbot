"""Continuous audio capture with bounded, ordered background transcription."""

from __future__ import annotations

from collections import deque
from pathlib import Path
import queue
import tempfile
import threading

import numpy as np
import soundfile as sf

from core.speech_runtime import check_cancel
from utils.errors import AudioError


def dictate(runtime, stop: threading.Event, cancel: threading.Event,
            on_text, stage=lambda message: None, *, pause: float = 1.3,
            max_segment: float = 30.0, queue_size: int = 10) -> None:
    """Caller owns runtime.lock; capture is independent from model inference.

    Stop flushes captured audio. Cancel discards unfinished work. A full queue
    stops capture, retains its final segment and reports overload after draining.
    """
    runtime.ensure_stt(stage)
    check_cancel(cancel)
    if stop.is_set():
        return
    runtime.ensure_microphone(stage)
    check_cancel(cancel)
    if stop.is_set():
        return
    runtime.vad.reset_threshold()
    stream = runtime.stream
    segments: queue.Queue = queue.Queue(maxsize=queue_size)
    done = threading.Event()
    errors = []

    with tempfile.TemporaryDirectory(prefix="dictation-", dir=runtime.workspace) as directory:
        def capture():
            collected = []
            frames = silence = 0
            count = 0
            preroll = deque(maxlen=max(1, int(0.2 * stream.sample_rate / stream.chunk_size)))

            def enqueue():
                nonlocal collected, frames, silence, count
                if not collected:
                    return
                path = Path(directory) / f"{count:06d}.wav"
                sf.write(path, np.concatenate(collected), stream.sample_rate, subtype="PCM_16")
                count += 1
                collected, frames, silence = [], 0, 0
                try:
                    segments.put_nowait(str(path))
                except queue.Full:
                    stop.set()
                    stream.stop_recording()
                    errors.append(AudioError("Распознавание не успевает за записью. Запись остановлена; обрабатываю накопленное."))
                    stage(str(errors[-1]))
                    while not cancel.is_set():
                        try:
                            segments.put(str(path), timeout=0.1)
                            break
                        except queue.Full:
                            pass

            try:
                stream.start_recording()
                stage("Слушаю…")
                while not cancel.is_set():
                    if stop.is_set():
                        stream.stop_recording()
                    try:
                        samples, rms = stream.chunk_queue.get(timeout=0.1)
                    except queue.Empty:
                        if stop.is_set():
                            break
                        if not stream.is_running:
                            raise AudioError("Микрофон отключён во время записи")
                        continue
                    above = rms > runtime.vad.threshold
                    if not collected and not above:
                        preroll.append(samples)
                        continue
                    if not collected:
                        collected.extend(preroll)
                        frames = sum(len(chunk) for chunk in preroll)
                        preroll.clear()
                    collected.append(samples)
                    frames += len(samples)
                    silence = 0 if above else silence + len(samples)
                    stream.set_speech_active(above)
                    if silence / stream.sample_rate >= pause or frames / stream.sample_rate >= max_segment:
                        enqueue()
                        if errors:
                            break
                if not cancel.is_set():
                    enqueue()
            except Exception as exc:
                errors.append(exc)
            finally:
                stream.set_speech_active(False)
                stream.stop_recording()
                done.set()

        recorder = threading.Thread(target=capture, name="speech-capture", daemon=True)
        recorder.start()
        try:
            while not done.is_set() or not segments.empty():
                check_cancel(cancel)
                try:
                    path = segments.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    text = runtime.transcribe(path, cancel, stage)
                    if text:
                        on_text(text)
                finally:
                    Path(path).unlink(missing_ok=True)
            check_cancel(cancel)
            if errors:
                raise errors[0]
        finally:
            # Also releases a producer blocked by a transcription exception.
            if not done.is_set():
                cancel.set()
            recorder.join()
