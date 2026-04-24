"""Этап 9: DeepFilterNet денойз перед Whisper — ручная приёмка.

Что делает скрипт: записывает одну и ту же фразу через микрофон (желательно
BT-гарнитуру в шумной обстановке) и прогоняет Whisper **дважды** —
на исходном WAV и на очищенном через DeepFilterNet. Печатает обе
транскрипции рядом, плюс время денойза и базовые RMS-метрики. Вы
принимаете этап глазами: стал ли текст точнее, нет ли артефактов,
оправдывает ли задержка.

Условия теста (важно для честной оценки):
  * Используйте ту гарнитуру, ради которой это делается (BT/HFP).
  * Создайте типичную шумную обстановку: вентилятор ПК, движение,
    фоновый разговор, улица за окном. Чем хуже условия — тем явнее
    выиграет DFN.
  * Произнесите фразу длиной 3–7 слов, например короткую команду
    ассистенту: «Шурочка, сделай заметку — купить молоко».

Действия пользователя:
  1. Запустите скрипт. Произойдёт bootstrap() + загрузка Whisper и DFN.
     Первый прогон DFN может быть медленным (скачивание весов один раз).
  2. Дождитесь приглашения «🎤 Говорите…» и произнесите тестовую фразу.
  3. Скрипт покажет:
       BASELINE (без DFN):  «…»
       DENOISE  (с DFN):    «…»
       DFN время:          NN мс
       RMS до/после:       X → Y
     WAV-файлы сохраняются в logs/stage9/ для повторного прослушивания.
  4. Повторите 2–3 раза для разных фраз / уровней шума.
  5. Ответьте y/n на вопрос о приёмке.

Критерии приёмки (чек-лист):
  [ ] DeepFilterNet загружается без ошибок (модель скачивается в ~/.cache)
  [ ] Очищенный WAV существует, воспроизводится, слышен голос
  [ ] Ни в одном прогоне Whisper на DFN-версии не **потерял** слова,
      которые корректно были в BASELINE (контроль артефактов)
  [ ] Хотя бы на одной шумной фразе DFN-транскрипция **чище** BASELINE
      (меньше «галлюцинаций», корректнее окончания, итд.)
  [ ] Задержка DFN в пределах ~50 мс на фразу 1–3 сек (на CPU)
  [ ] USE_DEEPFILTER=True не ломает основной пайплайн (`python main.py`
      стартует и принимает один турн — проверяется отдельно после приёмки)

ПРИМЕЧАНИЕ: скрипт временный, удаляется после приёмки этапа.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from bootstrap import bootstrap

# Форсируем USE_DEEPFILTER на время теста — не ждём, пока пользователь
# переключит флаг в config.py. Оригинальный пайплайн это не затрагивает.
import config
config.USE_DEEPFILTER = True

from core.audio_stream import AudioStream  # noqa: E402
from core.preprocessing import (  # noqa: E402
    compute_rms,
    enhance_audio,
    preload_deepfilter,
)
from core.stt import WhisperSTT  # noqa: E402
from core.vad import VoiceActivityDetector  # noqa: E402


OUT_DIR = Path("logs/stage9")


def _banner(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _one_pass(stt: WhisperSTT, vad: VoiceActivityDetector, idx: int) -> bool:
    """Один цикл: запись → baseline STT → DFN → STT → вывод."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    input("\n  ⏎ Enter — начать запись фразы ... ")
    print("  🎤 Говорите (автостоп через ~1 сек тишины)…")
    raw_wav = vad.record_until_silence(
        output_path=str(OUT_DIR / f"take{idx}_raw.wav"),
    )
    print(f"  записано: {raw_wav}")

    # BASELINE
    t0 = time.monotonic()
    baseline_text = stt.transcribe(raw_wav).strip()
    t_baseline = (time.monotonic() - t0) * 1000

    # DENOISE
    clean_wav = OUT_DIR / f"take{idx}_clean.wav"
    t0 = time.monotonic()
    try:
        enhance_audio(Path(raw_wav), clean_wav)
    except Exception as exc:
        print(f"  ❌ DeepFilterNet упал: {exc}")
        return False
    t_dfn = (time.monotonic() - t0) * 1000

    t0 = time.monotonic()
    clean_text = stt.transcribe(str(clean_wav)).strip()
    t_clean = (time.monotonic() - t0) * 1000

    rms_raw = compute_rms(raw_wav)
    rms_clean = compute_rms(str(clean_wav))

    _banner(f"Результат прогона #{idx}")
    print(f"  BASELINE (без DFN): «{baseline_text}»")
    print(f"  DENOISE  (с DFN):   «{clean_text}»")
    print()
    print(f"  STT baseline: {t_baseline:.0f} мс")
    print(f"  DFN денойз:   {t_dfn:.0f} мс")
    print(f"  STT на clean: {t_clean:.0f} мс")
    print(f"  RMS до:       {rms_raw:.0f}")
    print(f"  RMS после:    {rms_clean:.0f}")
    print(f"  WAV файлы:    {raw_wav}  |  {clean_wav}")
    return True


def main() -> int:
    bootstrap()

    print("\nЗагрузка Whisper…")
    stt = WhisperSTT()
    stt.load_model()
    print("Whisper готов.\n")

    print("Загрузка DeepFilterNet (первый раз может скачать веса)…")
    t0 = time.monotonic()
    preload_deepfilter()
    print(f"DFN готов за {time.monotonic() - t0:.1f}с.\n")

    stream = AudioStream()
    stream.start()
    try:
        vad = VoiceActivityDetector(stream)
        print("Калибровка шума (молчите ~2 сек)…")
        noise, thr = vad.calibrate()
        print(f"  шум={noise:.0f} RMS, порог={thr:.0f}")

        takes = 0
        while True:
            takes += 1
            _one_pass(stt, vad, takes)
            again = input("\n  Ещё один прогон? [y/N] ").strip().lower()
            if again != "y":
                break
    finally:
        stream.stop()

    _banner("Приёмка этапа 9")
    print("Пересмотрите критерии в docstring'е скрипта.")
    verdict = input("Принимаете этап? [y/N] ").strip().lower()
    if verdict == "y":
        print("✅ Этап 9 принят. Не забудьте выставить USE_DEEPFILTER=True в config.py.")
        print(f"   Скрипт можно удалить: {Path(__file__).name}")
        return 0
    print("❌ Этап не принят. Правьте и запускайте снова.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
