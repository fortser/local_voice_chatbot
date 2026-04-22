# План миграции функционала «Шурочка» в shura v2

**Задача:** перенести в этот проект весь прикладной функционал утраченной
«Шурочки» — команды (заметки, скриншоты, управление плеером, громкость,
перемотка), SessionManager, интеграция с VLC/MPC/YouTube, системный трей,
overlay-окно. Wake word, STT, TTS, LLM, VAD, audio I/O **уже есть** в shura v2
и переиспользуются без изменений.

**Принцип:** каждый этап заканчивается `check_stage_<код>.py`, который
пользователь запускает вручную и отмечает чек-лист приёмки. Без успешной
валидации следующий этап не начинается. Правила скриптов — как в
`DEVELOPMENT_PLAN.md` (секция «Правило ручной валидации»).

**Исходные материалы (не терять):**
- `T:\test_python\shurochka\CLAUDE.md` — архитектура «Шурочки»
- `T:\test_python\shurochka\docs\rosy-herding-sonnet.md` — детальный план «Шурочки»
- `T:\test_python\shurochka\tests\test_*.py` — 13 тест-файлов, фактически
  спецификация API (command_parser, state_machine, players, volume_control,
  audio_feedback, overlay, tray и т.д.)
- `T:\test_python\shurochka\commands\executor.py` — уцелевший живой исходник
  (стиль и интерфейс команды)

Эти файлы — ориентир по сигнатурам и поведению, но **слепо не копируем**:
архитектура shura v2 другая (provider pattern, VoicePipeline, lock,
`WakeWordListener`), интегрируем новый функционал в неё.

---

## Обзор этапов

| Этап | Название | Что добавляется | Приёмка |
|---|---|---|---|
| M1 | Каркас и роутер команд | Пакеты `commands/`, `system/`, `players/`; CommandRouter; интеграция в VoicePipeline | `check_stage_m1.py` |
| M2 | SessionManager + «запиши заметку» | `system/session_manager.py`, NoteCommand с диктовкой | `check_stage_m2.py` |
| M3 | Скриншоты | `system/screenshot.py` (mss), ScreenshotCommand | `check_stage_m3.py` |
| M4 | Управление плеером (VLC/MPC/YouTube) | `players/` с детектором, пауза/продолжить | `check_stage_m4.py` |
| M5 | Громкость (pycaw COM worker) | `system/volume_control.py`, mute/громче/тише | `check_stage_m5.py` |
| M6 | Перемотка + остановка + отмена | Seek ±, StopCommand, CancelCommand | `check_stage_m6.py` |
| M7 | Композитная команда «скриншот-заметка» | ScreenshotNoteCommand | `check_stage_m7.py` |
| M8 | Overlay + SystemTray | Tkinter Toplevel поверх окон, pystray | `check_stage_m8.py` |
| M9 | LLM fallback + fuzzy matching | Догонка парсера командами и LLM при пропуске | `check_stage_m9.py` |
| M10 | Q&A команда + полировка | «Шурочка, ответь на вопрос …» в LLM, серийный режим | `check_stage_m10.py` |

Предполагаемый объём: M1–M10, каждый этап — 1 рабочая сессия.

---

## Этап M1 — Каркас и роутер команд

**Цель:** завести структуру пакетов и прослойку `CommandRouter`. После wake
word и STT текст фразы уходит в роутер: если распознана команда — она
выполняется (пока все команды-заглушки), иначе — в LLM как сейчас.

**Что делаем:**
1. Создать пакеты:
   - `commands/` (`__init__.py`, `base.py`, `registry.py`, `router.py`)
   - `system/` (`__init__.py`)
   - `players/` (`__init__.py`)
2. `commands/base.py`:
   - `BaseCommand` — ABC с `name: str`, `synonyms: tuple[str, ...]`,
     `command_type: CommandType`, `execute(ctx) -> bool`
   - `CommandType` (enum: `GLOBAL`, `INSTANT`, `CONTENT`, `COMPOSITE`)
   - `CommandContext` — dataclass (pipeline, session_manager, player_manager,
     volume_control, ui_callback, full_text)
