# Voice AI Assistant — Поэтапный план разработки

**Создан:** 2026-04-19
**Обновлён:** 2026-04-19 (v2 — интегрированы решения из `benchmark_runner.py` и `voice_converter.py`; добавлено правило об обязательном `check_stage_<N>.py`)
**Статус:** В работе
**Принцип:** Каждый этап заканчивается ручной валидацией. Следующий этап начинается только после успешной проверки предыдущего.

---

## Правило ручной валидации (обязательно для каждого этапа)

По окончании **каждого** этапа ассистент обязан создать отдельный standalone-скрипт для ручной проверки пользователем. Требования к скрипту:

1. **Размещение и имя:** `check_stage_<номер_этапа>.py` в корне проекта (например, `check_stage_1c.py`, `check_stage_3.py`). Скрипт — временный, удаляется после приёмки этапа пользователем.
2. **Запускается одной командой** из корня: `python check_stage_<N>.py`. Никаких аргументов, никаких подготовительных действий кроме явно описанных.
3. **Шапка-докстринг скрипта** должна содержать:
   - **Что именно делает этап** (одна-две строки).
   - **Что должен сделать пользователь** во время запуска (говорить в микрофон, не шуметь, подождать калибровку, нажать Enter и т.д.).
   - **На что обращать внимание** при наблюдении (какие числа/звуки/сообщения ожидать, какие — тревожный сигнал).
   - **Ожидаемый результат** (пример корректного вывода или диапазон значений).
   - **Критерии приёмки** — список пунктов в стиле чек-листа, которые пользователь может отметить: всё прошло → этап принят; хоть один пункт не выполнен → этап возвращается на доработку.
4. **Скрипт должен сам печатать** ключевые подсказки и ожидаемые диапазоны — пользователь не должен сверяться с планом в процессе. Финальной строкой — явный вопрос типа `Все ли критерии выполнены? (y/n) — см. список выше.`
5. **Никаких обязательных внешних зависимостей** помимо уже установленных для проекта. Ввод пользователя — только через `input()` и микрофон.
6. **Корректная обработка `Ctrl+C`** и освобождение ресурсов (микрофон, GPU) в `finally`.
7. **Обязательный `bootstrap()` в начале скрипта** (из `bootstrap.py`) — он настраивает логирование и фиксирует предпочтительные аудио-устройства (`PREFERRED_INPUT_DEVICE` / `PREFERRED_OUTPUT_DEVICE` из `config.py`). Скрипт должен печатать выбранные устройства, чтобы пользователь сразу видел, какой вход/выход будут использоваться.

Пример структуры (этап 1b):
```python
"""Этап 1b: AudioStream — фоновый чтец с RMS-мониторингом.

Что делает скрипт: открывает микрофон, 5 секунд показывает RMS / noise_floor / %.

Действия пользователя:
  1. Запустите скрипт в тихой комнате.
  2. Первые 2 сек молчите — смотрите, как стабилизируется noise_floor.
  3. Затем произнесите несколько слов — RMS должен резко скакнуть.
  4. Замолчите — RMS вернётся к noise_floor в течение секунды.

Ожидаемые диапазоны:
  * RMS в тишине: 50–300 (зависит от микрофона)
  * RMS при речи: 2000–10000+
  * noise_floor в тихой комнате: < 500

Критерии приёмки:
  [ ] RMS реагирует на голос (видно скачок)
  [ ] noise_floor стабилизируется за 2–3 секунды
  [ ] После stop() скрипт выходит без зависания
  [ ] Нет трейсбеков / предупреждений overflow
"""
```

Скрипт — **обязательная часть** результата этапа наряду с продуктовым кодом. Без него этап не считается завершённым.

---

## Прогресс

