"""Per-session mute через pycaw (M4).

Идея: пользователь говорит «выключи звук» → заглушаем все аудио-сессии
Windows, **кроме своей собственной** (Шурочка должна продолжать
говорить). На «включи звук» — снимаем mute с тех сессий, что мы сами
заглушили (не трогая те, что пользователь muted руками заранее).

Тонкости:

* COM **инициализируется per-call** (CoInitializeEx + CoUninitialize в
  finally). Это медленнее, чем держать выделенный COM-поток, но
  надёжнее: 50–100 мс на вызов → невидимая пользователю задержка для
  голосовой команды. Если когда-нибудь упрёмся в гонку или утечку —
  переедем на dedicated COM worker (план M5/Q-таблица).
* **Persistent state не сохраняется на диск.** Если процесс упадёт с
  заглушёнными сессиями — пользователь снимет mute через системный
  микшер (Win+B → правый клик на громкости → «Открыть микшер
  громкости»). При штатном выключении Шурочки — `restore_all()` снимает
  всё, что мы заглушили.
* **Идемпотентность:** двойной mute не падает; список заглушённых
  не растёт сверх реального количества сессий.
"""

from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)

# Импорт лениво в методах: pycaw тащит comtypes, который инициализирует
# COM при импорте. Это безопасно, но мы хотим, чтобы импорт модуля был
# дешёвым (на случай, если кто-то импортирует system.* в тестах).


class MuteController:
    """Заглушает все чужие аудио-сессии Windows и снимает обратно."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Запоминаем sessionInstanceIdentifier'ы заглушённых сессий, чтобы
        # на unmute снять mute строго с них и не зацепить то, что
        # пользователь приглушил сам ранее.
        self._muted_keys: set[str] = set()
        self._self_pid = os.getpid()

    # ---- public ----

    def mute_others(self) -> int:
        """Заглушить все аудио-сессии, кроме собственной. Вернуть кол-во заглушённых."""
        with self._lock:
            return self._with_com(self._mute_others_locked)

    def unmute_others(self) -> int:
        """Снять mute с тех сессий, что мы сами заглушили. Вернуть кол-во."""
        with self._lock:
            return self._with_com(self._unmute_others_locked)

    def restore_all(self) -> None:
        """Снять mute со всех ранее заглушённых нами сессий. Идемпотентно.

        Вызывается при остановке Шурочки. Если ничего не было заглушено —
        пустая операция.
        """
        if not self._muted_keys:
            return
        try:
            self.unmute_others()
        except Exception:
            logger.exception("MuteController.restore_all failed")

    @property
    def has_muted(self) -> bool:
        return bool(self._muted_keys)

    # ---- internals ----

    def _with_com(self, fn):
        """Запустить ``fn()`` в инициализированном COM-контексте текущего потока.

        Используем `comtypes.CoInitialize` (STA = COINIT_APARTMENTTHREADED), а
        не `pythoncom.CoInitializeEx(MULTITHREADED)`. Причина: pycaw тащит
        comtypes, который при первом импорте на потоке инициализирует COM в
        STA. Если потом попробовать переинициализировать в MTA, Win32 кидает
        `RPC_E_CHANGED_MODE` («изменение режима для потока невозможно»).
        STA-режим даёт нам совместимость с уже инициализированным COM и не
        требует pywin32 как зависимость.
        """
        import comtypes  # noqa: PLC0415 — ленивый импорт намеренно

        # Идемпотентно: если COM уже инициализирован в STA на этом потоке,
        # вернётся S_FALSE, мы всё равно сбалансируем CoUninitialize.
        try:
            comtypes.CoInitialize()
        except OSError:
            logger.exception("CoInitialize failed; пробуем работать без явной инициализации")
            return fn()
        try:
            return fn()
        finally:
            try:
                comtypes.CoUninitialize()
            except OSError:
                logger.exception("CoUninitialize failed")

    def _mute_others_locked(self) -> int:
        from pycaw.pycaw import AudioUtilities  # noqa: PLC0415

        sessions = AudioUtilities.GetAllSessions()
        muted_now = 0
        for s in sessions:
            try:
                proc = s.Process
            except Exception:
                continue
            if proc is None:
                # Сессии без процесса — системные звуки Windows; не трогаем.
                continue
            if proc.pid == self._self_pid:
                # Это сама Шурочка (Python-интерпретатор) — пропускаем.
                continue

            volume = s.SimpleAudioVolume
            try:
                already_muted = bool(volume.GetMute())
            except Exception:
                logger.exception("Failed to read mute state for pid=%s", proc.pid)
                continue
            if already_muted:
                # Эту сессию пользователь muted сам — не «заявляем» её
                # своей, чтобы при unmute не дёрнуть её.
                continue

            try:
                volume.SetMute(1, None)
            except Exception:
                logger.exception("Failed to mute pid=%s", proc.pid)
                continue
            key = self._session_key(s, proc)
            self._muted_keys.add(key)
            muted_now += 1
            logger.info(
                "Muted session: pid=%s name=%s",
                proc.pid, getattr(proc, "name", lambda: "?")(),
            )
        logger.info("mute_others: заглушено %d сессий (всего трекаем %d)",
                    muted_now, len(self._muted_keys))
        return muted_now

    def _unmute_others_locked(self) -> int:
        from pycaw.pycaw import AudioUtilities  # noqa: PLC0415

        if not self._muted_keys:
            return 0
        sessions = AudioUtilities.GetAllSessions()
        unmuted_now = 0
        still_muted: set[str] = set()
        for s in sessions:
            try:
                proc = s.Process
            except Exception:
                continue
            if proc is None:
                continue
            key = self._session_key(s, proc)
            if key not in self._muted_keys:
                continue
            try:
                s.SimpleAudioVolume.SetMute(0, None)
                unmuted_now += 1
                logger.info(
                    "Unmuted session: pid=%s name=%s",
                    proc.pid, getattr(proc, "name", lambda: "?")(),
                )
            except Exception:
                logger.exception("Failed to unmute pid=%s", proc.pid)
                still_muted.add(key)
        # Для сессий, которые исчезли (плеер закрылся) — забываем их.
        # Оставляем в треке только те, что не удалось снять.
        self._muted_keys = still_muted
        logger.info("unmute_others: снято %d, осталось %d",
                    unmuted_now, len(self._muted_keys))
        return unmuted_now

    @staticmethod
    def _session_key(session, proc) -> str:
        """Стабильный ключ сессии для трекинга между mute/unmute."""
        # InstanceIdentifier меняется реже, чем PID (тот же плеер при
        # переоткрытии получает новую сессию). Если недоступен —
        # фоллбэк на pid+name.
        try:
            iid = session.InstanceIdentifier
            if iid:
                return iid
        except Exception:
            pass
        try:
            return f"{proc.pid}:{proc.name()}"
        except Exception:
            return f"{proc.pid}"
