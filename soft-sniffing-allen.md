# План: Редизайн GUI (Dashboard + Settings на PySide6) и рефакторинг config.py

## Context

Текущий `ui/tkinter_ui.py` — монолит 1174 строк, совмещающий пульт, настройки, лог и диагностику. В `config.py` 89 констант, которые нельзя менять из программы — только редактировать исходник и перезапускать. Документ `разработка дизайна графического интерфейса.txt` описывает редизайн: разделение на компактный Dashboard (420×320) и отдельное окно Settings с sidebar, поиском и семью категориями; переход Tkinter → PySide6; Pydantic-модель конфига + пользовательский `settings.toml`; метки ⚡/🔄/⚠ по способу применения параметров; таблица команд из `CommandRegistry`.

Проверенные факты после исследования:
- **Ядро чистое:** `VoicePipeline` (main.py) не содержит Tkinter-вызовов, общается с UI только через callbacks и очереди — миграция безопасна.
- **Pydantic v2.9.2 уже в `requirements.txt`** (используется в `ipc/schemas.py`).
- **24 модуля** импортируют из `config.py` (`from config import X`) — трогать их массово рискованно.
- **Тесты минимальны:** только `tests/test_wake_word.py` (text-matching). Регрессии на конфиге ловить нечем.
- **Overlay** — чистый Tk Toplevel с ctypes click-through; **tray** на pystray; **hotkey** на pynput. `pynput` с Qt совместим, `pystray` — нет (заменяется `QSystemTrayIcon`).
- **check_stage_*.py** — готовый паттерн с y/n-приёмкой, 9 скриптов в корне.

**Решения по развилкам (ответы пользователя):**
1. **Параллельная миграция** на отдельной ветке с флагом `UI_BACKEND={tkinter|pyside6}` — старое окно работает до приёмки нового.
2. **Overlay переписывается на QWidget** (frameless + `Qt.WindowStaysOnTopHint` + `Qt.WindowTransparentForInput`) — однородный стек.
3. **Config shim:** `config.py` внутри конструирует singleton Pydantic `Settings`, но продолжает экспортировать все старые module-level константы (`WHISPER_MODEL_SIZE = settings.whisper.model_size` и т.д.). Импорты 24 модулей не меняются.
4. **Предварительные регрессионные тесты пишутся ДО рефакторинга** — snapshot-значений констант, smoke-импорты всех потребителей, pytest на `CommandRegistry`.

---

## Этап 0 — Предварительная подготовка (baseline)

**Цель:** зафиксировать текущее состояние, чтобы ловить регрессии.

**Действия:**
1. Создать ветку `feat/ui-redesign` от `main`.
2. Обновить `requirements.txt`: добавить `PySide6>=6.7,<7`, `tomli-w>=1.0,<2` (для записи TOML; чтение — stdlib `tomllib` в Python 3.11+, здесь 3.10 → добавить `tomli>=2.0,<3`).
3. Снять «снимок» текущих значений: скрипт `scripts/dump_config_snapshot.py` — печатает все 89 констант из `config.py` в JSON-файл `tests/fixtures/config_snapshot_baseline.json`. Коммитится в репозиторий.
4. Создать файл `docs/config_migration_map.md` — таблица `старое_имя → новое_поле` для всех 89 параметров (нужна как основа для shim и для человека).
5. Зафиксировать baseline командных названий: `scripts/dump_commands_snapshot.py` сохраняет `{name, synonyms, command_type}` каждой команды из `build_default_registry()` в `tests/fixtures/commands_snapshot.json`.

**Критичные файлы:** `requirements.txt`, новые `scripts/dump_config_snapshot.py`, `scripts/dump_commands_snapshot.py`, `tests/fixtures/config_snapshot_baseline.json`, `tests/fixtures/commands_snapshot.json`, `docs/config_migration_map.md`.

**Регрессий нет** — только чтение.

---

## Этап 1 — Предварительные тесты (safety net)

**Цель:** автоматизированная страховка против регрессий рефакторинга. Запускается перед КАЖДЫМ следующим этапом.

