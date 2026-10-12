"""Independent pages. They consume the backend contract, never VoicePipeline."""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

from .components import Card, LevelMeter, VoiceOrb, button, label


class OverviewPage(QWidget):
    def __init__(self, context) -> None:
        super().__init__()
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        hero = Card()
        row = QHBoxLayout()
        copy = QVBoxLayout()
        copy.addWidget(label("ВАШ ЛИЧНЫЙ АССИСТЕНТ", "eyebrow"))
        copy.addWidget(label("Скажите —\nя рядом.", "hero"))
        self.status = label("Нажмите «Начать работу», чтобы запустить ассистента", "muted")
        copy.addWidget(self.status)
        self.loading_status = label("", "muted")
        self.loading_status.hide()
        copy.addWidget(self.loading_status)
        copy.addSpacing(10)
        controls = QHBoxLayout()
        self.start = button("Начать работу", context.start_work, "primary")
        self.start.setToolTip("Загрузить модели и включить прослушивание кодового слова")
        self.pause = button("Остановить", context.toggle_listening)
        self.pause.setToolTip("Приостановить прослушивание кодового слова, сохранив модели в памяти")
        controls.addWidget(self.start)
        controls.addWidget(self.pause)
        copy.addLayout(controls)
        row.addLayout(copy, 3)
        self.orb = VoiceOrb()
        row.addWidget(self.orb, 2)
        hero.body.addLayout(row)
        layout.addWidget(hero)

        row = QHBoxLayout()
        row.setSpacing(18)
        microphone = Card("Микрофон")
        self.level = LevelMeter()
        self.level_text = label("Ожидание аудиопотока", "muted")
        microphone.body.addWidget(self.level)
        microphone.body.addWidget(self.level_text)
        self.standby = QCheckBox("Активация голосом")
        self.standby.setToolTip("Слушать кодовое слово в фоновом режиме")
        self.standby.toggled.connect(context.backend.request_toggle_standby)
        microphone.body.addWidget(self.standby)
        row.addWidget(microphone, 1)

        services = Card("Система")
        self.service_labels = {}
        for key, title in (("stt", "Распознавание речи"), ("llm", "Языковая модель"), ("tts", "Синтез голоса")):
            service = label(f"○   {title} · ожидание", "muted")
            services.body.addWidget(service)
            self.service_labels[key] = (title, service)
        row.addWidget(services, 1)
        layout.addLayout(row)

        audio = Card("Аудиоустройства")
        audio.body.addWidget(label("Устройства по умолчанию Windows · включая связь", "muted"))
        self.audio_combos = {}
        self.audio_labels = {}
        self._audio_snapshot = {}
        for direction, title in (("input", "Микрофон"), ("output", "Выход")):
            active = label(f"{title}: ожидание устройств", "muted")
            combo = QComboBox()
            combo.setAccessibleName(f"{title} по умолчанию Windows")
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(15)
            combo.activated.connect(lambda index, key=direction: self._select_audio(key, index))
            audio.body.addWidget(active)
            audio.body.addWidget(combo)
            self.audio_combos[direction] = combo
            self.audio_labels[direction] = active
        self.audio_refresh = button("Обновить устройства", context.backend.request_audio_devices)
        audio.body.addWidget(self.audio_refresh)
        hardware = QHBoxLayout()
        hardware.setSpacing(18)
        hardware.addWidget(audio, 2)

        gpu = Card("GPU")
        self.gpu_status = label("Ожидание показателей видеокарты", "muted")
        gpu.body.addWidget(self.gpu_status)
        gpu.body.addWidget(label("Загрузка и видеопамять всех процессов · обновление раз в секунду", "muted"))
        gpu.body.addStretch()
        hardware.addWidget(gpu, 1)
        layout.addLayout(hardware)

        recent = Card("Последний диалог")
        self.user_text = label("Здесь появится ваша голосовая команда.", "muted")
        self.answer = label("Нажмите «Начать работу», затем произнесите кодовое слово и команду.")
        self.answer.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.timing = label("Время ответа · —", "muted")
        recent.body.addWidget(self.user_text)
        recent.body.addWidget(self.answer)
        recent.body.addWidget(self.timing)
        self.history = button("Вся история  →", context.open_sessions)
        self.history.setToolTip("Открыть папку с сохранёнными заметками и снимками экрана")
        recent.body.addWidget(self.history)
        layout.addWidget(recent)
        layout.addStretch()
        context.backend.level_update.connect(self._level)
        context.backend.health_update.connect(self._health)
        context.backend.model_update.connect(self._health)
        context.backend.audio_devices_update.connect(self._audio_devices)
        context.backend.gpu_update.connect(self._gpu)
        context.backend.turn_result.connect(self._result)
        context.backend.standby_changed.connect(self._standby)

    def _level(self, rms: float, percent: int) -> None:
        self.level.set_level(rms, percent)
        self.orb.set_level(rms, percent)
        self.level_text.setText(f"Уровень входа · {max(0, min(percent, 100))}%")

    def _standby(self, enabled: bool) -> None:
        self.standby.blockSignals(True)
        self.standby.setChecked(enabled)
        self.standby.blockSignals(False)

    def _health(self, snapshot: dict) -> None:
        for key, (title, widget) in self.service_labels.items():
            if key not in snapshot:
                continue
            data = snapshot.get(key, {}) or {}
            good = data.get("healthy" if key == "llm" else "loaded", False)
            state = "готово" if good else "недоступно"
            if key == "tts" and data.get("gpu_swap") and not good:
                state = "загрузка по запросу"
            if key == "stt" and data.get("gpu_swap") and not good:
                state = "временно выгружена"
            details = ""
            if key in {"stt", "tts"}:
                provider = str(data.get("provider") or "")
                provider = {"WhisperSTT": "Whisper", "GigaAMSTT": "GigaAM", "SileroTTS": "Silero", "XTSTTTS": "XTTS"}.get(provider, provider)
                model = str(data.get("model") or "—")
                device = str(data.get("device") or "").lower()
                mode = "GPU" if device.startswith(("cuda", "gpu")) else "CPU" if device == "cpu" else "—"
                details = f"\n{provider} · {model} · {mode}"
            widget.setText(f"{'●' if good else '○'}   {title} · {state}{details}")
            widget.setToolTip(str(data.get("error") or data.get("device") or data.get("provider") or ""))

    def set_audio_enabled(self, enabled: bool) -> None:
        self.audio_refresh.setEnabled(enabled)
        for combo in self.audio_combos.values():
            combo.setEnabled(enabled and combo.count() > 0)

    def _audio_devices(self, snapshot: dict) -> None:
        self._audio_snapshot = snapshot
        if not snapshot.get("stream_running", True):
            self.level.set_level(0, 0)
            self.orb.set_level(0, 0)
            self.level_text.setText("Аудиопоток остановлен")
        for direction, title in (("input", "Микрофон"), ("output", "Выход")):
            info = snapshot.get(direction, {})
            active = (snapshot.get("active") or {}).get(direction)
            name = active.get("name", "—") if active else "недоступен"
            if direction == "input" and not snapshot.get("stream_running", True):
                name += " · поток остановлен"
            elif active and not snapshot.get("standalone") and active.get("id") != info.get("default_id"):
                name += " · ожидает переключения на выбор Windows"
            self.audio_labels[direction].setText(f"{title}: {name}")
            self.audio_labels[direction].setToolTip(name)
            combo = self.audio_combos[direction]
            # Do not move the user's pointer target while the popup is open.
            if combo.view().isVisible():
                continue
            combo.blockSignals(True)
            combo.clear()
            for endpoint in info.get("devices", []):
                combo.addItem(endpoint["name"], endpoint["id"])
                combo.setItemData(combo.count() - 1, endpoint["name"], Qt.ToolTipRole)
            selected = active.get("id") if snapshot.get("standalone") and active else info.get("default_id")
            combo.setCurrentIndex(combo.findData(selected))
            combo.blockSignals(False)
        self.set_audio_enabled(self.context.can_act)

    def _select_audio(self, direction: str, index: int) -> None:
        combo = self.audio_combos[direction]
        endpoint_id = combo.itemData(index)
        if self.context.can_act and endpoint_id:
            if self.context.backend.request_set_audio_device(direction, endpoint_id):
                self.context.set_state("switching_audio")
        self._audio_devices(self._audio_snapshot)

    def _gpu(self, snapshot: dict) -> None:
        rows = []
        for gpu in snapshot.get("devices", []):
            utilization = gpu.get("utilization")
            used, total = gpu.get("memory_used"), gpu.get("memory_total")
            load = f"{utilization}%" if utilization is not None else "—"
            memory = (f"{used / 1024**3:.2f} / {total / 1024**3:.2f} ГиБ"
                      if used is not None and total is not None else "—")
            rows.append(f"{gpu['name']}\nЗагрузка: {load} · Видеопамять: {memory}")
        self.gpu_status.setText("\n\n".join(rows) if rows else snapshot.get("error") or "Мониторинг недоступен")

    def _result(self, result) -> None:
        user = getattr(result, "user_text", "") or "Речь не распознана"
        answer = getattr(result, "error", None) or getattr(result, "llm_text", "") or "Обработка завершена."
        self.user_text.setText("ВЫ   " + user[:240] + ("…" if len(user) > 240 else ""))
        self.answer.setText(answer[:400] + ("…" if len(answer) > 400 else ""))
        self.timing.setText(f"Время ответа · {getattr(result, 'total_s', 0):.1f} с")