| Этап | Название | Статус |
|------|----------|--------|
| 0 | Окружение и инфраструктура | ✅ Готово |
| 1a | Аудио — воспроизведение и preprocessing | ✅ Готово |
| 1b | AudioStream — фоновый чтец с RMS-мониторингом | ✅ Готово |
| 1c | VAD и калибровка шума — автозапись по голосу | ✅ Готово |
| 2 | STT — распознавание речи | ✅ Готово |
| 3 | LLM — Ollama/LM Studio, robust-парсер и таксономия ошибок | ✅ Готово |
| 4 | TTS — синтез речи | ✅ Готово |
| 5 | Интеграция pipeline (STT → LLM → TTS) | ✅ Готово |
| 6 | IPC-сервер | ✅ Готово |
| 7 | Tkinter UI с диагностикой | ✅ Готово |
| 8 | Wake-word активация («Шурочка») | 🟡 В работе |
| 9 | Финальное тестирование и полировка | ⬜ Не начат |

---

## Этап 0: Окружение и инфраструктура

**Цель:** Проект запускается, зависимости установлены, логирование работает.

### Что создаём:
1. Файловая структура (все папки и пустые `__init__.py`)
2. `requirements.txt` с точными версиями
3. `config.py` — все параметры в одном месте (включая параметры VAD и LLM из референсов)
4. `logging_config.py` — структурированные логи в файл + консоль, ротация
5. `utils/errors.py` — кастомные исключения: `OllamaError`, `STTError`, `TTSError`, `AudioError`
6. `utils/helpers.py` — утилита **`save_state_atomic(path, payload)`** (паттерн из `benchmark_runner.py`: tmp-файл → `os.replace`, защита от повреждения при crash)
7. `core/base.py` — абстрактные классы `STTProvider`, `LLMProvider`, `TTSProvider`

### Параметры `config.py` (минимум на старте):
```python
# Пути
BASE_DIR = Path(__file__).parent
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"

# Аудио
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1024

# VAD и калибровка (из voice_converter.py)
CALIBRATION_DURATION = 2.0        # секунд для калибровки
CALIBRATION_MULTIPLIER = 1.8      # порог = max_rms * 1.8
MIN_ENERGY_THRESHOLD = 150        # минимальный порог (защита от тишины)
PAUSE_THRESHOLD = 1.0             # секунд тишины = конец фразы
NOISE_HISTORY_SIZE = 100          # размер скользящего окна для шума
DYNAMIC_ENERGY_DAMPING = 0.15
DYNAMIC_ENERGY_RATIO = 1.5

# STT
WHISPER_MODEL_SIZE = "large-v3"
WHISPER_DEVICE = "cuda"
WHISPER_LANGUAGE = "russian"

# LLM (из benchmark_runner.py)
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma-4-coder"
OLLAMA_TIMEOUT = 120
OLLAMA_MAX_TOKENS = 2048
OLLAMA_MAX_TOKENS_THINKING_MULTIPLIER = 2
OLLAMA_MAX_RETRIES = 2
OLLAMA_RETRY_DELAY = 5
THINKING_MODEL_PATTERNS = ["thinking", "think", "r1", "reasoning", "qwq"]

# TTS
TTS_DEVICE = "cuda"
TTS_LANGUAGE = "ru"

# IPC
IPC_HOST = "127.0.0.1"
IPC_PORT = 9999
```

### Ручная валидация:
```bash
python -c "from config import *; print('Config OK')"
python -c "from logging_config import setup_logging; setup_logging(); import logging; logging.getLogger().info('Test'); print('Logging OK')"
python -c "from core.base import STTProvider, LLMProvider, TTSProvider; print('Base classes OK')"
python -c "from utils.helpers import save_state_atomic; save_state_atomic('test_state.json', {'hello': 'world'}); import json; assert json.load(open('test_state.json'))['hello']=='world'; print('Atomic save OK')"
```

**Критерий:** Все команды выполняются без ошибок, лог-файл создаётся, `test_state.json` содержит корректный JSON.

---

## Этап 1a: Аудио — воспроизведение и preprocessing

**Цель:** Можем воспроизводить WAV-файлы и нормализовать аудио.

### Что создаём:
1. `core/audio_output.py` — класс `AudioPlayer` для проигрывания WAV
2. `core/preprocessing.py` — нормализация громкости, конвертация sample rate, RMS-утилита
3. Помещаем в репо тестовый WAV `tests/fixtures/sample.wav` для ручных проверок