**Действия:**
1. `tests/test_config_contract.py`:
   - `test_all_known_constants_present` — сверяет список атрибутов модуля `config` с baseline-snapshot (именованно).
   - `test_default_values_unchanged` — для каждой константы из snapshot сравнивает `getattr(config, name)` с зафиксированным значением. Исключения: только `BASE_DIR`/`LOGS_DIR`/`MODELS_DIR` (абсолютные пути, сравниваются как `.name`).
   - `test_types_unchanged` — для каждой константы фиксируется тип.
2. `tests/test_config_importers.py`:
   - `test_smoke_import_all_consumers` — параметризованно импортирует каждый из 24 модулей-потребителей (`core.stt`, `core.llm`, …, `ui.overlay`, `ipc.server`, `logging_config`, `main`). Проверяется, что импорт не падает. Не инстанцирует тяжёлые объекты (Whisper/TTS).
3. `tests/test_commands_registry.py`:
   - `test_default_registry_matches_snapshot` — `build_default_registry()` даёт тот же набор `(name, synonyms, type)`, что в `commands_snapshot.json`.
   - `test_all_synonyms_two_words_or_more` — инвариант «команды ≥ 2 слов» из памяти.
4. `tests/test_pipeline_smoke.py` (с моками):
   - `test_voice_pipeline_init_without_audio` — VoicePipeline инстанцируется с моками `AudioStream`/`STT`/`TTS`/`LLM`; проверяется, что `start()` вызывает `on_stage` с ожидаемыми именами. Нужен `conftest.py` с fixture-моками провайдеров.
5. Добавить `pytest.ini` с маркерами `@pytest.mark.slow` / `@pytest.mark.gpu`, чтобы в CI запускать быстрые без GPU.

**Критерий приёмки:** `pytest -q` зелёный на чистом main до рефакторинга.

**Stage-скрипт:** не нужен (чистые автотесты).

---

## Этап 2 — Рефакторинг config.py на Pydantic Settings + settings.toml (shim)

**Цель:** внутренности config.py меняются на Pydantic-модель, пользовательские правки пишутся в `settings.toml`, но 24 модуля-потребителя не трогаем (module-level атрибуты остаются).

**Действия:**
1. Новый модуль `config_model.py`:
   - Nested Pydantic BaseSettings: `AudioSettings`, `VADSettings`, `DeepFilterSettings`, `STTSettings`, `LLMSettings` (с sub-моделями `OllamaSettings`, `LMStudioSettings`), `TTSSettings` (с `SileroSettings`, `XTTSSettings`), `WakeWordSettings`, `CommandSettings`, `DictateSettings`, `UISettings`, `LoggingSettings`, `RemindersSettings`, `IPCSettings`, `PathsSettings`.
   - `class Settings(BaseSettings)` агрегирует все под-модели.
   - `load_settings()` — загружает `settings.toml` поверх дефолтов (если файл есть), валидирует, возвращает singleton.
   - `save_settings(settings, diff_only=True)` — сохраняет ТОЛЬКО изменённые поля в `settings.toml` через `tomli-w`.
2. `config.py` переписывается:
   ```python
   from config_model import load_settings
   settings = load_settings()
   # --- Обратная совместимость (shim) ---
   WHISPER_MODEL_SIZE = settings.stt.whisper_model_size
   WHISPER_DEVICE = settings.stt.whisper_device
   # ... все 89 констант
   ```
   Список и маппинг из `docs/config_migration_map.md`.
3. `settings.toml` НЕ коммитится (в `.gitignore`); коммитится `settings.toml.example` с закомментированными опциями.
4. `logging_config.py`, `main.py` и др. работают без изменений — они всё ещё читают `from config import X`.

**Критичные файлы:** `config_model.py` (новый), `config.py` (переписан), `.gitignore`, `settings.toml.example` (новый).

