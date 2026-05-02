"""Этап 10: напоминания — ручная приёмка.

Поток, который валидируем (CONTENT-команда, как Note/Question):

  Шурочка → гудок → «поставь напоминание»
    → ack-WAV «я готова добавить новое напоминание, диктуйте»
    → диктовка тела («напомни через 5 минут проверить кашу»)
    → подтверждение «поставила напоминание через пять минут проверить кашу»
    … в момент fire_at …
    → «вы хотели проверить кашу»

Что тестируем:
  1. Парсер тела (regex-only; умеет съедать «напомни»/«напомни мне»
     в начале — пользователь по привычке повторяет префикс после ack).
  2. Конвертер числа в слова — ОБА бэкенда side-by-side.
  3. Триггер-команда через микрофон: полный CONTENT-поток.
  4. Программное создание напоминания на короткий интервал.
  5. Очередь: напоминание во время активного турна ждёт pipeline-lock.
  6. Персистентность: абсолютный fire_at в logs/reminders.json; рестарт
     процесса → активные снова запланированы, просроченные проиграны.

Скрипт — меню. Пункты 1–2 — быстрые юнит-проверки без запуска
пайплайна; 3+ — полноценный VoicePipeline (Whisper + TTS).

ПРЕД-РЕКВИЗИТ: `python -m utils.generate_ack_phrases` должен быть
запущен после добавления команды — нужен WAV `assets/ack/reminder_before.wav`.
Без него dictate() упадёт на дефолтный беп-стартер и голосового
«я готова добавить новое напоминание» пользователь не услышит (сама
команда всё равно отработает).

Критерии приёмки (чек-лист):
  [ ] `reminder_before.wav` существует и звучит корректно.
  [ ] Триггер («поставь напоминание», «добавь напоминание», …)
      вызывает ack + диктовку, не делает inline-парсинг.
  [ ] Тело «напомни через 5 минут проверить кашу» корректно
      парсится (префикс «напомни» съедается).
  [ ] Подтверждение «поставила напоминание через <N слов> <текст>»
      звучит грамматически корректно для 1/2/5/11/21/22-минутных и
      1/2/5-часовых напоминаний.
  [ ] На слух Silero произносит оба бэкенда чисел естественно.
  [ ] Напоминание на 10 сек срабатывает ровно через 10 сек и
      озвучивает «вы хотели <текст>».
  [ ] Очередь: напоминание запланировано на +5с, сразу задали вопрос
      LLM → напоминание прозвучало ПОСЛЕ ответа.
  [ ] Рестарт: активное напоминание переживает выход процесса
      (или сработает в свой fire_at, или сразу при старте как
      просроченное).
  [ ] Файл logs/reminders.json не повреждается по ходу сценариев.
  [ ] Мусорное тело («кашу проверить») — голосовая подсказка,
      в LLM не уходит.

ПРИМЕЧАНИЕ: скрипт временный, удаляется после приёмки этапа.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from bootstrap import bootstrap


def _banner(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


# ---------- 1. Parser unit checks ----------

def _test_parser() -> None:
    from core.reminders.parser import parse_reminder_tail, unit_to_seconds

    _banner("1. Парсер regex")
    # Тело — как придёт из диктовки: может начинаться с «напомни»/«напомни мне»
    # (пользователь по привычке повторяет часть фразы после ack), либо сразу
    # с «через» или числа.
    cases = [
        ("напомни через 5 минут проверить кашу",       (5, "minute", "проверить кашу")),
        ("напомни мне через 20 минут проверить кашу",  (20, "minute", "проверить кашу")),
        ("20 минут проверить кашу",                     (20, "minute", "проверить кашу")),
        ("через 20 минут проверить кашу",               (20, "minute", "проверить кашу")),
        ("5 секунд тест",                                (5, "second", "тест")),
        ("через 1 секунду позвонить маме",              (1, "second", "позвонить маме")),
        ("2 часа выключить духовку",                    (2, "hour",   "выключить духовку")),
        ("через 3 часа забрать посылку",                (3, "hour",   "забрать посылку")),
        ("21 минуту перезвонить",                       (21, "minute", "перезвонить")),
        ("22 минуты вернуться",                          (22, "minute", "вернуться")),
        ("через полчаса тест",                           None),  # regex не знает «полчаса»
        ("кашу проверить",                               None),  # нет числа
        ("30 минут",                                     None),  # нет текста
        ("",                                              None),
    ]
    ok = True
    for tail, expected in cases:
        got = parse_reminder_tail(tail)
        mark = "✓" if got == expected else "✗"
        if got != expected:
            ok = False
        print(f"  {mark} {tail!r:45} → {got}  (ожидали {expected})")
    print()
    print("unit_to_seconds:")
    for n, u, s in [(5, "second", 5), (3, "minute", 180), (2, "hour", 7200)]:
        got = unit_to_seconds(n, u)
        mark = "✓" if got == s else "✗"
        if got != s:
            ok = False
        print(f"  {mark} ({n}, {u!r}) → {got}c")
    print("\n  Итог парсера:", "OK" if ok else "FAIL")


# ---------- 2. Number-to-words side-by-side ----------

def _test_num_to_words() -> None:
    _banner("2. Конвертер чисел → слов (manual vs num2words)")

    from core.reminders import num_to_words_manual as M
    try:
        from core.reminders import num_to_words_external as E
        have_external = E._num2words is not None
    except Exception as exc:
        print(f"⚠ num2words-бэкенд недоступен: {exc}")
        have_external = False
        E = None  # type: ignore

    numbers = [1, 2, 3, 4, 5, 11, 15, 21, 22, 25, 30, 41, 55, 100, 111, 145]
    units = ["second", "minute", "hour"]

    header = f"{'n':>4} | {'unit':<7} | {'manual':<32} | {'num2words':<32}"
    print(header)
    print("-" * len(header))
    for u in units:
        for n in numbers:
            m_str = M.humanize_duration(n, u)
            if have_external:
                try:
                    e_str = E.humanize_duration(n, u)
                except Exception as exc:
                    e_str = f"ERROR: {exc}"
            else:
                e_str = "— (не установлен)"
            diff = "  " if m_str == e_str else "≠ "
            print(f"{n:>4} | {u:<7} | {m_str:<32} | {diff}{e_str}")
        print()

    print(
        "На слух оцените оба столбца: какой естественнее для Silero\n"
        "произнести фразу «поставила напоминание через <здесь>».\n"
        "Переключение — `NUM_TO_WORDS_BACKEND` в config.py."
    )


# ---------- 3+. Pipeline scenarios ----------

def _run_pipeline() -> "object":
    """Старт полного VoicePipeline. Возвращает объект пайплайна."""
    from main import VoicePipeline
    bootstrap()
    p = VoicePipeline()
    p.start()
    return p


def _test_schedule_now(pipeline: "object", delay_seconds: int = 10) -> None:
    _banner(f"3. Создание напоминания на +{delay_seconds}с (программно)")
    scheduler = pipeline.reminder_scheduler  # type: ignore[attr-defined]
    from core.reminders.num_to_words import humanize_duration

    # Программно — без STT — чтобы проверка не зависела от микрофона.
    text = "проверить таймер тестового этапа"
    scheduler.add(delay_seconds, text)
    print(f"  Добавлено. Ожидайте ~{delay_seconds}с — должна прозвучать фраза:")
    print(f'    «вы хотели {text}»')
    print()
    input("Нажмите Enter после того, как услышите напоминание > ")


def _test_queue_behind_answer(pipeline: "object") -> None:
    _banner("4. Очередь: напоминание ждёт окончания LLM-ответа")
    scheduler = pipeline.reminder_scheduler  # type: ignore[attr-defined]
    print(
        "  Ставлю напоминание на +5с, затем сразу стартую длинный LLM-ответ.\n"
        "  Ожидание: LLM отвечает → ТОЛЬКО ПОТОМ играет напоминание.\n"
    )
    scheduler.add(5, "тест очереди за вопросом")
    t0 = time.monotonic()
    # Используем answer_question напрямую — занимает lock на всё время генерации.
    pipeline.answer_question("Расскажи вкратце историю Рима в трёх предложениях.")  # type: ignore[attr-defined]
    print(f"  LLM-ответ закончен за {time.monotonic() - t0:.1f}с.")
    print("  Напоминание должно прозвучать сразу после.")
    input("Нажмите Enter после того, как услышите напоминание > ")


def _test_persistence_note(pipeline: "object") -> None:
    _banner("5. Персистентность — инструкция")
    from config import REMINDERS_FILE
    scheduler = pipeline.reminder_scheduler  # type: ignore[attr-defined]
    scheduler.add(120, "тест персистентности — можно игнорировать")
    print(
        f"  Добавлено напоминание на +120 секунд.\n"
        f"  Файл: {REMINDERS_FILE}\n"
        f"  Сейчас: выйдите из скрипта (пункт 9), проверьте что запись\n"
        f"  в файле есть. Запустите `python main.py` до или после fire_at —\n"
        f"  убедитесь, что напоминание срабатывает (или проигрывается\n"
        f"  сразу как просроченное, если уже прошло)."
    )


def _test_interactive_voice(pipeline: "object") -> None:
    _banner("6. Интерактив: полный CONTENT-поток через микрофон")
    print(
        "  Шаг 1 (триггер). Нажмите Enter — произнесите, например:\n"
        "    «Шурочка, поставь напоминание»\n"
        "    «Шурочка, добавь напоминание»\n"
        "  Роутер должен сматчить ReminderCommand, проиграть ack\n"
        "  «я готова добавить новое напоминание, диктуйте», затем\n"
        "  автоматически начать запись тела.\n\n"
        "  Шаг 2 (тело — уже внутри dictate()). Произнесите:\n"
        "    «напомни через десять секунд проверить кашу»\n"
        "    или без префикса: «через десять секунд проверить кашу»\n\n"
        "  Ожидание:\n"
        "    → ack-WAV reminder_before.wav\n"
        "    → автозапись тела (VAD)\n"
        "    → подтверждение «поставила напоминание через десять секунд\n"
        "      проверить кашу»\n"
        "    → через 10с: «вы хотели проверить кашу»"
    )
    input("Нажмите Enter для записи триггера > ")
    pipeline.process_voice_input()  # type: ignore[attr-defined]
    print(
        "\n  Теперь подождите до fire_at (~10с) — напоминание должно"
        "\n  прозвучать автоматически."
    )
    input("Нажмите Enter после того, как услышите «вы хотели …» > ")


# ---------- menu ----------

def main() -> int:
    menu = """
