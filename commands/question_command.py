"""QuestionCommand — явный путь к LLM (M2.5).

Раньше в роутере был неявный фоллбэк: если ни одна команда не сматчилась,
текст уходил в LLM. Это давало случайные многотокенные ответы на любой
шум Whisper'а («бабушка пришла» → длинный пересказ). Теперь LLM вызывается
только через эту команду — пользователь обозначает запрос явным триггером
(«ответь на вопрос …», «подскажи …», «нужна помощь …»).

Логика — зеркало :class:`NoteCommand`:

* Fast path: если после слова-маркера есть содержательный хвост
  (≥ ``QUESTION_FAST_PATH_MIN_WORDS`` слов) — отправляем хвост в LLM
  без второго раунда STT.
* Dictation path: если после маркера ничего не сказано — зовём
  ``pipeline.dictate()`` (бип, ждём вопрос, STT, передаём в LLM).
"""

from __future__ import annotations

import logging

from commands.base import BaseCommand, CommandContext, CommandType
from commands.note_command import _extract_tail
from config import QUESTION_FAST_PATH_MIN_WORDS
from utils.errors import LLMError, STTError

logger = logging.getLogger(__name__)


class QuestionCommand(BaseCommand):
    name = "question"
    command_type = CommandType.CONTENT
    ack_before = "question_before.wav"
    synonyms = (
        "ответь на вопрос",
        "нужна помощь",
        "нужна консультация",
        "дай консультацию",
        "подскажи пожалуйста",
        "объясни мне",
    )

    def execute(self, ctx: CommandContext) -> bool:
        pipeline = ctx.pipeline

        tail = _extract_tail(ctx.full_text, ctx.matched_synonym)
        words = tail.split()

        if len(words) >= QUESTION_FAST_PATH_MIN_WORDS:
            question = tail
            logger.info(
                "QuestionCommand fast-path: %d слов из inline-фразы", len(words)
            )
        else:
            try:
                question = pipeline.dictate(
                    ack_filename=self.ack_before, stats=ctx.stats
                )
            except STTError:
                logger.exception("QuestionCommand: STT упал во время диктовки")
                print("⚠ Вопрос не распознан.")
                return True
            question = (question or "").strip()
            if not question:
                logger.info("QuestionCommand: пустая диктовка — ничего не спрашиваем")
                print("⚠ Нечего спрашивать (тишина).")
                return True

        print(f"❓ «{question}»")
        # Если был fast-path (диктовка не вызывалась) — заполнить user_text
        # вручную, чтобы UI показал именно вопрос, а не фразу-триггер.
        if ctx.stats is not None and question:
            ctx.stats.user_text = question
        try:
            pipeline.answer_question(question, stats=ctx.stats)
        except LLMError:
            # answer_question уже озвучил FALLBACK_LLM_ERROR; здесь просто
            # помечаем, что команда «обработала» вход (в LLM повторно не идём).
            pass
        return True