**Риски и защиты:**
- Pydantic может не принять существующие значения (например, строки вместо `Literal[...]`) — Этап 1 `test_default_values_unchanged` ловит расхождения сразу.
- Поля `Path` должны сохранять совместимость — `PathsSettings` возвращает `Path` там, где раньше был `Path`, и `str` где был `str`.

**Stage-скрипт `check_stage_config_refactor.py`:**
- печатает 20 случайных констант (старые значения vs settings), подтверждает совпадение;
- создаёт временный `settings.toml` с изменённым `OLLAMA_TIMEOUT`, перезагружает, убеждается что `config.OLLAMA_TIMEOUT` подтянул новое значение;
- чек-лист: [ ] `pytest` зелёный, [ ] `python main.py --mode ipc` стартует, [ ] голосовая turn-операция отрабатывает.

---

## Этап 3 — PySide6-скелет + флаг UI_BACKEND

**Цель:** PySide6-приложение стартует пустым окном параллельно с Tkinter; старое `python main.py` работает как было.

**Действия:**
1. `ui/pyside6/__init__.py`, `ui/pyside6/app.py` — QApplication-bootstrap, подключение `qtvscodestyle` Solarized Light. Резервная QSS — своя (в `ui/pyside6/styles/solarized.qss`), чтобы не зависеть от заброса пакета.
2. `ui/pyside6/bridge.py` — мост `VoicePipeline ↔ Qt`:
   - `PipelineBridge(QObject)` с сигналами `state_changed(str, object)`, `turn_result(TurnResult)`, `health_update(dict)`, `level_update(float)`.
   - Внутри — поток (`QThread` или пул) с консьюмером тех же `_ui_queue`/`_job_queue`, которые уже использует Tkinter-версия. Это позволит не менять `main.py`.
3. `main.py` получает флаг `--ui pyside6|tkinter` (default = `tkinter` на этапе 3, переключится на `pyside6` на этапе 8).
4. Dashboard-заглушка: главное `QMainWindow` 420×320 с четырьмя кнопками и полем статуса — ничего не делают, но отрисовываются.

**Критичные файлы:** `main.py` (только добавление CLI-флага), `ui/pyside6/app.py`, `ui/pyside6/bridge.py`, `ui/pyside6/dashboard.py` (заглушка), `ui/pyside6/styles/solarized.qss`.

**Stage-скрипт `check_stage_pyside6_skeleton.py`:** запускает оба варианта UI по очереди, пользователь подтверждает, что старый работает нормально, а новый стартует и отображает заглушку.

---

## Этап 4 — Dashboard (пульт управления)

**Цель:** функциональный пульт на PySide6 с живым уровнем микрофона, индикаторами состояния, 4 кнопками, историей последней turn-операции.

**Действия:**
1. `ui/pyside6/dashboard.py`:
   - Статус-виджет (иконка + текст из `STATE_LABELS`);
   - Кастомный `LevelMeter(QWidget)` — рисует RMS-bar через `QPainter`, подписан на `bridge.level_update`;
   - Панель последней turn: «Вы: …» / «Шурочка: …» / тайминги STT/LLM/TTS/итого;
   - 4 кнопки: Listen, Stop, Standby toggle, Recalibrate;
   - Комбобокс LLM-модели с Apply (копия логики из `tkinter_ui.py:266-282`);
   - Status bar с тремя цветными точками (STT/LLM/TTS) и строкой последнего warning.
2. Кнопка-шестерёнка ⚙ открывает (пока пустое) окно Settings.
3. Переиспользуется: `bridge.state_changed`, `bridge.level_update`, `bridge.turn_result`, `bridge.health_update`.

**Критичные файлы:** `ui/pyside6/dashboard.py`, `ui/pyside6/widgets/level_meter.py`, `ui/pyside6/widgets/status_indicator.py`.

**Stage-скрипт `check_stage_dashboard.py`:** пользователь произносит «Шурочка, сколько времени?», проверяет: (1) иконка состояний проходит idle→listening→processing→speaking; (2) уровень микрофона дрожит; (3) тайминги появляются; (4) смена LLM-модели через комбобокс работает.

---