3. `commands/registry.py` — `CommandRegistry` (name→command), `build_default_registry()`
4. `commands/router.py` — `CommandRouter`:
   - `parse(text) -> BaseCommand | None` — MVP: точное совпадение и startswith
     по синонимам (нормализация: lower, ё→е, убрать пунктуацию)
   - `dispatch(text, ctx) -> bool` — парсит, выполняет, True если сработало
5. Заглушки команд (каждая только логирует и возвращает True):
   `PauseCommand`, `ResumeCommand`, `VolumeUpCommand`, `VolumeDownCommand`,
   `MuteCommand`, `SeekForwardCommand`, `SeekBackwardCommand`, `StopCommand`,
   `CancelCommand`, `ScreenshotCommand`, `NoteCommand`, `QuestionCommand`
6. `config.py` — добавить:
   - `COMMAND_PARSE_FUZZY_THRESHOLD = 0.80` (на потом)
   - `COMMAND_LLM_FALLBACK = False` (M9 включит)
7. Интеграция в `main.py`:
   - `VoicePipeline` получает `registry` и `router`
   - В `wake_word` ветке после STT: сначала `router.dispatch(text, ctx)`;
     если вернул False — прежний путь в LLM
   - Внутри `CommandContext` — все необходимые ссылки

**Что нельзя делать:** не трогаем `core/wake_word.py`, `core/vad.py`,
`core/stt.py`, `core/tts.py`, провайдеров LLM. Не добавляем реальной логики
команд — только каркас и диспетчеризация.

**check_stage_m1.py:**
- Запуск: `python check_stage_m1.py`
- Без микрофона. Вручную вызывает `router.dispatch(...)` с набором фраз:
  «пауза», «громче», «сделай скриншот», «произвольный вопрос»
- Печатает: какая команда выбрана / `None` / путь в LLM
- Критерии приёмки:
  - [ ] Команды сопоставляются по точному имени и по синонимам
  - [ ] Нормализация работает (проверка «Пауза.», «ПАУЗА», «пауза»)
  - [ ] Незнакомая фраза возвращает `None` (пойдёт в LLM)
  - [ ] Логи показывают правильное имя команды и `command_type`
  - [ ] Запуск `python main.py --mode console` не сломан: wake word + LLM
    по-прежнему работают для не-команд

---

## Этап M2 — SessionManager и «запиши заметку»

**Цель:** первая реальная команда. `NoteCommand` принимает фразу, после
триггера переходит в режим диктовки (VAD с более длинной тишиной),
записанный текст сохраняется в файл сессии.

**Что делаем:**
1. `system/session_manager.py`:
   - `SessionManager` — создаёт папку `~/Shura/<timestamp>/` на первый
     вызов, держит текущую сессию, `save_note(text)`, `save_screenshot(img)`
   - Имя папки: `YYYY-MM-DD_HH-MM`
   - Конфиг: `SESSION_BASE_DIR` в `config.py` (`~/Shura` по умолчанию)
2. `core/vad.py` — **не менять интерфейс**, но добавить метод/режим «диктовка»
   с более длинной паузой (5с), если такого ещё нет. Если уже есть
   `record_until_silence(pause_threshold=5.0, max_duration=60.0)` — используем.
3. `commands/note_command.py`:
   - `NoteCommand(command_type=CONTENT)`
   - Синонимы: «запиши», «запиши заметку», «новая заметка», «заметка»
   - Fast path: если после слова-маркера в `full_text` ≥ 3 слов — берём их как
     контент, без диктовки
   - Иначе: вызываем `ctx.pipeline.dictate()` → STT → записываем в сессию
4. `VoicePipeline.dictate()` — новый метод (с блокировкой `pipeline.lock`):
   VAD запись с длинной паузой → Whisper → вернуть текст
5. UI-feedback: короткий beep + отображение «🎤 Диктуйте заметку» в UI
   (через тот же механизм, что `WakeWordListener` уже использует)

**check_stage_m2.py:**
- Запуск: `python check_stage_m2.py`
- Автономный: сам инициализирует pipeline без UI, сам открывает wake word,
  ждёт срабатывания на «Шурочка»
