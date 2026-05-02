"""Этап 6: IPC-сервер — ручная приёмка.

Что делает скрипт: поднимает VoicePipeline + VoiceAIServer в этом же процессе
(headless-режим), затем в том же процессе дёргает VoiceAIClient и прогоняет
четыре метода API: health_check, generate_only, transcribe_and_respond,
recalibrate. Дополнительно проверяет негативные кейсы — неизвестный метод и
кривые параметры.

Действия пользователя:
  1. Проверьте, что bootstrap() показывает корректные вход/выход Windows.
  2. Убедитесь, что LLM-бэкенд запущен (LM Studio на 1234 или Ollama на 11434).
  3. Во время инициализации и при шаге recalibrate — 2 секунды тишины.
  4. Следите за логами — все IPC-вызовы должны быть видны.

На что обращать внимание:
  * После старта в консоли должно появиться "🛰 IPC сервер на tcp://127.0.0.1:9999".
  * health_check должен вернуть словарь со всеми подсистемами.
  * generate_only — LLM сгенерировал ответ на русском, создан WAV-файл в logs/tts_out.
  * transcribe_and_respond — распознан текст из sample.wav, LLM ответил, создан WAV.
  * recalibrate — noise_rms / threshold рассчитаны, threshold ≥ MIN_ENERGY_THRESHOLD.
  * UNKNOWN_METHOD + INVALID_REQUEST — возвращаются как error-ответы, сервер НЕ падает.
  * После всех тестов — корректное завершение, никаких зависаний.

Ожидаемое время: 30–90 секунд (прогрев Whisper + LLM + Silero TTS).

Критерии приёмки (чек-лист):
  [ ] IPC-сервер поднялся без ошибок на 127.0.0.1:9999.
  [ ] health_check вернул словарь с ключами stt/llm/tts/audio.
  [ ] generate_only: получен непустой output_text + путь к WAV.
  [ ] transcribe_and_respond: input_text не пуст, output_text не пуст, есть WAV.
  [ ] recalibrate: noise_rms ≥ 0, threshold ≥ MIN_ENERGY_THRESHOLD.
  [ ] UNKNOWN_METHOD и INVALID_REQUEST вернулись как structured error, сервер жив.
  [ ] logs/voice_ai.log содержит записи каждого IPC-вызова.
  [ ] После закрытия скрипта — нет зависших потоков, порт освобождён.

ПРИМЕЧАНИЕ: скрипт временный, удаляется после приёмки этапа пользователем.
"""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

from bootstrap import bootstrap
from config import IPC_HOST, IPC_PORT, MIN_ENERGY_THRESHOLD
from ipc import VoiceAIClient, VoiceAIServer
from ipc.client import IPCRemoteError
from main import VoicePipeline


FIXTURE_WAV = Path("tests/fixtures/sample.wav")


CHECKLIST = """
=== Чек-лист приёмки Stage 6 ===
  [ ] IPC-сервер поднялся на 127.0.0.1:9999
  [ ] health_check вернул словарь со всеми подсистемами
  [ ] generate_only: непустой output_text + WAV-файл
  [ ] transcribe_and_respond: input_text и output_text не пусты, есть WAV
  [ ] recalibrate: noise_rms ≥ 0, threshold ≥ MIN_ENERGY_THRESHOLD
  [ ] UNKNOWN_METHOD и INVALID_REQUEST — error-ответы, сервер жив
  [ ] logs/voice_ai.log содержит каждый IPC-вызов
  [ ] После закрытия — нет зависших потоков, порт свободен
"""


def _banner(title: str) -> None:
    print()
    print("─" * 60)
    print(f"  {title}")
    print("─" * 60)


def _pass(msg: str) -> None:
    print(f"  ✅ {msg}")


def _fail(msg: str) -> None:
    print(f"  ❌ {msg}")


def _test_health(client: VoiceAIClient) -> bool:
    _banner("1) health_check")
    try:
        result = client.health_check()
    except Exception as exc:  # noqa: BLE001 — report everything
        _fail(f"raised {type(exc).__name__}: {exc}")
        return False
    print(f"     {result}")
    for key in ("stt", "llm", "tts", "audio"):
        if key not in result:
            _fail(f"missing key {key!r} in result")
            return False
    _pass("health_check вернул все подсистемы")
    if not result["llm"].get("healthy"):
        print(
            f"     ⚠ LLM healthy=False ({result['llm'].get('error')}). "
            "Запустите LM Studio / Ollama перед следующими шагами."
        )
    return True


def _test_generate_only(client: VoiceAIClient) -> bool:
    _banner("2) generate_only")
    try:
        result = client.generate_only("Скажи коротко привет по-русски.")
    except IPCRemoteError as exc:
        _fail(f"server error: {exc}")
        return False
    except Exception as exc:  # noqa: BLE001
        _fail(f"raised {type(exc).__name__}: {exc}")
        return False
    print(f"     input : {result.get('input_text')!r}")
    print(f"     output: {result.get('output_text')!r}")
    print(f"     audio : {result.get('audio_file')}")
    print(f"     time  : {result.get('processing_time'):.2f}s")
    if not (result.get("output_text") or "").strip():
        _fail("пустой output_text")
        return False
    audio = result.get("audio_file")
    if not audio or not Path(audio).is_file():
        _fail(f"WAV не создан: {audio}")
        return False
    _pass(f"LLM ответил, WAV создан ({Path(audio).stat().st_size} bytes)")
    return True