## Этап 5 — Settings: каркас + 7 категорий

**Цель:** окно Settings 800×600 с sidebar, поиском, семью панелями параметров (Общие / Аудио-VAD / STT / LLM / TTS / Wake-word / Интерфейс).

**Действия:**
1. `ui/pyside6/settings/window.py` — `QMainWindow` с `QSplitter`: слева `QListWidget` (категории), справа `QStackedWidget` (панели).
2. `ui/pyside6/settings/search.py` — индекс всех полей (label + описание + путь в sidebar), `QLineEdit` фильтрует и показывает все совпадения списком с хлебными крошками.
3. По одному файлу на категорию: `settings/panels/general.py`, `audio_vad.py`, `stt.py`, `llm.py`, `tts.py`, `wake_word.py`, `interface.py`. Каждая панель — `QWidget` с Pydantic-связанными полями:
   - `SettingField(QWidget)` — базовый класс: label, редактор (Spin/Line/Combo/Slider/Text), иконка ⚡/🔄/⚠ справа, bold при отличии от default, правый клик → «Сбросить».
   - Валидация через `settings.model_validate()` на изменении — красная рамка + tooltip при ошибке.
4. Сохранение: Save пишет в `settings.toml` через `config_model.save_settings(diff_only=True)`, эмитит сигнал `settings_changed(changed_keys: list[str])`.
5. Применение:
   - ⚡ поля — бридж вызывает соответствующие сеттеры subsystem'ов (например, `pipeline.vad.pause_threshold = x`) немедленно.
   - 🔄 поля — бридж дергает `pipeline.reload_llm()` / `pipeline.reload_tts()` (новые методы, тонкие обёртки над текущими unload/load).
   - ⚠ поля — модальный диалог «Перезапустить сейчас?», при согласии — `pipeline.shutdown()` + `pipeline.start()`.
6. LLM-панель переключает отображаемые поля в зависимости от провайдера (Ollama vs LM Studio); TTS-панель — аналогично.
7. Двухуровневые секции: виджет `CollapsibleSection(QWidget)`, состояние хранится в `QSettings`.

**Критичные файлы:** `ui/pyside6/settings/*`, новые методы `VoicePipeline.reload_llm()`, `VoicePipeline.reload_tts()` в `main.py`.

**Stage-скрипт `check_stage_settings.py`:** пользователь меняет (1) системный промпт ⚡ — применяется без рестарта; (2) голос Silero 🔄 — перезагружается за 2-3с; (3) модель Whisper ⚠ — диалог, рестарт. Проверяется, что `settings.toml` содержит только изменённые ключи.

---

## Этап 6 — Таблица команд + полировка (live VAD, TTS-тест, hotkey capture)

**Цель:** недостающие фичи из документа.

**Действия:**
1. `ui/pyside6/settings/panels/commands_table.py` — `QTableView` с моделью над `build_default_registry()`, колонки: name, type, synonyms, status. Сортировка и фильтр через `QSortFilterProxyModel`. Кнопка «Обновить» перечитывает реестр.
2. Live VAD preview в панели Audio: `LevelMeter` + горизонтальная линия порога, подвязанная к слайдеру `MIN_ENERGY_THRESHOLD`. Двигаешь слайдер — линия смещается в реальном времени.
3. Кнопка «Тест» рядом с выбором голоса TTS — синтезирует фиксированную фразу через текущий TTS провайдер и проигрывает.
4. Виджет захвата горячей клавиши (`HotkeyCapture(QLineEdit)`) для `WAKE_HOTKEY`.
5. Alias-чипы для `WAKE_WORD_ALIASES` — кастомный `TagInput(QWidget)`.

**Критичные файлы:** `ui/pyside6/settings/panels/commands_table.py`, `ui/pyside6/widgets/hotkey_capture.py`, `ui/pyside6/widgets/tag_input.py`.

**Stage-скрипт:** пользователь видит все 13 команд в таблице, меняет hotkey через capture-виджет, двигает VAD-слайдер и видит живое смещение порога, жмёт «Тест» у голоса Silero и слышит фразу.

