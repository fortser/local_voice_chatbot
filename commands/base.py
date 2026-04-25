"""Base types for the command subsystem.

Threading: command instances are constructed once at startup and shared across
turns. ``execute`` runs on whatever thread the router is invoked from
(usually the wake-word listener thread or the console REPL thread). Commands
must not assume single-threaded access to external resources — use the
collaborators in :class:`CommandContext` (which own their own locks) instead
of stashing mutable state on ``self``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Sequence


@dataclass
class TurnStats:
    """Накопитель метрик текущего хода для построения финального ``TurnResult``.

    CONTENT-команды делают свои собственные STT/LLM/TTS внутри ``execute()``
    (dictate второй раз, answer_question и т.п.), но эти результаты иначе
    терялись бы для UI: ``_process_voice_input_locked`` видит только
    исходную фразу-триггер. Команды пишут в этот объект через
    ``pipeline.dictate(stats=...)`` / ``pipeline.answer_question(stats=...)``,
    а pipeline собирает финальный ``TurnResult`` из накопленного.

    ``stt_ms`` суммируется по всем STT-проходам за ход (триггер + диктовка),
    ``llm_ms``/``tts_ms`` — однократные.
    """

    user_text: str = ""
    llm_text: str = ""
    wav_out: str | None = None
    stt_ms: float | None = None
    llm_ms: float | None = None
    tts_ms: float | None = None
    llm_prompt_tokens: int | None = None
    llm_completion_tokens: int | None = None

    def add_stt_ms(self, ms: float) -> None:
        self.stt_ms = (self.stt_ms or 0.0) + ms


class CommandType(Enum):
    """Coarse classification used by the router and standby state machine.

    * ``GLOBAL`` — interrupts/overrides anything in flight (Stop, Cancel).
      Checked first by the router even when another command is mid-execution.
    * ``INSTANT`` — fire-and-forget, no further user input required
      (Pause, VolumeUp, Screenshot).
    * ``CONTENT`` — needs additional user content after the trigger phrase,
      typically via ``pipeline.dictate()`` (Note, Question).
    * ``COMPOSITE`` — chains multiple steps that may include their own
      content phase (ScreenshotNote).
    """

    GLOBAL = "global"
    INSTANT = "instant"
    CONTENT = "content"
    COMPOSITE = "composite"


@dataclass
class CommandContext:
    """Everything a command may need at execution time.

    Populated by :class:`VoicePipeline` per dispatch. Fields default to
    ``None`` so M1 (skeleton) can construct a context without M2+ subsystems
    being wired up yet — each command checks for the collaborators it needs
    and gracefully degrades if they're missing.
    """

    pipeline: Any  # VoicePipeline; typed loosely to avoid an import cycle
    full_text: str
    matched_synonym: str = ""
    session_manager: Any = None  # M2
    player_manager: Any = None   # M4
    volume_control: Any = None   # M5
    ui_callback: Callable[[str, object], None] | None = None
    # Накопитель метрик хода. Заполняется ``VoicePipeline`` перед dispatch'ем;
    # CONTENT-команды передают его в ``pipeline.dictate(stats=...)`` /
    # ``pipeline.answer_question(stats=...)``, чтобы UI получил полные тайминги
    # и текст ответа, а не только трим-фразу-триггер.
    stats: TurnStats | None = None


class BaseCommand(ABC):
    """ABC for every assistant command.

    Subclasses set the three class-level attributes and implement
    :meth:`execute`. The router compares normalised text against ``synonyms``
    (the longest match wins, see :class:`commands.router.CommandRouter`).
    """

    name: str = ""
    synonyms: Sequence[str] = ()
    command_type: CommandType = CommandType.INSTANT
    # Pre-rendered ack-WAV в assets/ack/, или None — нет ack для этой фазы.
    # ``ack_before`` — играется ПЕРЕД приёмом тела команды (например, перед
    # dictate). ``ack_after`` — играется ПОСЛЕ выполнения. Утилита
    # `utils.generate_ack_phrases` собирает файлы под канонические имена
    # ``<command.name>_<phase>.wav``; команда выставляет имя файла, чтобы
    # отвязать рантайм от текстов фраз.
    ack_before: str | None = None
    ack_after: str | None = None

    @abstractmethod
    def execute(self, ctx: CommandContext) -> bool:
        """Run the command. Return True iff the command handled the input.

        Returning False signals the router to fall through to the LLM path
        (e.g. command refused because a required subsystem isn't available).
        """

    def __repr__(self) -> str:  # pragma: no cover — trivial
        return f"<{type(self).__name__} name={self.name!r} type={self.command_type.value}>"
