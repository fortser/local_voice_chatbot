# План: голосовое управление окном терминала с Claude Code

> Статус: **согласовано, разработка отложена.** Этот документ самодостаточен —
> новой сессии достаточно прочитать его, чтобы сразу приступить к реализации.
> Дата согласования: 2026-05-30.

## 1. Зачем (мотивация и сценарий)

Пользователь смотрит YouTube в одном окне, а рядом, в **отдельном окне Windows
Terminal**, работает Claude Code (разработка / code review его проектов). Claude
периодически останавливается и **спрашивает подтверждения** действия. Сейчас,
чтобы продолжить, надо тянуться мышью к другому окну.

Идея: добавить в Шурочку голосовые команды, которые переключают фокус на окно
терминала, эмулируют нужное нажатие клавиш (чтобы Claude продолжил), и
возвращают фокус обратно на окно YouTube.

### Жёсткие предпосылки сценария (важны для оценки рисков)

- Используется **только** когда на экране одновременно видны два окна
  **side-by-side**. Полноэкранного режима (fullscreen) не подразумевается.
- **Человек в контуре:** пользователь даёт команду только тогда, когда сам
  видит глазами, что Claude остановился и что именно спрашивает. Это не
  автоматизация вслепую — это исполнение осознанного решения пользователя.
- Следствие: риск «слепого Enter» (подтвердить деструктив, не прочитав вопрос)
  практически снят самим сценарием использования. Соответствует принципу
  «уведомлять/исполнять, а не угадывать» (memory `feedback_avoid_complex_auto`).

## 2. Принятые решения (зафиксировано в обсуждении)

| Вопрос | Решение |
|---|---|
| Поиск окна терминала | **По имени процесса** `WindowsTerminal.exe` |
| Контроль содержимого запроса | **Слепой Enter** (вариант A), без OCR. Безопасность обеспечивает «человек в контуре» |
| Набор команд | **Две** команды (см. ниже) |
| Возврат фокуса | **Да**, после каждой команды фокус возвращается на окно, которое было активным до переключения (окно YouTube) |
| Способ переключения фокуса | `SetForegroundWindow` + `SendInput` (см. раздел 4) |
| Новые зависимости | **Нет.** Всё на `ctypes`, по образцу `system/media_keys.py` |

### Две команды

1. **`give_permission`** — синоним(ы): `«даю разрешение»`.
   Действие: эмулировать одиночное нажатие **Enter** в окне терминала.
   Смысл: однократно подтвердить текущий запрос Claude (выбрать подсвеченный
   по умолчанию пункт меню подтверждения, обычно «Yes»).

2. **`give_continuation`** — синоним(ы): `«даю продолжение»`.
   Действие: **напечатать текст «продолжай»** в окне терминала, затем **Enter**.
   Смысл: когда Claude закончил этап и ждёт в обычном промпте — дать команду
   перейти к следующему этапу.

> Состояние Claude (открыто меню подтверждения vs. обычный промпт) пользователь
> различает сам и выбирает правильную команду — точно так же, как в
> `system/media_keys.py` pause/resume это один и тот же toggle, а пользователь
> говорит подходящую фразу под текущее состояние плеера. Никакого авто-детекта
> состояния НЕ делаем (хрупко, противоречит `feedback_avoid_complex_auto`).

## 3. Почему именно этот способ переключения фокуса (итог дискуссии 3 экспертов)

Рассматривались три школы:

1. **`SetForegroundWindow` + `SendInput`** (переключение фокуса). ✅ Выбрано.
2. **Без переключения фокуса** — `PostMessage`/`WriteConsoleInput` напрямую в
   окно. ❌ Отклонено: Windows Terminal на ConPTY **не слушает** `PostMessage`
   надёжно; `WriteConsoleInput` требует `AttachConsole(pid)`, что конфликтует с
   режимом `--mode console` Шурочки и хрупко.
3. **Высокоуровневый фреймворк** (`pywinauto`/UIA). ❌ Отклонено: тяжёлая новая
   зависимость, тянет `comtypes` и рискует конфликтовать с нашей STA-инициализацией
   COM (memory `feedback_com_init_sta`); UIA на WT капризна; для «нажать Enter» —
   избыточно.

