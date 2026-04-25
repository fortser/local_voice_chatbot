"""Функциональный Dashboard 960×640 (Этап 4 + ревизия).

Двухколоночный layout:

* Левая колонка — оперативная панель: статус, LevelMeter, последний оборот,
  тайминги, ряд LLM-модели, 4 кнопки управления.
* Правая колонка — :class:`DevicesPanel` (текущий микрофон / выход Windows
  и заряд парных Bluetooth-устройств).

Внизу — status bar с тремя цветными точками (STT/LLM/TTS) и строкой статуса.
Кнопка ⚙ открывает заглушку Settings (полноценный экран — Этап 5).
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .bridge import PipelineBridge
from .widgets.devices_panel import DevicesPanel
from .widgets.level_meter import LevelMeter
from .widgets.status_indicator import StatusIndicator

logger = logging.getLogger(__name__)


def _fmt_ms(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f} мс".replace(",", " ")


class _HealthDot(QLabel):
    """Кружок-индикатор здоровья сервиса (STT/LLM/TTS) для статус-бара."""

    _COLORS = {
        "ok": "#3bb143",
        "warn": "#e1c340",
        "err": "#c93f3f",
        "off": "#888888",
    }

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = label
        self._set("off")

    def _set(self, kind: str) -> None:
        color = self._COLORS.get(kind, self._COLORS["off"])
        self.setText(
            f"<span style='color:{color}; font-size:14pt;'>●</span> "
            f"<span>{self._label}</span>"
        )

    def set_ok(self) -> None: self._set("ok")
    def set_warn(self) -> None: self._set("warn")
    def set_err(self) -> None: self._set("err")
    def set_off(self) -> None: self._set("off")


class DashboardWindow(QMainWindow):
    """Пульт управления 960×640, двухколоночный."""

    WINDOW_WIDTH = 960
    WINDOW_HEIGHT = 640

    def __init__(self, bridge: PipelineBridge) -> None:
        super().__init__()
        self._bridge = bridge

        self.setWindowTitle("Шурочка — Dashboard")
        self.setMinimumSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        self.resize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)

        central = QWidget(self)
        self.setCentralWidget(central)

        outer = QHBoxLayout(central)
        outer.setContentsMargins(14, 12, 14, 8)
        outer.setSpacing(12)

        outer.addLayout(self._build_left_column(), stretch=3)
        self._devices_panel = DevicesPanel()
        self._devices_panel.setMinimumWidth(320)
        outer.addWidget(self._devices_panel, stretch=2)

        # ---- status bar (внизу) ------------------------------------------
        status = QStatusBar(self)
        self._dot_stt = _HealthDot("STT")
        self._dot_llm = _HealthDot("LLM")
        self._dot_tts = _HealthDot("TTS")
        for d in (self._dot_stt, self._dot_llm, self._dot_tts):
            status.addPermanentWidget(d)
        self._status_msg = QLabel("Инициализация…")
        status.addWidget(self._status_msg, stretch=1)
        self.setStatusBar(status)

        # ---- bridge wiring -----------------------------------------------
        bridge.state_changed.connect(self._on_state_changed)
        bridge.level_update.connect(self._level.set_level)
        bridge.turn_result.connect(self._on_turn_result)
        bridge.health_update.connect(self._on_health)
        bridge.models_list.connect(self._on_models_list)
        bridge.model_applied.connect(self._on_model_applied)
        bridge.model_error.connect(self._on_model_error)
        bridge.ipc_changed.connect(self._on_ipc_changed)
        bridge.ready.connect(self._on_ready)
        bridge.fatal.connect(self._on_fatal)
        bridge.error_message.connect(
            lambda msg: self._status_msg.setText(f"⚠ {msg}")
        )

        self._set_action_buttons_enabled(False)

    # ---- layout helpers ---------------------------------------------------

    def _build_left_column(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(10)

        # ---- header (status + cog) ---------------------------------------
        header = QHBoxLayout()
        header.setSpacing(8)
        self._status = StatusIndicator()
        header.addWidget(self._status, stretch=1)

        self._settings_btn = QToolButton()
        self._settings_btn.setText("⚙")
        font = QFont()
        font.setPointSize(14)
        self._settings_btn.setFont(font)
        self._settings_btn.setToolTip("Настройки (Этап 5)")
        self._settings_btn.clicked.connect(self._on_open_settings)
        header.addWidget(self._settings_btn)
        col.addLayout(header)

        # ---- level meter group --------------------------------------------
        level_group = QGroupBox("Уровень микрофона")
        lg_layout = QVBoxLayout(level_group)
        lg_layout.setContentsMargins(10, 14, 10, 10)
        lg_layout.setSpacing(4)
        self._level = LevelMeter()
        self._level.setMinimumHeight(36)
        lg_layout.addWidget(self._level)
        self._level_info = QLabel("RMS: —   Шум: —   Порог: —")
        f_lvl = QFont("Consolas")
        f_lvl.setPointSize(9)
        self._level_info.setFont(f_lvl)
        lg_layout.addWidget(self._level_info)
        col.addWidget(level_group)

        # ---- last turn group ----------------------------------------------
        turn_group = QGroupBox("Последний оборот")
        tg_layout = QVBoxLayout(turn_group)
        tg_layout.setContentsMargins(10, 14, 10, 10)
        tg_layout.setSpacing(6)

        self._user_label = QLabel("Вы: —")
        self._user_label.setWordWrap(True)
        self._user_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        f_body = QFont()
        f_body.setPointSize(11)
        self._user_label.setFont(f_body)
        self._user_label.setMinimumHeight(48)
        tg_layout.addWidget(self._user_label)

        self._llm_label = QLabel("Шурочка: —")
        self._llm_label.setWordWrap(True)
        self._llm_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._llm_label.setFont(f_body)
        self._llm_label.setMinimumHeight(72)
        tg_layout.addWidget(self._llm_label, stretch=1)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        tg_layout.addWidget(sep)

        self._timing_label = QLabel(
            "STT: —    LLM: —    TTS: —    Σ: —"
        )
        f_t = QFont("Consolas")
        f_t.setPointSize(9)
        self._timing_label.setFont(f_t)
        tg_layout.addWidget(self._timing_label)

        self._tokens_label = QLabel("токены: —")
        self._tokens_label.setFont(f_t)
        self._tokens_label.setStyleSheet("color:#586e75;")
        tg_layout.addWidget(self._tokens_label)
        col.addWidget(turn_group, stretch=1)

        # ---- LLM model row ------------------------------------------------
        llm_group = QGroupBox("Языковая модель")
        llm_row = QHBoxLayout(llm_group)
        llm_row.setContentsMargins(10, 14, 10, 10)
        llm_row.setSpacing(6)
        self._model_combo = QComboBox()
        self._model_combo.setEditable(False)
        llm_row.addWidget(self._model_combo, stretch=1)

        self._refresh_models_btn = QPushButton("⟳ Обновить")
        self._refresh_models_btn.clicked.connect(self._bridge.request_list_models)
        llm_row.addWidget(self._refresh_models_btn)

        self._apply_model_btn = QPushButton("Применить")
        self._apply_model_btn.clicked.connect(self._on_apply_model)
        llm_row.addWidget(self._apply_model_btn)
        col.addWidget(llm_group)

        # ---- 4 action buttons --------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        def _make_btn(text: str) -> QPushButton:
            btn = QPushButton(text)
            btn.setMinimumHeight(36)
            return btn

        self.btn_listen = _make_btn("🎤 Слушать")
        self.btn_listen.clicked.connect(self._bridge.request_turn)
        btn_row.addWidget(self.btn_listen)

        self.btn_stop = _make_btn("⏹ Стоп")
        self.btn_stop.clicked.connect(self._bridge.request_cancel)
        btn_row.addWidget(self.btn_stop)

        self.btn_standby = _make_btn("🛌 Дежурный")
        self.btn_standby.setCheckable(True)
        self.btn_standby.toggled.connect(self._on_standby_toggled)
        btn_row.addWidget(self.btn_standby)

        self.btn_recal = _make_btn("🔄 Калибровка")
        self.btn_recal.clicked.connect(self._bridge.request_recalibrate)
        btn_row.addWidget(self.btn_recal)
        col.addLayout(btn_row)

        return col

    # ---- bridge handlers --------------------------------------------------

    @Slot(str, object)
    def _on_state_changed(self, name: str, detail: object) -> None:
        self._status.set_state(name, detail)
        pipeline = self._bridge.pipeline
        if name == "idle" and pipeline is not None and pipeline.vad is not None:
            self._level.set_vad(
                float(pipeline.vad.noise_rms), float(pipeline.vad.threshold)
            )
            self._refresh_level_text()

    def _refresh_level_text(self) -> None:
        m = self._level
        self._level_info.setText(
            f"RMS: {m.rms:>6.0f} ({m.percent:>3}%)   "
            f"Шум: {m.noise_rms:>5.0f}   "
            f"Порог: {m.threshold:>5.0f}"
        )

    @Slot(object)
    def _on_turn_result(self, result: Any) -> None:
        user_text = (getattr(result, "user_text", "") or "").strip() or "—"
        llm_text = (getattr(result, "llm_text", "") or "").strip() or "—"
        self._user_label.setText(f"Вы: {user_text}")
        self._llm_label.setText(f"Шурочка: {llm_text}")
        stt_ms = getattr(result, "stt_ms", None)
        llm_ms = getattr(result, "llm_ms", None)
        tts_ms = getattr(result, "tts_ms", None)
        total_s = getattr(result, "total_s", None)
        total_ms = total_s * 1000 if total_s else None
        self._timing_label.setText(
            f"STT: {_fmt_ms(stt_ms)}    LLM: {_fmt_ms(llm_ms)}    "
            f"TTS: {_fmt_ms(tts_ms)}    Σ: {_fmt_ms(total_ms)}"
        )
        prom = getattr(result, "llm_prompt_tokens", None)
        comp = getattr(result, "llm_completion_tokens", None)
        if prom is not None or comp is not None:
            parts = []
            if prom is not None:
                parts.append(f"prompt={prom}")
            if comp is not None:
                parts.append(f"completion={comp}")
            if prom is not None and comp is not None:
                parts.append(f"всего={prom + comp}")
            self._tokens_label.setText("токены: " + ", ".join(parts))
        else:
            self._tokens_label.setText("токены: —")

        err = getattr(result, "error", None)
        if err:
            self._status_msg.setText(f"⚠ последний оборот: {err}")
        else:
            self._status_msg.setText("оборот завершён")

    @Slot(dict)
    def _on_health(self, snap: dict) -> None:
        stt = snap.get("stt", {}) or {}
        llm = snap.get("llm", {}) or {}
        tts = snap.get("tts", {}) or {}
        audio = snap.get("audio", {}) or {}

        if stt.get("loaded"):
            self._dot_stt.set_ok()
        else:
            self._dot_stt.set_warn()

        if llm.get("healthy"):
            self._dot_llm.set_ok()
        else:
            self._dot_llm.set_err()

        if tts.get("loaded"):
            self._dot_tts.set_ok()
        else:
            self._dot_tts.set_warn()

        noise = audio.get("noise_rms")
        thr = audio.get("threshold")
        if noise is not None and thr is not None:
            self._level.set_vad(float(noise), float(thr))
            self._refresh_level_text()

    @Slot(object, object)
    def _on_models_list(self, models: object, current: object) -> None:
        values = list(models) if models else []
        self._model_combo.blockSignals(True)
        try:
            self._model_combo.clear()
            self._model_combo.addItems(values)
            if current and current in values:
                self._model_combo.setCurrentText(str(current))
        finally:
            self._model_combo.blockSignals(False)

    @Slot(str, float, bool)
    def _on_model_applied(self, name: str, elapsed: float, thinking: bool) -> None:
        suffix = " (thinking)" if thinking else ""
        self._status_msg.setText(
            f"✓ модель «{name}» прогрета за {elapsed:.1f}с{suffix}"
        )

    @Slot(str)
    def _on_model_error(self, msg: str) -> None:
        self._status_msg.setText(f"✗ {msg}")

    @Slot(object)
    def _on_ipc_changed(self, ok: object) -> None:
        if ok is True:
            self._status_msg.setText("IPC: активен")
        elif ok is False:
            self._status_msg.setText("IPC: не стартовал (порт занят?)")

    @Slot()
    def _on_ready(self) -> None:
        self._set_action_buttons_enabled(True)
        listener = self._bridge.wake_listener
        if listener is not None and getattr(listener, "is_enabled", False):
            self.btn_standby.blockSignals(True)
            self.btn_standby.setChecked(True)
            self.btn_standby.blockSignals(False)
        self._status_msg.setText("готов")

    @Slot(str)
    def _on_fatal(self, msg: str) -> None:
        self._set_action_buttons_enabled(False)
        QMessageBox.critical(self, "Шурочка — ошибка", msg)
        self._status_msg.setText(f"❌ {msg}")

    # ---- UI actions -------------------------------------------------------

    def _on_apply_model(self) -> None:
        name = self._model_combo.currentText().strip()
        if not name:
            self._status_msg.setText("выберите модель")
            return
        self._status_msg.setText(f"применяю «{name}»…")
        self._bridge.request_set_model(name)

    def _on_standby_toggled(self, checked: bool) -> None:
        self._bridge.request_toggle_standby(checked)

    def _on_open_settings(self) -> None:
        QMessageBox.information(
            self,
            "Настройки",
            "Окно настроек появится на Этапе 5.\n"
            "Сейчас доступен только пульт.",
        )

    def _set_action_buttons_enabled(self, enabled: bool) -> None:
        for btn in (
            self.btn_listen,
            self.btn_stop,
            self.btn_standby,
            self.btn_recal,
            self._apply_model_btn,
            self._refresh_models_btn,
            self._model_combo,
        ):
            btn.setEnabled(enabled)

    # ---- close handling ---------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        try:
            self._devices_panel.shutdown()
        except Exception:
            logger.exception("DevicesPanel.shutdown raised")
        try:
            self._bridge.shutdown()
        except Exception:
            logger.exception("bridge.shutdown raised on close")
        super().closeEvent(event)
