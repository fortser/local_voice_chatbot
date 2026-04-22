"""NoteCommand — «запиши заметку …» (M2).

Два пути:

* **Fast path** — пользователь произнёс заметку одной фразой:
  «запиши заметку купить молоко». Если после слова-маркера осталось
  ≥ ``NOTE_FAST_PATH_MIN_WORDS`` слов, считаем их содержимым заметки и
  ничего больше не записываем.

* **Dictation path** — пользователь сказал только триггер
  («запиши заметку», «новая заметка»). Зовём ``pipeline.dictate()``,
  который проигрывает бип-стартер, ждёт речь, прогоняет её через STT и
  возвращает текст. Пустой результат → таймаут, заметка не сохраняется.

Команда живёт под уже взятым ``pipeline.lock`` (router запускается
из-под него), поэтому ``dictate()`` использует RLock-режим, см.
:class:`VoicePipeline`.
"""

from __future__ import annotations

import logging

from commands.base import BaseCommand, CommandContext, CommandType
from commands.router import normalize
from config import NOTE_FAST_PATH_MIN_WORDS, WAKE_WORD, WAKE_WORD_ALIASES
from utils.errors import STTError

logger = logging.getLogger(__name__)


def _extract_tail(full_text: str, matched_synonym: str) -> str:
    """Вернуть «хвост» фразы после слова-маркера.

    Применяет ту же нормализацию, что и роутер (lower, ё→е, без пунктуации),
    срезает wake-word и сам синоним. Если хвоста нет — возвращает ``""``.
    """
    norm = normalize(full_text)
    for w in (WAKE_WORD, *WAKE_WORD_ALIASES):
        wn = w.lower().replace("ё", "е")
        if norm.startswith(wn + " "):
            norm = norm[len(wn) + 1 :]
            break
    if norm.startswith(matched_synonym + " "):
        return norm[len(matched_synonym) + 1 :].strip()
    if norm == matched_synonym:
        return ""
    # Не должно случиться (роутер уже подтвердил совпадение), но на всякий.
    return ""


class NoteCommand(BaseCommand):
    name = "note"
    command_type = CommandType.CONTENT
    ack_before = "note_before.wav"
    # ack_after намеренно None: фразу «добавила в заметки» команда играет
    # сама внутри execute(), сразу после неё — TTS-озвучка распознанного
    # текста заметки. Если бы ack_after был выставлен, внешний обработчик
    # в _process_voice_input_locked сыграл бы фразу второй раз поверх речи.
    NOTE_SAVED_ACK = "note_after.wav"
    # Длинные синонимы первыми — для читабельности; роутер всё равно
    # сортирует пары (synonym, command) по убыванию длины.
    # Все синонимы — минимум 2 слова: однословные триггеры («запиши»,
    # «заметка») цепляются на любой шум Whisper'а. Whisper стабильно
    # путает «запиши/напиши/сохрани/сделай» — поэтому держим все варианты.
    synonyms = (
        "запиши заметку",
        "напиши заметку",
        "сохрани заметку",
        "сделай заметку",
        "добавь заметку",
        "новая заметка",
    )

    def execute(self, ctx: CommandContext) -> bool:
        session = ctx.session_manager
        pipeline = ctx.pipeline
        if session is None:
            logger.warning("NoteCommand: SessionManager не передан в контекст")
            return False

        tail = _extract_tail(ctx.full_text, ctx.matched_synonym)
        words = tail.split()

        if len(words) >= NOTE_FAST_PATH_MIN_WORDS:
            note_text = tail
            logger.info(
                "NoteCommand fast-path: %d слов из inline-фразы", len(words)
            )
        else:
            try:
                note_text = pipeline.dictate(ack_filename=self.ack_before)
            except STTError:
                logger.exception("NoteCommand: STT упал во время диктовки")
                print("⚠ Диктовка не распознана.")
                return True  # «обработали»: в LLM это уходить не должно
            note_text = (note_text or "").strip()
            if not note_text:
                logger.info("NoteCommand: пустая диктовка — заметка не сохранена")
                print("⚠ Нечего записывать (тишина).")
                return True

        path = session.save_note(note_text)
        print(f"✅ Заметка сохранена: {path}")
        print(f"   «{note_text}»")
        # Голосовая верификация: «добавила в заметки» + TTS-чтение текста.
        # Так пользователь слышит, как именно Whisper распознал его слова —
        # ошибки распознавания становятся очевидны сразу.
        pipeline._play_ack(self.NOTE_SAVED_ACK)
        pipeline._speak_safely(note_text)
        return True