Меню check_stage_10:
  1. Юнит-тест парсера (без пайплайна)
  2. Сравнение конвертеров чисел (без пайплайна)
  3. Запустить пайплайн и создать напоминание на +10с (программно)
  4. Запустить пайплайн и протестировать очередь (напоминание за LLM)
  5. Добавить напоминание на +120с и выйти (для теста персистентности)
  6. Интерактив: произнести команду в микрофон
  9. Выход
"""
    pipeline = None
    try:
        while True:
            print(menu)
            try:
                choice = input("Выбор: ").strip()
            except EOFError:
                break
            if choice == "1":
                _test_parser()
            elif choice == "2":
                _test_num_to_words()
            elif choice in ("3", "4", "5", "6"):
                if pipeline is None:
                    pipeline = _run_pipeline()
                if choice == "3":
                    _test_schedule_now(pipeline, 10)
                elif choice == "4":
                    _test_queue_behind_answer(pipeline)
                elif choice == "5":
                    _test_persistence_note(pipeline)
                    break
                elif choice == "6":
                    _test_interactive_voice(pipeline)
            elif choice == "9":
                break
            else:
                print("Неизвестный пункт.")
    finally:
        if pipeline is not None:
            pipeline.stop()  # type: ignore[attr-defined]

    _banner("Приёмка")
    ans = input("Этап принят? (y/n): ").strip().lower()
    return 0 if ans == "y" else 1


if __name__ == "__main__":
    sys.exit(main())