---

## Этап 7 — Миграция overlay/tray/hotkey на Qt

**Цель:** убрать зависимости от Tkinter Toplevel, pystray; убедиться что `python main.py --ui pyside6` работает полностью без Tk.

**Действия:**
1. `ui/pyside6/overlay.py` — frameless `QWidget` с `Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool | Qt.WindowTransparentForInput`. Отрисовка через `QPainter`. Позиционирование по `QScreen.availableGeometry()` + `OVERLAY_MARGIN`.
2. `ui/pyside6/tray.py` — `QSystemTrayIcon` с тем же меню: Enable Assistant, Open Session, Reload Config, Quit. Иконка из того же PNG, что использовала pystray.
3. `ui/pyside6/hotkey.py` — оставляется `pynput` (работает независимо от GUI-фреймворка), только обёртка переезжает в папку Qt для единообразия импорта.
4. Удалить `pystray` и `Pillow` из `requirements.txt`. `pynput` остаётся.

**Критичные файлы:** `ui/pyside6/overlay.py`, `ui/pyside6/tray.py`, `ui/pyside6/hotkey.py`, `requirements.txt`.

**Stage-скрипт:** пользователь запускает `python main.py --ui pyside6` (без каких-либо Tk-окон), проверяет: оверлей показывается и кликается насквозь; трей-иконка работает; Ctrl+Alt+S включает wake-word.

---

## Этап 8 — Переключение по умолчанию + удаление Tkinter

**Цель:** финальная очистка: `pyside6` становится дефолтом, старый Tkinter удаляется.

**Действия:**
1. `main.py`: default `--ui` = `pyside6`.
2. Удалить `ui/tkinter_ui.py` (1174 строки).
3. Удалить старые `ui/overlay.py` (Tk-версия), `ui/tray.py` (pystray), `ui/hotkey.py` (корневой, если дублирует новый).
4. `ui/pyside6/*` переехать в `ui/*` (упростить импорты, если папочная иерархия избыточна).
5. CLAUDE.md: обновить разделы «Entry points», «UI». Добавить упоминание `settings.toml`.
6. README/документация: обновить скриншоты, инструкции.

**Критичные файлы:** удаление `ui/tkinter_ui.py`, `ui/overlay.py`, `ui/tray.py`, `ui/hotkey.py` (старые); правка `main.py`, `CLAUDE.md`.

**Stage-скрипт:** пользователь запускает `python main.py` без флагов, всё работает, старого окна нет.

---

## Этап 9 — Полная проверка на регрессии (financial regression pass)

**Цель:** система равноценна или лучше прежней по ВСЕМ ранее принятым этапам (Stages 1-10 + M4/M6/M8). Никаких «ой, это сломалось».

**Действия — автоматизированная часть:**
1. `pytest -q` — все тесты из Этапа 1 зелёные (включая snapshot-сверку).
2. `scripts/verify_config_snapshot.py` — сверяет текущие `config.X` значения с `config_snapshot_baseline.json`; допускаются ТОЛЬКО добавления новых полей (новые опции), удалений быть не должно.
3. `scripts/verify_commands_snapshot.py` — аналогично для `commands_snapshot.json`.
4. Проверка импортов всех 24 модулей (из `test_config_importers.py`).