### Ручная валидация:
```bash
python -c "
from core.audio_output import AudioPlayer
p = AudioPlayer()
p.play_file('tests/fixtures/sample.wav')
print('Воспроизведение OK')
"
python -c "
from core.preprocessing import compute_rms, normalize_audio
normalize_audio('tests/fixtures/sample.wav', 'test_normalized.wav')
print(f'RMS: {compute_rms(\"test_normalized.wav\"):.1f}')
"
```

**Критерий:** Слышишь тестовый файл, нормализованный файл создан с корректным форматом (16kHz, mono), RMS посчитан.

---

## Этап 1b: AudioStream — фоновый чтец с RMS-мониторингом

**Цель:** Микрофон открывается один раз, фоновый поток непрерывно читает чанки и вычисляет RMS каждого чанка. Это основа для VAD, индикатора уровня и калибровки.

### Что создаём:
1. `core/audio_stream.py` — класс `AudioStream`:
   - `start()` / `stop()` — управление микрофоном
   - Фоновый поток: читает чанки, вычисляет RMS, кладёт в очередь
   - `deque(maxlen=NOISE_HISTORY_SIZE)` — история RMS, обновляется только когда речь НЕ активна
   - `@property noise_floor_rms` — текущий средний шум (thread-safe)
   - `@property noise_floor_percent` — `min(100, int(rms / 327.67))`
   - Callback `on_level_update(rms, percent)` для UI

### Архитектурный паттерн (из `voice_converter.py`):
```python
class AudioStream:
    def __init__(self):
        self._noise_history = deque(maxlen=NOISE_HISTORY_SIZE)
        self._noise_floor_rms = 0.0
        self._noise_floor_lock = threading.Lock()
        self._speech_active = False
        self._level_queue = queue.Queue(maxsize=10)

    def _audio_loop(self):
        while self._running:
            data = self._stream.read(CHUNK_SIZE)
            rms = self._compute_rms(data)
            # обновляем шум только в тишине
            if not self._speech_active:
                self._update_noise_floor(rms)
            # публикуем уровень
            self._level_queue.put_nowait((rms, percent))
```

### Ручная валидация:
```bash
python -c "
from core.audio_stream import AudioStream
import time
stream = AudioStream()
stream.start()
print('Говорите или шумите 5 секунд...')
for _ in range(50):
    time.sleep(0.1)
    print(f'RMS={stream.current_rms:.1f}  noise_floor={stream.noise_floor_rms:.1f}  percent={stream.noise_floor_percent}%', end='\r')
stream.stop()
print('\nOK')
"
```

**Критерий:** RMS меняется в реальном времени, noise_floor стабилизируется за 2-3 секунды тишины, при речи RMS резко скачет, при тишине возвращается к noise_floor. Нет утечек памяти (проверить deque).

---

## Этап 1c: VAD и калибровка — автозапись по голосу

**Цель:** Юзер нажимает "Слушай" один раз → калибровка 2 сек → автоматическая запись всей фразы → автоматическая остановка через 1 сек тишины → WAV-файл только с речью.

### Что создаём:
1. `core/vad.py` — класс `VoiceActivityDetector`:
   - `calibrate(duration=2.0) -> (noise_rms, suggested_threshold)` — записывает тишину, считает `max_rms * 1.8`, минимум `150`
   - `record_until_silence(pause_threshold=1.0) -> str` — пишет до N сек тишины, возвращает путь к WAV
   - Dynamic подстройка порога: `threshold = threshold * (1 - damping) + rms * damping * ratio` (только когда нет речи)
2. Интеграция с `AudioStream` из 1b — VAD не открывает микрофон сам, берёт чанки из стрима.

### Логика FSM:
```
[idle]
  ↓ rms > threshold
[recording] ← rms > threshold (сброс silence timer)
  ↓ rms < threshold (silence_duration растёт)
  ↓ silence_duration >= PAUSE_THRESHOLD
[stopped] → сохранить WAV → return path
```