- Инструкции пользователю прямо в скрипте: «скажите "Шурочка, запиши
  заметку купить молоко"», «скажите "Шурочка, запиши заметку", потом
  продиктуйте»
- Критерии приёмки:
  - [ ] Fast path работает: «Шурочка, запиши заметку купить молоко» →
    в файле сессии появляется «купить молоко»
  - [ ] Диктовка работает: «Шурочка, запиши заметку» → бип → голос
    фиксируется до 5с тишины → текст сохранён
  - [ ] Папка сессии создана в `~/Shura/<timestamp>/`, внутри — текстовый
    файл заметки
  - [ ] Повторный «запиши заметку» в той же сессии добавляет **новую**
    заметку (или дописывает — по договорённости; в скрипте проверяется
    выбранное поведение)
  - [ ] Без голоса после активации → таймаут → отмена + сообщение
    в логе/UI

---

## Этап M3 — Скриншоты

**Цель:** команда «сделай скриншот» / «скриншот» сохраняет PNG в папку сессии.

**Что делаем:**
1. `pip install mss` (в `requirements.txt`)
2. `system/screenshot.py`:
   - `take_screenshot(monitor: int | None = None) -> bytes` (PNG)
3. `SessionManager.save_screenshot(data: bytes) -> Path` — имя
   `screenshot_<timestamp>.png`
4. `commands/screenshot_command.py`:
   - `ScreenshotCommand(command_type=INSTANT)`
   - Синонимы: «скриншот», «сделай скриншот», «сфоткай», «сфотографируй»
   - `execute`: берёт скриншот → сохраняет → short beep → готово

**check_stage_m3.py:**
- Предлагает пользователю сказать «Шурочка, сделай скриншот»
- Открывает папку сессии в Проводнике через `os.startfile` (чтобы
  пользователь визуально увидел файл)
- Критерии:
  - [ ] В папке сессии появился `screenshot_*.png`
  - [ ] Файл открывается, изображение соответствует тому, что было на экране
  - [ ] Повторный вызов добавляет новый файл, не перетирает старый
  - [ ] Многомониторная конфигурация: сохраняется основной монитор
    (если критично — обсудить)

---

## Этап M4 — Управление плеером (VLC / MPC-HC / YouTube)

**Цель:** команды «пауза» / «продолжи» действуют на активный медиаплеер.

**Что делаем:**
1. `players/base.py` — `PlayerBase` (ABC: `is_running`, `pause`, `resume`, `seek`, `get_pid`)
2. `players/vlc_player.py` — HTTP API на `localhost:8080` (токен в config)
3. `players/mpc_player.py` — HTTP API на `localhost:13579`
4. `players/youtube_player.py` — `pygetwindow` + `pydirectinput` (пробел для
   паузы, ← → для перемотки)
5. `players/player_manager.py`:
   - `PlayerManager` — по `config.PLAYERS_PRIORITY` опрашивает плееры,
     возвращает первый работающий; методы `pause()`, `resume()`, `seek(±sec)`
6. Конфиг: `PLAYERS_PRIORITY = ["vlc", "mpc", "youtube"]`,
   `VLC_PORT=8080`, `VLC_PASSWORD=""`, `MPC_PORT=13579`, `YOUTUBE_SEEK_STEP=5`
7. Обновить `PauseCommand`, `ResumeCommand` — делегируют в PlayerManager
8. Fail-safe: если ни один плеер не отвечает — команда возвращает False,
   TTS-ответ «Плеер не найден»

**check_stage_m4.py:**
- Инструкция: «запустите VLC с видео, нажмите "Шурочка, пауза"»
- Критерии:
  - [ ] VLC: пауза/продолжить срабатывают, лаг < 500 мс
  - [ ] MPC-HC: то же самое
  - [ ] YouTube в активном окне Chrome/Firefox: пауза/продолжить через
    пробел (если активно другое окно — не должно ломать)
  - [ ] Без плееров: команда вежливо говорит «Плеер не найден», скрипт
    не падает

---

## Этап M5 — Громкость (pycaw COM worker)

**Цель:** «громче», «тише», «без звука», «со звуком» — влияют только на
текущий плеер (per-process mute через pycaw).