**Ключевой объективный факт, решивший спор:** цель — Windows Terminal поверх
ConPTY, а он надёжно принимает ввод **только через `SendInput` при наличии
фокуса**. Поэтому доставка клавиш = `SendInput` с реальным фокусом; спор был лишь
о том, как добывать фокус. Победил способ, который ложится на уже существующий
`SendInput`-код и не тянет зависимостей.

## 4. Архитектура и реализация

Пайплайн действия одной команды:

```
fg = GetForegroundWindow()          # запомнить окно YouTube (активное сейчас)
terminal = find_terminal_window()   # HWND процесса WindowsTerminal.exe
activate(terminal)                  # выдвинуть терминал на передний план (с фокусом)
send_keys(...)                      # Enter  ИЛИ  type_unicode("продолжай") + Enter
activate(fg)                        # вернуть фокус на окно YouTube
```

### 4.1 Снятие foreground-lock

Windows блокирует `SetForegroundWindow` из фонового процесса (foreground lock).
Шурочка срабатывает по голосу, а не по клику, поэтому под блокировку попадает.

**Основной приём (чистый, из горячего пути убран):** разово при старте Шурочки
вызвать
```
SystemParametersInfo(SPI_SETFOREGROUNDLOCKTIMEOUT, 0, 0, SPIF_SENDCHANGE)
# SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
```
После этого обычный `SetForegroundWindow` проходит без пер-вызовных хаков.
Делать в `bootstrap()`-фазе entry point'ов (см. CLAUDE.md: bootstrap обязателен).

**Фолбэк (двухуровневая надёжность):** после `SetForegroundWindow` проверить
`GetForegroundWindow() == terminal`. Если нет — применить `AttachThreadInput`-приём:
```
cur_tid = GetCurrentThreadId()
tgt_tid = GetWindowThreadProcessId(terminal, NULL)
AttachThreadInput(cur_tid, tgt_tid, TRUE)
SetForegroundWindow(terminal); BringWindowToTop(terminal)
AttachThreadInput(cur_tid, tgt_tid, FALSE)   # ОБЯЗАТЕЛЬНО отсоединить
```

### 4.2 Поиск окна по процессу

На `ctypes`, без новых зависимостей:
- `EnumWindows(callback, 0)` — перебрать top-level окна.
- Для каждого HWND: `IsWindowVisible(hwnd)` → отфильтровать невидимые.
- `GetWindowThreadProcessId(hwnd, byref(pid))` → получить PID.
- Сопоставить PID с именем процесса. Имя процесса достать через
  `QueryFullProcessImageNameW` (`OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`)
  — без новых зависимостей. (Если в проекте УЖЕ есть `psutil` — можно через него,
  но проверить requirements.txt; по умолчанию НЕ добавлять зависимость.)
- Имя целевого процесса берётся из конфига (`TERMINAL_PROCESS_NAME`).

У пользователя одно окно WT → берём первый подходящий видимый HWND. Если найдено
несколько — лог + берём первый (на будущее см. раздел 7 «запомни терминал»).
Если не найдено — команда возвращает `False` + проигрывает «не нашла окно» / бип.

### 4.3 Эмуляция клавиш — расширение `system/media_keys.py`

В `media_keys.py` уже есть вся `SendInput`-инфраструктура (`_INPUT`, `_KEYBDINPUT`,
`_send_key_event`, `_press_key`). Достроить:

- `VK_RETURN = 0x0D`; функция `press_enter()` через существующий `_press_key`.
- Печать Unicode-строки (для «продолжай», кириллица в любой раскладке):
  через `SendInput` с `KEYEVENTF_UNICODE` (`wVk = 0`, `wScan = ord(char)`).
  ```
  KEYEVENTF_UNICODE = 0x0004
  # на каждый символ: keydown(unicode) + keyup(unicode)
  ```
  Функция `type_unicode(text: str, inter_char_delay_ms: int)`.
- Небольшая задержка между активацией окна и началом ввода (окно должно
  фактически получить фокус) — `FOCUS_SETTLE_DELAY_MS` (~50–100 мс).