### Ручная валидация:
```bash
python -c "
from core.audio_stream import AudioStream
from core.vad import VoiceActivityDetector

stream = AudioStream()
stream.start()
vad = VoiceActivityDetector(stream)

print('Калибровка (2 сек тишины)...')
noise, thr = vad.calibrate()
print(f'Шум: {noise:.0f} RMS, порог: {thr}')

print('Говорите фразу (автостоп через 1 сек тишины)...')
wav_path = vad.record_until_silence()
print(f'Записано: {wav_path}')

stream.stop()
"
# Затем прослушать результат — должна быть только ваша речь без длинных хвостов
```

**Критерий:**
- Калибровка возвращает разумные значения (в тихой комнате `noise_rms < 200`, `threshold` в районе 200-400)
- Запись **автоматически** останавливается через ~1 сек после того как ты замолчал
- В WAV-файле нет длинной тишины в начале или конце
- Повторный тест с работающим вентилятором/кондиционером → `noise_rms` выше, порог выше → всё равно срабатывает

---

## Этап 2: STT — распознавание речи

**Цель:** Говоришь фразу (через VAD) — получаешь текст на русском.

### Что создаём:
1. `core/stt.py` — класс `WhisperSTT(STTProvider)`: загрузка модели, транскрибирование, выгрузка из GPU
2. `core/__init__.py` — фабрика `create_stt_provider()`
3. Логирование VRAM до/после загрузки модели

### Ручная валидация:
```bash
python -c "
from core.audio_stream import AudioStream
from core.vad import VoiceActivityDetector
from core import create_stt_provider

stream = AudioStream(); stream.start()
vad = VoiceActivityDetector(stream)
vad.calibrate()
print('Скажите \"привет мир\"...')
wav = vad.record_until_silence()
stream.stop()

stt = create_stt_provider('whisper')
stt.load_model()
result = stt.transcribe(wav)
print(f'Результат: {result}')
stt.unload_model()
"
```

**Критерий:**
- Модель загружается без ошибок
- Фраза распознаётся корректно
- После `unload_model()` VRAM освобождается (Task Manager → GPU)
- В `logs/voice_ai.log` видны записи о загрузке, VRAM и времени транскрибирования

---

## Этап 3: LLM — Ollama с robust-парсером и таксономией ошибок

**Цель:** Отправляем текст в Ollama, получаем ответ; парсер гарантированно убирает reasoning-блоки (включая **незакрытые**); понятные классы ошибок с retry-логикой.

### Что создаём:
1. `core/ollama_client.py` — REST-клиент:
   - `generate(prompt, model=None) -> str`
   - `is_healthy() -> bool` для health-check UI
   - Функция **`classify_ollama_error(e) -> ErrorType`** (паттерн из `benchmark_runner.py._classify_error`):
     - `CONNECTION_ERROR` — Ollama не запущена
     - `TIMEOUT` — истёк timeout
     - `MODEL_NOT_FOUND` — модели нет в каталоге
     - `CONTEXT_OVERFLOW` — слишком длинный промпт
     - `RATE_LIMIT` — редко, но retriable
     - `API_ERROR` — всё остальное
   - Retry **только** для `TIMEOUT` и `RATE_LIMIT`, с exp. backoff: `delay * (attempt + 2)`
   - `CONNECTION_ERROR`, `MODEL_NOT_FOUND`, `CONTEXT_OVERFLOW` → немедленный fail с понятным сообщением

2. `core/prompt_manager.py` — **портируем функции из `benchmark_runner.py`**:
   - `strip_think_tags(text)` — удаляет `<think>...</think>` И **незакрытые** `<think>...$` (критично: если LLM упрётся в token limit посреди рассуждения, без обработки незакрытых тегов TTS озвучит reasoning)
   - `clean_llm_response(text)` — для MVP: strip_think_tags + trim + удаление markdown-обёрток
   - На будущее (не MVP): `extract_json_strict` / `extract_json_lenient` с brace-matching для tool-calling

3. `core/llm.py` — класс `OllamaLLM(LLMProvider)`:
   - Функция `is_thinking_model(name)` — проверка по паттернам `["thinking", "think", "r1", "reasoning", "qwq"]`
   - Автоматическая подстройка `max_tokens` × 2 для thinking-моделей
   - Увеличение timeout для thinking-моделей

4. `core/__init__.py` — фабрика `create_llm_provider()`