**Что делаем:**
1. `pip install pycaw comtypes`
2. `system/volume_control.py`:
   - `VolumeControl` — запускает **выделенный COM-поток** (STA), все вызовы
     маршалятся через `queue.Queue`. Методы: `mute_pid(pid)`,
     `unmute_pid(pid)`, `volume_up()`, `volume_down()`, `set_master(pct)`
   - Отдельный поток обязателен — pycaw чувствителен к COM-инициализации
3. Конфиг: `VOLUME_STEP = 10` (%)
4. Команды: `VolumeUpCommand`, `VolumeDownCommand`, `MuteCommand`,
   `UnmuteCommand` — вызывают VolumeControl с `pid = player_manager.get_pid()`
5. Обязательно: `VolumeControl.stop()` вызывается при выходе и **снимает
   mute** со всех приложений, которые были заглушены

**check_stage_m5.py:**
- Запустить музыку в VLC, сказать «Шурочка, без звука» — VLC замолчал,
  остальные приложения играют
- Критерии:
  - [ ] Mute/unmute работает **только** для текущего плеера
  - [ ] Громче/тише шагом 10% относительно системного
  - [ ] Двойной mute — идемпотентен (не падает)
  - [ ] После `Ctrl+C` все приложения восстановили звук

---

## Этап M6 — Перемотка, остановка, отмена

**Цель:** «перемотай вперёд» / «назад», «отмена», «остановись».

**Что делаем:**
1. `SeekForwardCommand`, `SeekBackwardCommand` (INSTANT):
   - Шаг из `SEEK_STEP_SECONDS = 5`
   - Делегируют в `PlayerManager.seek(±step)`
2. `StopCommand` (GLOBAL):
   - Прерывает любую команду в процессе, возвращает Pipeline в idle,
     деактивирует standby (wake word)
3. `CancelCommand` (GLOBAL):
   - Отменяет текущую команду в состоянии ожидания диктовки/параметра
     (если оно есть), но не выключает standby
4. **Global** команды проверяются роутером до всех остальных (даже когда
   идёт диктовка)

**check_stage_m6.py:**
- Критерии:
  - [ ] «Шурочка, перемотай вперёд» в VLC — видео уезжает на +5с
  - [ ] «Шурочка, перемотай назад» — -5с
  - [ ] Во время диктовки заметки «Шурочка, отмена» — заметка не
    сохранена, pipeline вернулся в ожидание
  - [ ] «Шурочка, остановись» — wake word выключен (UI показывает idle)

---

## Этап M7 — Композитная команда «скриншот-заметка»

**Цель:** одна команда делает скриншот + принимает надиктованный комментарий
и сохраняет их как пару.

**Что делаем:**
1. `commands/screenshot_note_command.py` (COMPOSITE):
   - Синонимы: «скриншот-заметка», «сфотографируй и запиши», «сделай
     скриншот и запиши заметку»
   - Последовательность: `take_screenshot()` → `ctx.pipeline.dictate()` →
     `session.save_screenshot_note(image, text)`
2. `SessionManager.save_screenshot_note(image, text)` — PNG + TXT с общим
   именем

**check_stage_m7.py:**
- Критерии:
  - [ ] В сессии появились `screenshot_note_<ts>.png` и `.txt` (или
    эквивалент — текст+картинка с одинаковым префиксом)
  - [ ] Fast path с инлайн-текстом работает
  - [ ] Отмена во время диктовки — скриншот удаляется (или помечается
    как сирота — по договорённости, проверяется в скрипте)

---

## Этап M8 — Overlay-окно и SystemTray

**Цель:** небольшое полупрозрачное окно в углу экрана, отображающее
состояние ассистента; иконка в системном трее с меню.

**Что делаем:**
1. `ui/overlay.py` — `Overlay` (Tkinter `Toplevel`):
   - Always-on-top, frameless, alpha 0.85
   - Позиция из конфига: `OVERLAY_POSITION = "top_right"`
   - Обновляется через `queue.Queue` из фонового потока pipeline
   - Состояния: Пассивен / Слышу / Обрабатываю / Отвечаю / Диктуйте
2. `ui/tray.py`:
   - `pip install pystray Pillow`
   - `SystemTray` — иконка, меню: Пауза ассистента / Открыть папку сессии /
     Перезагрузить конфиг / Выход