class HistoryPage(QWidget):
    LIMIT = 200

    def __init__(self, context) -> None:
        super().__init__()
        self.entries: list[tuple[str, str, str, str]] = []
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти в диалогах…")
        self.search.setAccessibleName("Поиск в истории")
        self.search.textChanged.connect(self._render)
        toolbar.addWidget(self.search, 1)
        self.export = button("Экспорт", self._export)
        toolbar.addWidget(self.export)
        toolbar.addWidget(button("Очистить", self._clear))
        layout.addLayout(toolbar)
        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.document().setDefaultStyleSheet(
            "body {color:#edf3f2;} p {line-height:150%;} "
            "h3 {color:#a8ebce;font-size:14px;} small {color:#9cabb2;}"
        )
        layout.addWidget(self.browser, 1)
        layout.addWidget(label("Последние 200 диалогов этой сессии. История хранится только в памяти.", "muted"))
        context.backend.turn_result.connect(self._add)
        self._render()

    def _add(self, result) -> None:
        self.entries.append((datetime.now().strftime("%H:%M"), getattr(result, "user_text", "") or "",
                             getattr(result, "llm_text", "") or "", getattr(result, "error", "") or ""))
        self.entries = self.entries[-self.LIMIT:]
        self._render()

    def _render(self) -> None:
        query = self.search.text().casefold().strip()
        parts = []
        for stamp, user, answer, error in reversed(self.entries):
            if query and query not in f"{user} {answer} {error}".casefold():
                continue
            safe = lambda value: escape(value).replace("\n", "<br>")
            parts.append(f"<h3>{stamp} · Вы</h3><p>{safe(user) or 'Речь не распознана'}</p>"
                         f"<h3>Шурочка</h3><p>{safe(answer) or 'Обработка завершена.'}</p>"
                         + (f"<p style='color:#ffafa8'>{safe(error)}</p>" if error else "") + "<hr>")
        self.browser.setHtml("".join(parts) or "<h3>Пока ничего нет</h3><p>Здесь появятся диалоги, соответствующие поиску.</p>")
        self.export.setEnabled(bool(self.entries))

    def _clear(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        if self.entries and QMessageBox.question(self, "Очистить историю?", "Диалоги этой сессии будут удалены из окна.",
                                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.entries.clear()
            self._render()

    def _export(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Сохранить историю", "shura-dialogs.txt", "Текст (*.txt)")
        if filename:
            try:
                Path(filename).write_text("\n\n".join(
                    f"{stamp}\nВы: {user}\nШурочка: {answer}" + (f"\nОшибка: {error}" if error else "")
                    for stamp, user, answer, error in self.entries), encoding="utf-8")
            except OSError as exc:
                self.context.notify(f"Не удалось сохранить историю: {exc}")


class CommandsPage(QWidget):
    def __init__(self, context) -> None:
        super().__init__()
        self.commands = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label("Ваши голосовые команды", "section"))
        layout.addWidget(label("Список учитывает пользовательские фразы из конфигурации. Выберите команду, чтобы скопировать пример.", "muted"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по названию или голосовой фразе…")
        self.search.setAccessibleName("Поиск команды")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        layout.addWidget(self.list, 1)
        footer = QHBoxLayout()
        self.count = label("Команды появятся после запуска ядра", "muted")
        footer.addWidget(self.count, 1)
        self.copy = button("Копировать фразу", self._copy)
        self.copy.setEnabled(False)
        self.list.currentItemChanged.connect(lambda item, previous: self.copy.setEnabled(item is not None))
        footer.addWidget(self.copy)
        layout.addLayout(footer)
        context.backend.commands_list.connect(self._load)

    def _load(self, commands) -> None:
        self.commands = list(commands)
        self._filter()

    def _filter(self) -> None:
        self.list.clear()
        query = self.search.text().casefold().strip()
        for command in self.commands:
            phrases = command["synonyms"]
            title = phrases[0].capitalize() if phrases else command["name"]
            details = " · ".join(phrases)
            if query not in f"{command['name']} {details} {command.get('description', '')}".casefold():
                continue
            item = QListWidgetItem(f"{title}\n{details}")
            item.setData(Qt.UserRole, phrases[0] if phrases else command["name"])
            item.setToolTip(details)
            self.list.addItem(item)
        self.count.setText(f"Показано {self.list.count()} из {len(self.commands)} команд")

    def _copy(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            QApplication.clipboard().setText(item.data(Qt.UserRole))


STT_PROVIDER_TITLES = (
    ("whisper", "Whisper (OpenAI) — по умолчанию"),
    ("gigaam", "GigaAM-v3 (Сбер) — только русский, меньше галлюцинаций"),
)


class SettingsPage(QWidget):
    def __init__(self, context) -> None:
        super().__init__()
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        model_card = Card("Языковая модель")
        model_card.body.addWidget(label("Выберите модель из запущенного Ollama или LM Studio. Смена действует в текущей сессии.", "muted"))
        row = QHBoxLayout()
        self.models = QComboBox()
        self.models.setMinimumWidth(200)
        self.models.setAccessibleName("Языковая модель")
        self.models.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.models.setMinimumContentsLength(20)
        row.addWidget(self.models, 1)
        self.refresh = button("Обновить", context.backend.request_list_models)
        self.apply = button("Применить", self._apply, "primary")
        row.addWidget(self.refresh)
        row.addWidget(self.apply)
        model_card.body.addLayout(row)
        self.model_status = label("Модели ещё не загружены", "muted")
        model_card.body.addWidget(self.model_status)
        layout.addWidget(model_card)

        audio = Card("Голос и микрофон")
        audio.body.addWidget(label("Если ассистент реагирует на шум, выполните калибровку. Во время измерения сохраняйте тишину.", "muted"))
        self.calibrate = button("Откалибровать микрофон", context.calibrate)
        audio.body.addWidget(self.calibrate)
        self.audio_status = label("Параметры аудио появятся после запуска", "muted")
        audio.body.addWidget(self.audio_status)
        layout.addWidget(audio)

        speech = Card("Распознавание речи")
        speech.body.addWidget(label("Модель распознавания. Смена применяется после перезапуска программы.", "muted"))
        self.stt_provider = QComboBox()
        self.stt_provider.setAccessibleName("Модель распознавания речи")
        for value, title in STT_PROVIDER_TITLES:
            self.stt_provider.addItem(title, value)
        index = self.stt_provider.findData(context.backend.saved_stt_provider)
        self.stt_provider.setCurrentIndex(max(0, index))
        self.stt_provider.currentIndexChanged.connect(self._stt_provider)
        speech.body.addWidget(self.stt_provider)
        self.stt_provider_status = label("", "muted")
        self.stt_provider_status.setWordWrap(True)
        speech.body.addWidget(self.stt_provider_status)
        self.speech_gate = QCheckBox("Не распознавать звук без речи (нейросетевой фильтр Silero VAD)")
        self.speech_gate.setChecked(context.backend.speech_gate_enabled)
        self.speech_gate.toggled.connect(self._speech_gate)
        speech.body.addWidget(self.speech_gate)
        self.stt_filter = QCheckBox("Удалять типичные галлюцинации («Продолжение следует», «Спасибо за просмотр»)")
        self.stt_filter.setChecked(context.backend.stt_filter_enabled)
        self.stt_filter.toggled.connect(self._stt_filter)
        speech.body.addWidget(self.stt_filter)
        self.speech_filters_status = label("", "muted")
        self.speech_filters_status.setWordWrap(True)
        speech.body.addWidget(self.speech_filters_status)
        layout.addWidget(speech)
        self._update_speech_status()

        appearance = Card("Интерфейс")
        self.animation = QCheckBox("Анимация голосового индикатора")
        self.animation.setChecked(context.settings.value("animation", True, type=bool))
        self.animation.toggled.connect(self._animation)
        appearance.body.addWidget(self.animation)
        appearance.body.addWidget(label("Ctrl+Space — запись     Esc — отмена     Ctrl+1…6 — разделы", "muted"))
        layout.addWidget(appearance)

        notes = Card("Заметки")
        self.note_journal = QCheckBox("Сохранять заметки со скриншотом в HTML-журнал")
        self.note_journal.setChecked(context.backend.note_journal_enabled)
        self.note_journal.toggled.connect(self._note_journal)
        notes.body.addWidget(self.note_journal)
        notes.body.addWidget(label(
            "Снимок делается в начале команды. Заметки сохраняются в TXT и в общий "
            "HTML-журнал месяца. Нажмите на миниатюру в журнале, чтобы увеличить снимок. "
            "Настройка применяется к следующим заметкам без перезапуска.", "muted"))
        notes.body.addWidget(button("Открыть журнал текущего месяца", self._open_note_journal))
        layout.addWidget(notes)

        files = Card("Файлы и конфигурация")
        files.body.addWidget(label("Провайдеры и голос задаются в settings.toml. Изменения в файле применяются после перезапуска. Аудиоустройства Windows переключаются на странице «Обзор».", "muted"))
        row = QHBoxLayout()
        row.addWidget(button("Открыть папку проекта", lambda: self._open(Path(__file__).resolve().parents[2])))
        row.addWidget(button("Заметки и снимки", context.open_sessions))
        files.body.addLayout(row)
        layout.addWidget(files)
        layout.addStretch()
        context.backend.models_list.connect(self._models)
        context.backend.health_update.connect(self._health)

    def _models(self, models, current) -> None:
        self.models.clear()
        values = list(models or [])
        if current and current not in values:
            values.insert(0, current)
        self.models.addItems(values)
        if current:
            self.models.setCurrentText(current)
        self.model_status.setText(f"Текущая модель: {current}" if current else "Модель не выбрана")
        self.apply.setEnabled(self.context.can_act and bool(values))

    def _apply(self) -> None:
        if self.context.can_act and self.models.currentText():
            self.context.set_state("warming", self.models.currentText())
            self.context.backend.request_set_model(self.models.currentText())

    def _health(self, snapshot: dict) -> None:
        audio = snapshot.get("audio", {})
        noise, threshold = audio.get("noise_rms"), audio.get("threshold")
        if noise is not None and threshold is not None:
            self.audio_status.setText(f"Фоновый шум: {noise:.1f} · Порог речи: {threshold:.1f}")

    def _animation(self, enabled: bool) -> None:
        if not self.context.preview:
            self.context.settings.setValue("animation", enabled)
        self.context.overview.orb.set_animated(enabled)
        floating = self.context.pages["stt"].floating
        if floating:
            floating.toggle.orb.set_animated(enabled)

    def _update_speech_status(self) -> None:
        backend = self.context.backend
        chosen = self.stt_provider.currentData()
        lines = []
        if chosen == backend.active_stt_provider:
            lines.append("Используется сейчас.")
        else:
            lines.append("Будет использована после перезапуска программы.")
        if chosen == "gigaam":
            missing = backend.missing_packages("gigaam")
            if missing:
                lines.append("Не хватает пакетов: " + ", ".join(missing)
                             + ". Установите: pip install -r requirements-gigaam.txt")
            else:
                lines.append("Только русский язык. Веса скачиваются при первом запуске в папку models/gigaam.")
        self.stt_provider_status.setText(" ".join(lines))
        notes = ["Фильтры действуют сразу. Пороги и свои фразы — в settings.toml, секции [speech_gate] и [stt.filter]."]
        if self.speech_gate.isChecked() and backend.missing_packages("speech_gate"):
            notes.insert(0, "Пакет silero-vad не установлен — фильтр речи пропускает звук без проверки. "
                            "Установите: pip install silero-vad")
        self.speech_filters_status.setText(" ".join(notes))

    def _restore(self, widget, value) -> None:
        widget.blockSignals(True)
        if isinstance(widget, QComboBox):
            widget.setCurrentIndex(max(0, widget.findData(value)))
        else:
            widget.setChecked(value)
        widget.blockSignals(False)

    def _stt_provider(self, _index: int) -> None:
        value = self.stt_provider.currentData()
        if not self.context.preview and not self.context.backend.set_stt_provider(value):
            self._restore(self.stt_provider, self.context.backend.saved_stt_provider)
        self._update_speech_status()

    def _speech_gate(self, enabled: bool) -> None:
        if not self.context.preview and not self.context.backend.set_speech_gate_enabled(enabled):
            self._restore(self.speech_gate, self.context.backend.speech_gate_enabled)
        self._update_speech_status()

    def _stt_filter(self, enabled: bool) -> None:
        if not self.context.preview and not self.context.backend.set_stt_filter_enabled(enabled):
            self._restore(self.stt_filter, self.context.backend.stt_filter_enabled)

    def _note_journal(self, enabled: bool) -> None:
        if self.context.preview:
            return
        if not self.context.backend.set_note_journal_enabled(enabled):
            self.note_journal.blockSignals(True)
            self.note_journal.setChecked(self.context.backend.note_journal_enabled)
            self.note_journal.blockSignals(False)

    def _open_note_journal(self) -> None:
        from config import SESSION_BASE_DIR
        from system.note_journal import JOURNAL_FILE

        path = (Path(SESSION_BASE_DIR).expanduser().resolve()
                / datetime.now().strftime("%Y-%m") / JOURNAL_FILE)
        if not path.is_file():
            self.context.notify("Журнал появится после первой заметки с включённым HTML-режимом.")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.context.notify("Не удалось открыть журнал заметок.")

    def _open(self, path: Path) -> None:
        if not path.exists():
            self.context.notify("Папка ещё не создана. Она появится после первой заметки или снимка.")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.context.notify("Не удалось открыть папку.")
