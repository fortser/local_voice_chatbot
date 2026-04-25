"""DevicesPanel — текущие аудио-устройства Windows + заряд BT-устройств.

* Аудио-устройства (микрофон и выход) тянутся из ``utils.audio_devices`` —
  это те же дефолты, что Windows показывает в «Параметры → Звук».
* BT-батарея читается через ``utils.bluetooth_battery`` (PowerShell PnP).
  Поллинг — в фоновом :class:`QThread`, чтобы 1–3 секунды на PowerShell
  не лочили UI.

Ничего не настраивает: только показывает. Менять устройства — в Windows.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import (
    QObject,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from utils.audio_devices import DeviceInfo, get_current_devices
from utils.bluetooth_battery import (
    BluetoothBattery,
    bt_matches_audio,
    get_battery_levels,
)

logger = logging.getLogger(__name__)


# ---- background BT poller ---------------------------------------------------


class _BtPoller(QObject):
    """Тянет get_battery_levels() по таймеру в собственном потоке."""

    levels_updated = Signal(list)  # list[BluetoothBattery]

    def __init__(self, interval_ms: int = 60_000) -> None:
        super().__init__()
        self._interval_ms = interval_ms
        self._timer: QTimer | None = None

    @Slot()
    def start(self) -> None:
        # Первый опрос — сразу, дальше — по таймеру.
        self._tick()
        timer = QTimer(self)
        timer.setInterval(self._interval_ms)
        timer.timeout.connect(self._tick)
        timer.start()
        self._timer = timer

    @Slot()
    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    def _tick(self) -> None:
        try:
            levels = get_battery_levels()
        except Exception:
            logger.exception("BT poll failed")
            return
        self.levels_updated.emit(levels)


# ---- BT row -----------------------------------------------------------------


class _BatteryRow(QWidget):
    """Имя устройства + полоска заряда + проценты."""

    def __init__(self, name: str, percent: int) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self._name = QLabel(name)
        self._name.setMinimumWidth(160)
        self._name.setToolTip(name)
        layout.addWidget(self._name, stretch=1)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setFixedWidth(120)
        self._bar.setFixedHeight(14)
        self._bar.setTextVisible(False)
        layout.addWidget(self._bar)

        self._pct = QLabel("—")
        self._pct.setMinimumWidth(40)
        f = QFont("Consolas")
        f.setPointSize(9)
        self._pct.setFont(f)
        layout.addWidget(self._pct)

        self.set_percent(percent)

    def set_name(self, name: str) -> None:
        self._name.setText(name)
        self._name.setToolTip(name)

    def set_percent(self, percent: int) -> None:
        percent = max(0, min(100, int(percent)))
        self._bar.setValue(percent)
        if percent <= 15:
            color = "#c93f3f"
        elif percent <= 35:
            color = "#e1c340"
        else:
            color = "#3bb143"
        self._bar.setStyleSheet(
            "QProgressBar { background:#eee8d5; border:1px solid #93a1a1; "
            "border-radius:3px; }"
            f"QProgressBar::chunk {{ background:{color}; border-radius:2px; }}"
        )
        self._pct.setText(f"{percent}%")


# ---- main panel -------------------------------------------------------------


class DevicesPanel(QGroupBox):
    """Группа: микрофон / выход + список BT-устройств с зарядом."""

    AUDIO_POLL_MS = 5_000   # дефолтное устройство Windows может смениться
    BT_POLL_MS = 60_000     # PowerShell-вызов медленный, чаще не нужно

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Устройства", parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(6)

        # ---- audio rows ---------------------------------------------------
        self._mic_label = QLabel("🎤 Микрофон: —")
        self._mic_label.setWordWrap(True)
        layout.addWidget(self._mic_label)

        self._out_label = QLabel("🔊 Выход: —")
        self._out_label.setWordWrap(True)
        layout.addWidget(self._out_label)

        # ---- separator ----------------------------------------------------
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        # ---- BT header + body --------------------------------------------
        self._bt_header = QLabel("🔋 Bluetooth-устройства")
        f = QFont()
        f.setBold(True)
        self._bt_header.setFont(f)
        layout.addWidget(self._bt_header)

        self._bt_body = QVBoxLayout()
        self._bt_body.setSpacing(2)
        self._bt_body.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._bt_body)

        self._bt_empty = QLabel(
            "(текущий микрофон/выход — не Bluetooth)"
        )
        self._bt_empty.setStyleSheet("color:#586e75;")
        self._bt_empty.setWordWrap(True)
        self._bt_body.addWidget(self._bt_empty)

        self._bt_rows: dict[str, _BatteryRow] = {}
        # Кеш последних аудио-имён и BT-снимка — чтобы при смене устройств
        # пере-фильтровать показ без ожидания следующего PowerShell-опроса.
        self._audio_names: list[str] = []
        self._last_bt_levels: list[BluetoothBattery] = []

        layout.addStretch(1)

        # ---- audio polling timer (UI thread, лёгкий вызов sounddevice) ----
        self._audio_timer = QTimer(self)
        self._audio_timer.setInterval(self.AUDIO_POLL_MS)
        self._audio_timer.timeout.connect(self._refresh_audio)

        # ---- BT polling thread -------------------------------------------
        self._bt_thread = QThread(self)
        self._bt_poller = _BtPoller(interval_ms=self.BT_POLL_MS)
        self._bt_poller.moveToThread(self._bt_thread)
        self._bt_thread.started.connect(self._bt_poller.start)
        self._bt_poller.levels_updated.connect(self._on_bt_levels)

        self._refresh_audio()
        self._audio_timer.start()
        # В тестах/валидаторах BT-поллинг отключаем — PowerShell-вызовы медленные
        # и для проверки layout'а не нужны.
        if os.environ.get("SHURA_DISABLE_BT_POLL") != "1":
            self._bt_thread.start()

    # ---- audio --------------------------------------------------------------

    def _refresh_audio(self) -> None:
        try:
            in_info, out_info = get_current_devices()
        except Exception:
            logger.exception("get_current_devices failed")
            return
        self._mic_label.setText("🎤 Микрофон: " + _format_device(in_info))
        self._out_label.setText("🔊 Выход: " + _format_device(out_info))
        new_names = [d.name for d in (in_info, out_info) if d is not None]
        if new_names != self._audio_names:
            self._audio_names = new_names
            # Перерисовываем BT-секцию под новый набор аудио-устройств — иначе
            # пользователь увидит «старую» фильтрацию до следующего PowerShell.
            self._render_bt_rows()

    # ---- BT -----------------------------------------------------------------

    @Slot(list)
    def _on_bt_levels(self, levels: list) -> None:
        self._last_bt_levels = [lv for lv in levels if isinstance(lv, BluetoothBattery)]
        self._render_bt_rows()

    def _render_bt_rows(self) -> None:
        """Применить текущий фильтр и отрисовать BT-строки.

        Показываем заряд только для тех BT-устройств, которые сейчас
        выбраны в Windows как input/output. Если пересечений нет — секция
        свёрнута до подсказки.
        """
        filtered = [
            lv
            for lv in self._last_bt_levels
            if bt_matches_audio(lv.name, self._audio_names)
        ]

        seen: set[str] = set()
        for lv in filtered:
            seen.add(lv.name)
            row = self._bt_rows.get(lv.name)
            if row is None:
                row = _BatteryRow(lv.name, lv.percent)
                self._bt_rows[lv.name] = row
                self._bt_body.addWidget(row)
            else:
                row.set_percent(lv.percent)

        for name in list(self._bt_rows.keys()):
            if name not in seen:
                row = self._bt_rows.pop(name)
                row.setParent(None)
                row.deleteLater()

        self._bt_empty.setVisible(not self._bt_rows)

    # ---- shutdown -----------------------------------------------------------

    def shutdown(self) -> None:
        try:
            self._audio_timer.stop()
        except Exception:
            pass
        try:
            self._bt_poller.stop()
        except Exception:
            pass
        try:
            if self._bt_thread.isRunning():
                self._bt_thread.quit()
                self._bt_thread.wait(2000)
        except Exception:
            pass


def _format_device(info: DeviceInfo | None) -> str:
    if info is None:
        return "(не определено)"
    return f"{info.name} [{info.hostapi}]"