3. Интеграция в `main.py --mode ui` (или новый режим `--mode overlay`):
   - Overlay на главном потоке Tkinter, трей — daemon thread
   - `on_quit` → корректный shutdown Pipeline + WakeWord + VolumeControl

**check_stage_m8.py:**
- Критерии:
  - [ ] Overlay виден, не мешает (не перехватывает клики)
  - [ ] Состояние меняется в реальном времени при работе
  - [ ] Правый клик на иконку в трее показывает меню
  - [ ] «Выход» из трея — программа завершается за < 2с, все потоки
    остановлены (проверить через Диспетчер задач)

---

## Этап M9 — Нечёткое совпадение и LLM fallback для команд

**Цель:** команда должна срабатывать даже при неточном произношении или
необычной формулировке.

**Что делаем:**
1. Расширить `CommandRouter.parse`:
   - Точное → startswith (длинные синонимы сначала) → `difflib.get_close_matches`
     с порогом `COMMAND_PARSE_FUZZY_THRESHOLD = 0.80`
2. LLM fallback (если включён `COMMAND_LLM_FALLBACK = True`):
   - Промпт: «Определи команду из списка: [...]. Фраза: "{text}". Верни
     только имя или NONE.»
   - Ограничение: только когда все предыдущие шаги вернули None
   - Таймаут 1.5с — иначе считаем NONE
3. Логировать каждый шаг распознавания (exact/startswith/fuzzy/llm/none)

**check_stage_m9.py:**
- Критерии:
  - [ ] «сфоткай экран» → ScreenshotCommand через fuzzy
  - [ ] «сделай заметочку про молоко» → NoteCommand
  - [ ] «уменьши звук» → VolumeDownCommand через LLM fallback
  - [ ] Совсем странная фраза — уходит в LLM (Q&A), не в команду

---

## Этап M10 — Q&A команда и полировка

**Цель:** привести поведение близко к «Шурочке» — явная команда «ответь на
вопрос», серийный режим (несколько команд подряд без повторного wake word).

**Что делаем:**
1. `QuestionCommand` (CONTENT): «ответь на вопрос», «что такое…», «скажи…»
   — делегирует в существующий LLM-путь с явным маркером «вопрос»
2. Серийный режим в `WakeWordListener`:
   - После выполнения команды — 4с ждать следующую без повторного wake
   - Таймаут 4с → возврат в passive
3. «Жду команду» / «Отключаюсь» — голосовые подсказки через TTS
4. Проверка: session удобно закрывается командой «Шурочка, закончи сессию»

**check_stage_m10.py:**
- Критерии:
  - [ ] Серия «Шурочка, запиши заметку молоко», потом без wake —
    «сделай скриншот», «громче» — отрабатывает
  - [ ] После 4с тишины — TTS «Отключаюсь», listener в idle
  - [ ] «Шурочка, ответь на вопрос, столица Франции» — LLM отвечает,
    не NoteCommand

---

## Соглашения по коду

- Каждый новый файл — докстринг с описанием модуля и потокобезопасности
- Новые пакеты — `__init__.py` с фабриками (`build_default_registry`,
  `create_player_manager` и т.д.) — как `core/__init__.py` делает для провайдеров
- Тесты для новых модулей — рядом в `tests/test_<module>.py`
- `check_stage_<код>.py` — в корне, удаляется после приёмки (как сейчас
  делают этапы shura v2)
- Не менять публичный API существующих модулей (`WakeWordListener`,
  `VoicePipeline`, провайдеры) без явной необходимости — только расширять
- Русский язык в UI/логах, английский — в докстрингах и технических
  сообщениях (как уже принято в проекте)

---

## Как начать следующую сессию

1. Открыть этот файл, прочитать шапку и обзор этапов
2. Открыть `DEVELOPMENT_PLAN.md` — ознакомиться с правилами `check_stage_N.py`
3. Принять решение: стартуем с M1 или что-то корректируем в плане
4. В конце каждого этапа — запустить `check_stage_<код>.py`, подтвердить
   критерии, удалить скрипт, пометить этап галочкой в таблице обзора выше