**Действия — ручная регрессия по ранее принятым этапам (чек-лист в `check_regression_full.py`):**
- [ ] **Stage 5 (STT→LLM→TTS):** полный голосовой turn, тайминги в UI совпадают с логом.
- [ ] **Stage 6 (IPC):** `python main.py --mode ipc` стартует; клиент делает `health_check`, `generate_only`, `transcribe_and_respond`, `recalibrate`.
- [ ] **Stage 7 (VAD динамика):** RMS-бар и порог живые, калибровка работает.
- [ ] **Stage 8 (Wake-word):** «Шурочка» активирует дежурный режим, таймаут работает, бипы on/off.
- [ ] **Stage 9 (DeepFilterNet):** флаг `USE_DEEPFILTER=true` (в `settings.toml`) корректно включает денойз; false — выключает.
- [ ] **Stage 10 (Reminders):** «Шурочка, напомни через 5 минут …» создаёт запись в `reminders.json`, напоминание срабатывает.
- [ ] **M4 (audio session mute):** команда «поставь на паузу» ставит музыку на паузу через pycaw; CoInitialize STA работает.
- [ ] **M6 (volume):** «сделай громче» / «тише» работает.
- [ ] **M8 (overlay+tray+hotkey):** всё работает на Qt-версии; оверлей click-through.
- [ ] **Правило «команды ≥2 слов»:** тест автоматический + ручная проверка, что однословные синонимы отвергаются.
- [ ] **LLM только через явный триггер:** бип на нераспознанное, без LLM-фолбэка.
- [ ] **COM STA:** логи без `RPC_E_CHANGED_MODE`.
- [ ] **XTTS/Whisper VRAM swap:** если `TTS_PROVIDER=xtts` и `TTS_DEVICE=cuda`, unload/reload цикл работает без OOM.
- [ ] **Настройки применяются:** ⚡ мгновенно, 🔄 перезагружает компонент, ⚠ спрашивает про рестарт.
- [ ] **`settings.toml` хранит только diff:** удалил файл — всё работает на дефолтах.
- [ ] **Старое окно удалено:** `grep -r tkinter` в `ui/` даёт 0 совпадений.

**Критичные файлы:** `check_regression_full.py` (новый standalone-скрипт в корне).

**Критерий приёмки:** все автоматические тесты зелёные + пользователь y-подтвердил каждый пункт ручного чек-листа. После — удалить все временные `check_stage_*.py` этой ветки.

---

## Верификация

Общий запуск:

```bash
pytest -q                                          # все unit + smoke
python scripts/verify_config_snapshot.py           # no breaking changes
python scripts/verify_commands_snapshot.py         # registry intact
python main.py                                     # дефолт = PySide6
python main.py --mode ipc                          # headless
python main.py --mode console                      # REPL + IPC
python check_regression_full.py                    # финальная ручная приёмка
```

Все шаги должны пройти; регрессионный скрипт — последний и самый строгий.

---

## Сводка критичных файлов

**Новые:**
- `config_model.py`, `settings.toml.example`
- `ui/pyside6/{app,bridge,dashboard,overlay,tray,hotkey}.py`
- `ui/pyside6/settings/{window,search}.py` + 7 панелей в `settings/panels/`
- `ui/pyside6/widgets/{level_meter,status_indicator,collapsible_section,hotkey_capture,tag_input}.py`
- `ui/pyside6/styles/solarized.qss`
- `tests/test_config_contract.py`, `tests/test_config_importers.py`, `tests/test_commands_registry.py`, `tests/test_pipeline_smoke.py`
- `tests/fixtures/config_snapshot_baseline.json`, `tests/fixtures/commands_snapshot.json`
- `scripts/dump_config_snapshot.py`, `scripts/dump_commands_snapshot.py`, `scripts/verify_config_snapshot.py`, `scripts/verify_commands_snapshot.py`
- `docs/config_migration_map.md`
- `check_stage_config_refactor.py`, `check_stage_pyside6_skeleton.py`, `check_stage_dashboard.py`, `check_stage_settings.py`, `check_stage_commands_table.py`, `check_stage_qt_overlay.py`, `check_regression_full.py`

**Модифицированные:**
- `config.py` (становится shim)
- `main.py` (новые `--ui` флаг, `reload_llm()`, `reload_tts()`)
- `requirements.txt` (+ PySide6, tomli/tomli-w; − pystray, Pillow)
- `.gitignore` (+ `settings.toml`)
- `CLAUDE.md` (обновление разделов UI и конфигурации)

**Удаляемые (на Этапе 8):**
- `ui/tkinter_ui.py`, `ui/overlay.py`, `ui/tray.py`, `ui/hotkey.py` (Tk-версии)