def _test_transcribe(client: VoiceAIClient) -> bool:
    _banner("3) transcribe_and_respond")
    if not FIXTURE_WAV.is_file():
        _fail(f"фикстура {FIXTURE_WAV} не найдена — пропускаем")
        return False
    try:
        result = client.transcribe_and_respond(str(FIXTURE_WAV.resolve()))
    except IPCRemoteError as exc:
        _fail(f"server error: {exc}")
        return False
    except Exception as exc:  # noqa: BLE001
        _fail(f"raised {type(exc).__name__}: {exc}")
        return False
    print(f"     input : {result.get('input_text')!r}")
    print(f"     output: {result.get('output_text')!r}")
    print(f"     audio : {result.get('audio_file')}")
    print(f"     time  : {result.get('processing_time'):.2f}s")
    if not (result.get("input_text") or "").strip():
        _fail("STT вернул пустой input_text")
        return False
    if not (result.get("output_text") or "").strip():
        _fail("LLM вернул пустой output_text")
        return False
    audio = result.get("audio_file")
    if not audio or not Path(audio).is_file():
        _fail(f"WAV не создан: {audio}")
        return False
    _pass("полный цикл STT→LLM→TTS через IPC прошёл")
    return True


def _test_recalibrate(client: VoiceAIClient) -> bool:
    _banner("4) recalibrate (молчите 1.5 сек)")
    print("     перекалибровка…")
    time.sleep(0.5)
    try:
        result = client.recalibrate(duration=1.5)
    except IPCRemoteError as exc:
        _fail(f"server error: {exc}")
        return False
    except Exception as exc:  # noqa: BLE001
        _fail(f"raised {type(exc).__name__}: {exc}")
        return False
    print(f"     {result}")
    if result.get("noise_rms", -1) < 0:
        _fail("noise_rms < 0")
        return False
    if result.get("threshold", 0) < MIN_ENERGY_THRESHOLD:
        _fail(f"threshold {result.get('threshold')} < MIN_ENERGY_THRESHOLD {MIN_ENERGY_THRESHOLD}")
        return False
    _pass("recalibrate вернул корректные значения")
    return True


def _test_error_paths(client: VoiceAIClient) -> bool:
    _banner("5) error-пути (сервер должен выжить)")
    ok = True

    try:
        client._call("does_not_exist", {})  # noqa: SLF001 — мы тестируем wire
    except IPCRemoteError as exc:
        if exc.code == "UNKNOWN_METHOD":
            _pass(f"UNKNOWN_METHOD: {exc.message[:60]}")
        else:
            _fail(f"ожидался UNKNOWN_METHOD, получено {exc.code}")
            ok = False
    except Exception as exc:  # noqa: BLE001
        _fail(f"raised {type(exc).__name__}: {exc}")
        ok = False

    try:
        client._call("generate_only", {"text": ""})  # пустая строка → min_length=1
    except IPCRemoteError as exc:
        if exc.code == "INVALID_REQUEST":
            _pass(f"INVALID_REQUEST: {exc.message[:80]}")
        else:
            _fail(f"ожидался INVALID_REQUEST, получено {exc.code}")
            ok = False
    except Exception as exc:  # noqa: BLE001
        _fail(f"raised {type(exc).__name__}: {exc}")
        ok = False

    # Проверим, что после ошибок сервер ещё жив
    try:
        client.health_check()
        _pass("сервер отвечает после ошибок")
    except Exception as exc:  # noqa: BLE001
        _fail(f"сервер мёртв после ошибок: {exc}")
        ok = False

    return ok


def main() -> int:
    print(__doc__)
    try:
        ans = input("Продолжить? [Enter=да, n=нет] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return 0
    if ans == "n":
        return 0

    bootstrap()
    print("Инициализирую VoicePipeline (это займёт 10–30 сек)…")
    pipeline = VoicePipeline()
    pipeline.start()

    server = VoiceAIServer(pipeline, host=IPC_HOST, port=IPC_PORT)
    server.start()
    print(f"🛰 IPC сервер слушает на tcp://{IPC_HOST}:{IPC_PORT}")

    client = VoiceAIClient()
    results: dict[str, bool] = {}
    try:
        results["health_check"] = _test_health(client)
        results["generate_only"] = _test_generate_only(client)
        results["transcribe_and_respond"] = _test_transcribe(client)
        results["recalibrate"] = _test_recalibrate(client)
        results["error_paths"] = _test_error_paths(client)
    except Exception:  # noqa: BLE001 — show what blew up, still clean up
        print("\n!!! смоук-тесты упали с исключением:")
        traceback.print_exc()
    finally:
        _banner("Останавливаю сервер и пайплайн")
        server.stop()
        pipeline.stop()

    _banner("Итоги смоук-тестов")
    for name, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {name}")

    print(CHECKLIST)
    try:
        input("Все ли критерии выполнены? (y/n) — нажмите Enter, чтобы выйти. ")
    except (EOFError, KeyboardInterrupt):
        print()
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