### Тест-кейсы для `strip_think_tags`:
```python
assert strip_think_tags("<think>Думаю...</think>\n\nПривет!") == "Привет!"
assert strip_think_tags("<think>Оборвалось...") == ""  # незакрытый
assert strip_think_tags("Привет <think>р</think> мир") == "Привет  мир"
assert strip_think_tags("") == ""
assert strip_think_tags("Без тегов вообще") == "Без тегов вообще"
```

### Ручная валидация:
```bash
# Тест 1: Health check при НЕ запущенной ollama
python -c "
from core.ollama_client import OllamaClient
c = OllamaClient()
print(f'Healthy: {c.is_healthy()}')
"

# Тест 2: Генерация + парсер (ollama serve должен работать)
python -c "
from core import create_llm_provider
llm = create_llm_provider('ollama')
response = llm.generate('Скажи коротко привет по-русски. Одно предложение.')
print(f'Ответ: {response}')
assert '<think>' not in response, 'В ответе не должно быть think-блоков'
"

# Тест 3: strip_think_tags
python -c "
from core.prompt_manager import strip_think_tags
cases = [
    ('<think>x</think>Привет', 'Привет'),
    ('<think>незакрытый', ''),
    ('Текст', 'Текст'),
]
for inp, exp in cases:
    got = strip_think_tags(inp).strip()
    assert got == exp, f'FAIL: {inp!r} → {got!r}, ожидалось {exp!r}'
print('Parser OK')
"

# Тест 4: Классификация ошибок
python -c "
from core.ollama_client import classify_ollama_error
import httpx
print(classify_ollama_error(httpx.TimeoutException('')))  # → TIMEOUT
print(classify_ollama_error(ConnectionError()))           # → CONNECTION_ERROR
"
```

**Критерий:**
- Ollama отвечает на русском
- `<think>` блоки (закрытые и незакрытые) корректно вырезаются — в ответе их нет
- При остановленной Ollama — `is_healthy() == False`, генерация даёт понятную ошибку `CONNECTION_ERROR`, не крэш
- В логах — время генерации, использованная модель, флаг thinking-model (если применимо)
- Все тест-кейсы `strip_think_tags` проходят

---

## Этап 4: TTS — синтез речи

**Цель:** Передаём текст на русском — получаем и слышим синтезированный голос.

### Что создаём:
1. `core/tts.py` — класс `XTSTTTS(TTSProvider)`: загрузка XTTS-v2, синтез, выгрузка из GPU
2. `core/tts_utils.py` — определение speaker, сохранение WAV
3. `core/__init__.py` — фабрика `create_tts_provider()`
4. Логика swap GPU: unload Whisper → load TTS → synthesize → unload TTS → load Whisper

### Ручная валидация:
```bash
python -c "
from core import create_tts_provider
from core.audio_output import AudioPlayer

tts = create_tts_provider('xtts')
tts.load_model()
audio_path = tts.synthesize('Привет! Это тест синтеза речи.')
tts.unload_model()

AudioPlayer().play_file(audio_path)
"
```

**Критерий:**
- Слышишь синтезированный голос на русском
- VRAM корректно освобождается после `unload_model()` (Task Manager)
- Нет артефактов/обрывов в аудио
- Проверить edge case: пустая строка → понятная ошибка, не крэш

---

## Этап 5: Интеграция pipeline (STT → LLM → TTS)

**Цель:** Полный голосовой цикл работает как единое целое в консольном режиме.

### Что создаём:
1. `main.py` — оркестратор:
   - Инициализация: AudioStream → калибровка VAD → STT → LLM (health check) → TTS (lazy load)
   - Метод `process_voice_input()` — полный цикл
   - GPU swap: Whisper ↔ XTTS
   - Режим `--mode console`

### Алгоритм `process_voice_input()`:
```
1. vad.record_until_silence()   → wav_file
2. stt.transcribe(wav_file)     → user_text
   if user_text пуст → "Не расслышал, повтори" → goto 5
3. llm.generate(user_text)      → raw_response
4. clean_llm_response(raw)      → clean_text
   if clean_text пуст → "Модель не ответила" → goto 5
5. stt.unload_model()
   tts.load_model()
   audio = tts.synthesize(clean_text)
   tts.unload_model()
   stt.load_model()
6. audio_output.play_file(audio)
```