> Решить при разработке: расширять `media_keys.py` (там уже есть SendInput) или
> вынести оконную часть в новый `system/window_control.py`, а низкоуровневую
> печать оставить в `media_keys.py`. Рекомендация: **новый модуль
> `system/window_control.py`** для поиска/активации/возврата фокуса; печать и
> VK_RETURN — в `media_keys.py` (рядом с остальным SendInput).

### 4.4 Новый модуль `system/window_control.py` (предлагаемый API)

```python
def find_window_by_process(process_name: str) -> int | None: ...
    # вернуть HWND первого видимого top-level окна процесса, или None

def get_foreground_window() -> int: ...

def activate_window(hwnd: int) -> bool: ...
    # SetForegroundWindow + проверка + AttachThreadInput-фолбэк; True если фокус получен

def disable_foreground_lock() -> None: ...
    # SPI_SETFOREGROUNDLOCKTIMEOUT=0; вызвать один раз в bootstrap()
```

### 4.5 Команды — `commands/terminal_control_command.py` (новый файл)

По образцу `commands/screenshot_command.py` (INSTANT, ack_after). Обе команды:

```python
class GivePermissionCommand(BaseCommand):
    name = "give_permission"
    command_type = CommandType.INSTANT
    synonyms = ("даю разрешение",)
    ack_after = "give_permission_after.wav"   # или общий звук подтверждения

    def execute(self, ctx) -> bool:
        from system.window_control import (
            find_window_by_process, get_foreground_window, activate_window,
        )
        from system.media_keys import press_enter
        from config import TERMINAL_PROCESS_NAME, TERMINAL_RETURN_FOCUS
        term = find_window_by_process(TERMINAL_PROCESS_NAME)
        if term is None:
            logger.warning("Окно терминала не найдено")
            return False
        prev = get_foreground_window()
        if not activate_window(term):
            return False
        press_enter()
        if TERMINAL_RETURN_FOCUS:
            activate_window(prev)
        return True


class GiveContinuationCommand(BaseCommand):
    name = "give_continuation"
    command_type = CommandType.INSTANT
    synonyms = ("даю продолжение",)
    ack_after = "give_continuation_after.wav"
    # то же, но вместо press_enter():  type_unicode(TERMINAL_CONTINUE_TEXT); press_enter()
```

> ⚠️ Напоминание про реестр команд (`commands/registry.py`): каждый синоним
> должен содержать **≥2 слова**, иначе `CommandRegistry.register` падает
> (memory `feedback_two_word_commands`). «даю разрешение» и «даю продолжение» —
> по 2 слова, проходят. Дополнительные синонимы тоже должны быть ≥2 слов.

### 4.6 Регистрация

- В `commands/registry.py` → `_default_commands()`: импортировать и добавить оба
  инстанса в секцию `# INSTANT` (рядом со `ScreenshotCommand()`).
- Обновить `tests/fixtures/commands_snapshot.json` (снапшот команд) — иначе
  соответствующий тест упадёт.
- Добавить примеры синонимов в `config/voice_commands.example.toml`.
- Добавить в «Полный список голосовых команд.txt» / «список команд» при наличии.

### 4.7 Конфиг (`config.py` + `config_model.py`)

```python
TERMINAL_PROCESS_NAME = "WindowsTerminal.exe"  # целевой процесс
TERMINAL_RETURN_FOCUS = True                   # возвращать фокус после команды
TERMINAL_CONTINUE_TEXT = "продолжай"           # что печатать для give_continuation
TERMINAL_FOCUS_SETTLE_DELAY_MS = 80            # пауза после активации до ввода
TERMINAL_INTER_CHAR_DELAY_MS = 5               # пауза между символами при печати
```
Если в проекте конфиг валидируется через `config_model.py` (Pydantic-модель) —
добавить поля и туда.

### 4.8 bootstrap()

Вызвать `disable_foreground_lock()` один раз на старте — в той же фазе, где
`bootstrap()` печатает аудио-устройства (memory `project_audio_devices`).
Проверить, что вызывается во всех entry point'ах, использующих эти команды.