### Ручная валидация:
```bash
python main.py --mode console
# Enter → говоришь → слышишь ответ
# Проверить 5 циклов подряд без крэша
# Проверить edge cases:
#   - молчание → нет STT-результата → "не расслышал"
#   - ollama остановить посередине → понятная ошибка
```

**Критерий:**
- Полный цикл проходит без ошибок
- Время < 15 сек на первом запросе (прогрев), < 10 сек далее
- В `logs/voice_ai.log` видны все шаги с таймингами
- Edge cases (тишина, недоступный Ollama) обрабатываются gracefully

---

## Этап 6: IPC-сервер

**Цель:** Другие приложения могут отправлять запросы и получать ответы через сокет.

### Что создаём:
1. `ipc/protocol.py` — JSON-RPC структуры запрос/ответ
2. `ipc/schemas.py` — Pydantic модели для валидации
3. `ipc/server.py` — TCP-сокет сервер на `localhost:9999`, в отдельном потоке
4. `ipc/client.py` — клиент для других приложений
5. Запуск IPC-сервера в `main.py`

### Методы API:
- `transcribe_and_respond(audio_file)` — полный цикл
- `generate_only(text)` — только LLM → TTS (для текстовых интеграций)
- `health_check()` — статус Ollama/STT/TTS
- `recalibrate()` — принудительная перекалибровка VAD

### Ручная валидация:
```bash
# Терминал 1:
python main.py --mode console

# Терминал 2:
python -c "
from ipc.client import VoiceAIClient
client = VoiceAIClient()
print(client.health_check())
result = client.transcribe_and_respond('tests/fixtures/sample.wav')
print(result)
"
```

**Критерий:**
- Получаешь JSON с `status: ok`, `input_text`, `output_text`, `audio_file`, `processing_time`
- При невалидном запросе — `status: error` с понятным сообщением
- Сервер не падает при malformed JSON, невалидных типах, отсутствующих файлах
- Health check возвращает статус каждого компонента

---

## Этап 7: Tkinter UI с диагностикой

**Цель:** Графический интерфейс, который не только управляет циклом, но и показывает, что происходит внутри (критично для отладки).

### Что создаём:
1. `ui/tkinter_ui.py` — интерфейс:

**Основная панель:**
- Кнопка "🎤 Слушай" (режим push-to-talk или VAD-auto)
- Кнопка "🔄 Перекалибровать"
- Текстовое поле: распознанный текст
- Текстовое поле: ответ LLM
- Status bar: `🟢 Готов / 🔵 Калибровка / 🔴 Запись / 🧠 Обработка / 🔊 Воспроизведение / ❌ Ошибка`

**Панель диагностики (из voice_converter.py):**
- **Live-полоса уровня сигнала (RMS в %)**, обновление 10 раз/сек
- **Красная линия** — текущий порог срабатывания
- **Синяя линия** — текущий уровень фонового шума
- Числовые метки: `Порог: 350 | Шум: 180 (55%)`
- Индикаторы статусов сервисов: `🟢 Ollama / 🟢 Whisper / 🟡 XTTS (lazy)`

**Log viewer:**
- Последние N=50 строк из `voice_ai.log`
- Фильтр по уровню (INFO / WARNING / ERROR)

### Важно по потокам:
- Вся обработка (STT/LLM/TTS) — в отдельном потоке, UI не фризится
- Обновление live-уровня — из `AudioStream.level_queue` через `root.after(100, ...)`

### Ручная валидация:
```bash
python main.py  # запуск с UI по умолчанию
```

**Критерий:**
- Окно открывается, калибровка проходит автоматически
- Полоса уровня двигается в реальном времени, порог и шум видны
- Нажал "Слушай" → говоришь → статусы меняются по порядку → слышишь ответ
- Распознанный текст и ответ LLM отображаются в окне
- UI не зависает во время обработки (можно двигать окно, скроллить логи)
- При остановленной Ollama — индикатор `🔴 Ollama`, понятная ошибка в status bar
- Кнопка "Перекалибровать" — пересчитывает порог, полоса обновляется

---

## Этап 8: Wake-word активация («Шурочка»)

**Цель:** дежурный режим — программа постоянно слушает микрофон, ничего не делает, и просыпается на кодовое слово «Шурочка». После wake-word ждёт вопрос 8 сек, обрабатывает, озвучивает ответ и возвращается в дежурный.

### Что создаём:
1. `core/wake_word.py` — `WakeWordListener`: фоновый тред, enable/disable/stop, exact-match по токенам STT-текста (без substring). Состояния: `standby_idle` / `wake_heard` / `wake_active` / `wake_processing`.
2. `core/audio_beep.py` — генератор бипа в памяти (синус + fade) для звуковых сигналов активации (880 Гц) и отмены по таймауту (400 Гц).
3. `tests/test_wake_word.py` — unit-тесты `_normalize` / `contains_wake_word`: punctuation, алиасы, case, защита от substring (`шурочкин` ≠ `шурочка`).
4. `check_stage_8.py` — скрипт ручной приёмки.

### Что модифицируем:
- `config.py` — новая секция Wake-word: `WAKE_WORD`, `WAKE_WORD_ALIASES`, `WAKE_WORD_ENABLED_AT_STARTUP`, `WAKE_WORD_SCAN_WINDOW=4.0`, `WAKE_WORD_ACTIVE_TIMEOUT=8.0`, частоты/длительность бипов.
- `core/vad.py` — `record_until_silence` принимает `initial_silence_timeout`: если не началось речи, бросает `AudioError` вместо ожидания полного `max_duration`.
- `main.py` — `VoicePipeline` получает `process_voice_input_from_wav()` и свойства `stt`/`player`; `_process_voice_input_locked` умеет принимать уже записанный WAV.
- `ui/tkinter_ui.py` — новая кнопка «🛌 Дежурный: вкл/выкл», новые `STATE_LABELS`, `_on_toggle_standby`, создание listener'а в `_do_init`, остановка в `_do_stop`.

### Архитектура:
- Listener держит `pipeline.lock` только на время одной итерации (scan ≤ 4с, либо активация ≤ 15с). Между итерациями лок свободен — ручная кнопка «🎤 Слушай» работает как fallback.
- Wake-word определяется по exact-match токена в STT-тексте (нижний регистр, без пунктуации). Алиасы — такой же exact-match. Подстроки (`шурочкин`, `аршура`) не срабатывают — защита от false-positive; см. user memory `feedback_avoid_complex_auto`.

### Ручная валидация:
`python check_stage_8.py` — сценарии: (1) дежурный выкл по умолчанию; (2) вкл → «Шурочка» → высокий бип → вопрос → ответ → возврат в дежурный; (3) «Шурочка» + молчание 8с → низкий бип → возврат; (4) случайная фраза без слова — нет реакции; (5) ручная кнопка во время дежурного режима работает; (6) повторный toggle выключает.

**Критерии успеха:**
- [ ] Дежурный режим выключен при старте; включается только по кнопке
- [ ] Кодовое слово берётся из `config.WAKE_WORD` — правка одного места меняет активацию
- [ ] Высокий бип на активацию, низкий — на таймаут; бипы не обрезаются
- [ ] `шурочкин` и похожие не триггерят активацию
- [ ] Ручная кнопка «🎤 Слушай» работает и когда listener активен
- [ ] Выключение окна корректно останавливает listener (нет висящих тредов)
- [ ] `pytest tests/test_wake_word.py` проходит

---

## Этап 9: Финальное тестирование и полировка

**Цель:** MVP готов к публикации — стабильно, задокументировано.

### Что создаём:
1. `tests/test_audio_stream.py` — unit-тесты RMS, noise_floor, thread-safety
2. `tests/test_vad.py` — тесты калибровки и FSM (с фейковым AudioStream)
3. `tests/test_prompt_manager.py` — **полный набор кейсов для `strip_think_tags`** (закрытые, незакрытые, вложенные, пустые, с markdown)
4. `tests/test_ollama_client.py` — mock-тесты классификации ошибок и retry-логики
5. `tests/test_stt.py`, `test_llm.py`, `test_tts.py`, `test_ipc.py`
6. `tests/test_integration.py` — интеграционный тест полного pipeline
7. `README.md` — установка, запуск, требования
8. `.gitignore`, лицензия MIT