## 5. Звуковые ack-фразы

По механизму `utils.generate_ack_phrases` (см. `commands/base.py`: `ack_after` →
файл `assets/ack/<name>_after.wav`). Сгенерировать:
- `give_permission_after.wav` (например «разрешение дано» / короткий бип-ОК)
- `give_continuation_after.wav` (например «продолжаю»)

Либо переиспользовать общий звук подтверждения, если такой есть.

## 6. Проверка (по стандарту проекта)

- **`check_stage_<N>.py`** — обязателен (memory `feedback_check_stage_scripts`):
  standalone-скрипт с чек-листом ручной приёмки. Должен:
  1. вызвать `bootstrap()` (+ `disable_foreground_lock()`),
  2. найти окно WT и распечатать его заголовок/HWND,
  3. по нажатию выполнить активацию → Enter → возврат фокуса,
  4. отдельный пункт — печать «продолжай» + Enter,
  5. спросить y/n: «фокус переключился? Enter дошёл? фокус вернулся на YouTube?».
  - ⚠️ Запускать из **отдельного** окна терминала, НЕ из окна активной сессии
    Claude Code (иначе скрипт дёрнет фокус сам у себя во время разработки).
- **pytest** — юнит-тесты на то, что поддаётся без живого окна:
  - команды зарегистрированы, синонимы ≥2 слов;
  - `find_window_by_process` с моками EnumWindows;
  - `execute()` возвращает `False`, когда окно не найдено;
  - snapshot-тест команд обновлён.

## 7. Возможные расширения (на будущее, НЕ сейчас)

- **«запомни терминал»** — отдельная команда, фиксирующая конкретный HWND
  активного окна (надёжнее поиска по процессу, если появится >1 окна WT/вкладок).
- **«отклоняю» / «отмена»** → Esc (вариант B-минимум «пульта»).
- **Полный пульт**: стрелки + Enter для выбора пунктов меню, прокрутка.
- **Вариант B (OCR)**: скриншот окна терминала + OCR → Шурочка зачитывает вопрос
  Claude вслух перед подтверждением. Безопаснее, но заметно дороже (новый
  OCR-модуль). Сейчас не делаем — «человек в контуре» закрывает потребность.

## 8. Риски (после уточнения сценария — минимальны)

| Риск | Статус |
|---|---|
| Слепой Enter подтвердит деструктив | Снят: человек в контуре, команда даётся только увидев вопрос |
| Сворачивание fullscreen YouTube | Снят: только оконный side-by-side режим |
| Мелькание фокуса | Незначительно: оба окна и так на экране, видео/звук от фокуса не зависят |
| Foreground-lock не снялся | Покрыт двухуровнево: SPI на старте + AttachThreadInput-фолбэк |
| Несколько окон WT/вкладок | Сейчас 1 окно; на будущее — «запомни терминал» (раздел 7) |
| Печать «продолжай» при открытом меню подтверждения | Ответственность пользователя (выбирает нужную команду под состояние) |

## 9. Чек-лист файлов для реализации

- [ ] `system/window_control.py` — новый (поиск/активация/возврат фокуса/SPI)
- [ ] `system/media_keys.py` — добавить `VK_RETURN`, `press_enter()`, `type_unicode()`
- [ ] `commands/terminal_control_command.py` — новый (2 команды)
- [ ] `commands/registry.py` — зарегистрировать обе команды
- [ ] `config.py` (+ `config_model.py`) — новые настройки
- [ ] `config/voice_commands.example.toml` — примеры синонимов
- [ ] `assets/ack/` — сгенерировать ack-WAV (`utils.generate_ack_phrases`)
- [ ] `tests/fixtures/commands_snapshot.json` — обновить снапшот
- [ ] `tests/test_terminal_control.py` — юнит-тесты
- [ ] `check_stage_<N>.py` — скрипт ручной приёмки (удалить после приёмки)
- [ ] bootstrap() — вызвать `disable_foreground_lock()` на старте
- [ ] Обновить документацию через `/update-docs` (CHANGELOG + PROJECT_INDEX)
- [ ] Обновить «Полный список голосовых команд.txt»