### Edge cases для обязательной проверки:
- Полная тишина (нет речи) → понятное сообщение
- Очень громкий звук (клип) → нет крэша
- Ollama остановлена → graceful error
- Ollama отвечает пустой строкой → graceful error
- LLM вернула только `<think>...</think>` (без полезного контента) → после парсинга пустота → сообщение юзеру
- Тhinking-модель без увеличенного max_tokens → обрезанный `<think>` → парсер корректно возвращает пусто
- GPU VRAM исчерпана → понятная ошибка, не крэш
- Очень длинный ответ LLM → TTS не падает, либо обрезается разумно

### Ручная валидация:
```bash
python -m pytest tests/ -v
```

**Критерии успеха MVP:**
- [ ] Полный цикл STT→LLM→TTS работает стабильно (10+ подряд без ошибок)
- [ ] Время обработки < 10 сек (после прогрева)
- [ ] VAD корректно отсекает тишину — никакой ручной остановки не требуется
- [ ] Калибровка адаптируется к уровню шума в комнате
- [ ] Reasoning-блоки **никогда** не попадают в TTS
- [ ] Все ошибки логируются и классифицируются, приложение не крэшится
- [ ] IPC работает и протестирован
- [ ] UI функционален, полоса уровня/шума помогает диагностировать проблемы
- [ ] `pytest tests/` проходит
- [ ] README достаточен для запуска с нуля

---

## Сводная таблица файлов по этапам

| Этап | Файлы | Источник идей |
|------|-------|---------------|
| 0 | `config.py`, `logging_config.py`, `utils/errors.py`, `utils/helpers.py` (save_state_atomic), `core/base.py`, `requirements.txt` | `benchmark_runner.py` |
| 1a | `core/audio_output.py`, `core/preprocessing.py` | — |
| 1b | `core/audio_stream.py` (RMS, noise_floor, deque) | `voice_converter.py` |
| 1c | `core/vad.py` (калибровка, record_until_silence, dynamic threshold) | `voice_converter.py` |
| 2 | `core/stt.py`, `core/__init__.py` (фабрика STT) | — |
| 3 | `core/ollama_client.py` (classify_error, retry), `core/prompt_manager.py` (strip_think_tags), `core/llm.py` (is_thinking_model), `core/__init__.py` (фабрика LLM) | `benchmark_runner.py` |
| 4 | `core/tts.py`, `core/tts_utils.py`, `core/__init__.py` (фабрика TTS) | — |
| 5 | `main.py` (консольный режим) | — |
| 6 | `ipc/protocol.py`, `ipc/schemas.py`, `ipc/server.py`, `ipc/client.py` | — |
| 7 | `ui/tkinter_ui.py` (level bar, threshold/noise lines, service indicators) | `voice_converter.py` |
| 8 | `tests/test_*.py`, `README.md`, `.gitignore`, LICENSE | — |

---

## Ключевые решения из референсных проектов

**Из `benchmark_runner.py` (LM Studio бенчмарк):**
1. `strip_think_tags` с поддержкой незакрытых тегов — Этап 3
2. Таксономия ошибок API с retry только для retriable — Этап 3
3. Детектор thinking-моделей + адаптивный `max_tokens` — Этап 3
4. `save_state_atomic` (tmp → replace) — Этап 0

**Из `voice_converter.py` (speech2txt с VAD):**
1. Фоновый `AudioStream` с chunk-by-chunk RMS — Этап 1b
2. Калибровка `max_rms * 1.8` при старте — Этап 1c
3. Скользящее среднее шума через `deque` — Этап 1b
4. Dynamic VAD: `threshold = threshold*(1-damping) + rms*damping*ratio` — Этап 1c
5. Pause-based end-of-utterance (1 сек тишины) — Этап 1c
6. Визуализация уровня/порога/шума в UI — Этап 7
