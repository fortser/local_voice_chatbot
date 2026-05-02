"""Ручная приёмка Этапа 4: функциональный PySide6 Dashboard.

Автоматические проверки (offscreen, без реального pipeline):
  1. Импорты ui.pyside6.* (app/bridge/dashboard/widgets) проходят.
  2. PipelineBridge имеет публичный API: start_pipeline / request_turn /
     request_recalibrate / request_list_models / request_set_model /
     request_cancel / request_toggle_standby / shutdown.
  3. PipelineBridge эмитит state_changed, level_update, turn_result,
     health_update, models_list, model_applied, model_error, ipc_changed,
     ready, fatal.
  4. DashboardWindow собирается под заглушечный PipelineBridge без падения,
     размер 420×320, кнопки на месте, все 4 action-кнопки disabled до ready.
  5. После эмита bridge.ready() кнопки разблокированы.
  6. Эмит bridge.level_update(rms, pct) обновляет LevelMeter.
  7. Эмит bridge.turn_result(<TurnResult-like>) заполняет панель оборота.
  8. Эмит bridge.state_changed("listening", None) меняет иконку на 🔴.

Ручная часть (y/N) — пользователь подтверждает:
  - python main.py --ui pyside6 — окно открылось, статус прошёл
    starting → calibrating → idle, кнопки разблокировались;
  - живой RMS-bar (LevelMeter) дрожит когда говоришь;
  - «🎤 Слушать» отрабатывает полный turn, тайминги STT/LLM/TTS появляются;
  - смена LLM-модели через комбобокс + «Применить» — статус-бар сообщает
    «✓ модель ... прогрета»;
  - три цветные точки в статус-баре отражают health (после первого опроса);
  - python main.py (без флага) — старый Tkinter-UI работает как раньше;
  - pytest -q — зелёный.

Запуск:
    python check_stage_dashboard.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

# Принудительно offscreen — не открывать окно при автотестах.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# DevicesPanel запускает PowerShell для BT-батареи — для авточеков отключаем.
os.environ.setdefault("SHURA_DISABLE_BT_POLL", "1")


def step1_imports() -> bool:
    print("\n[1/8] Импорт ui.pyside6.* (app/bridge/dashboard/widgets)")
    print("-" * 70)
    try:
        from ui.pyside6 import app as _app  # noqa: F401
        from ui.pyside6 import bridge as _bridge  # noqa: F401
        from ui.pyside6 import dashboard as _dash  # noqa: F401
        from ui.pyside6.widgets import level_meter as _lm  # noqa: F401
        from ui.pyside6.widgets import status_indicator as _si  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: {exc!r}")
        return False
    print("  OK")
    return True


def step2_bridge_methods() -> bool:
    print("\n[2/8] PipelineBridge имеет ожидаемые слоты")
    print("-" * 70)
    from ui.pyside6.bridge import PipelineBridge

    expected = (
        "start_pipeline",
        "request_turn",
        "request_recalibrate",
        "request_list_models",
        "request_set_model",
        "request_cancel",
        "request_toggle_standby",
        "shutdown",
    )
    missing = [n for n in expected if not callable(getattr(PipelineBridge, n, None))]
    if missing:
        print(f"  FAIL: отсутствуют методы {missing}")
        return False
    print("  OK")
    return True


def step3_bridge_signals() -> bool:
    print("\n[3/8] PipelineBridge имеет ожидаемые сигналы")
    print("-" * 70)
    from ui.pyside6.bridge import PipelineBridge

    expected = (
        "state_changed",
        "turn_result",
        "health_update",
        "level_update",
        "models_list",
        "model_applied",
        "model_error",
        "ipc_changed",
        "ready",
        "fatal",
    )
    missing = [n for n in expected if not hasattr(PipelineBridge, n)]
    if missing:
        print(f"  FAIL: отсутствуют сигналы {missing}")
        return False
    print("  OK")
    return True


def _make_app_and_bridge():
    from PySide6.QtWidgets import QApplication

    from ui.pyside6.bridge import PipelineBridge

    app = QApplication.instance() or QApplication([])
    # Бридж не запускаем (start_pipeline не вызываем) — worker не будет грузить
    # Whisper. Останавливаем worker сразу, чтобы он не висел.
    bridge = PipelineBridge(with_ipc=False)
    return app, bridge


def step4_dashboard_builds() -> bool:
    print("\n[4/8] DashboardWindow собирается, размер 960x640, action-кнопки disabled")
    print("-" * 70)
    try:
        from ui.pyside6.dashboard import DashboardWindow
        app, bridge = _make_app_and_bridge()
        win = DashboardWindow(bridge=bridge)
        size = win.size()
        if (size.width(), size.height()) != (960, 640):
            print(f"  FAIL: размер {size.width()}x{size.height()}, ожидалось 960x640")
            return False
        if not hasattr(win, "_devices_panel"):
            print("  FAIL: DashboardWindow не содержит DevicesPanel")
            return False
        if any(
            btn.isEnabled()
            for btn in (win.btn_listen, win.btn_stop, win.btn_standby, win.btn_recal)
        ):
            print("  FAIL: action-кнопки активны до ready()")
            return False
        win.close()
        bridge.shutdown()
        _ = app
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: {exc!r}")
        return False
    print("  OK")
    return True


def step5_ready_unlocks_buttons() -> bool:
    print("\n[5/8] bridge.ready() разблокирует action-кнопки")
    print("-" * 70)
    try:
        from ui.pyside6.dashboard import DashboardWindow
        app, bridge = _make_app_and_bridge()
        win = DashboardWindow(bridge=bridge)
        bridge.ready.emit()
        # Qt-событие ready ставится в очередь; обработать её.
        app.processEvents()
        ok = all(
            btn.isEnabled()
            for btn in (win.btn_listen, win.btn_stop, win.btn_standby, win.btn_recal)
        )
        win.close()
        bridge.shutdown()
        if not ok:
            print("  FAIL: кнопки остались заблокированы после ready")
            return False
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: {exc!r}")
        return False
    print("  OK")
    return True


def step6_level_update() -> bool:
    print("\n[6/8] level_update(rms, percent) докатывается до LevelMeter")
    print("-" * 70)
    try:
        from ui.pyside6.dashboard import DashboardWindow
        app, bridge = _make_app_and_bridge()
        win = DashboardWindow(bridge=bridge)
        bridge.level_update.emit(1234.0, 42)
        app.processEvents()
        meter = win._level
        ok = meter.percent == 42 and abs(meter.rms - 1234.0) < 0.01
        win.close()
        bridge.shutdown()
        if not ok:
            print(f"  FAIL: percent={meter.percent}, rms={meter.rms}")
            return False
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: {exc!r}")
        return False
    print("  OK")
    return True


def step7_turn_result() -> bool:
    print("\n[7/8] turn_result заполняет блок «Последний оборот»")
    print("-" * 70)
    try:
        from dataclasses import dataclass

        from ui.pyside6.dashboard import DashboardWindow

        @dataclass
        class _T:
            user_text: str = "сколько времени"
            llm_text: str = "пятнадцать тридцать"
            stt_ms: float = 312.0
            llm_ms: float = 815.0
            tts_ms: float = 410.0
            total_s: float = 1.6
            error: object = None
            wav_in: object = None
            wav_out: object = None
            llm_prompt_tokens: object = None
            llm_completion_tokens: object = None

        app, bridge = _make_app_and_bridge()
        win = DashboardWindow(bridge=bridge)
        bridge.turn_result.emit(_T())
        app.processEvents()
        ok = (
            "сколько времени" in win._user_label.text()
            and "пятнадцать тридцать" in win._llm_label.text()
            and "312" in win._timing_label.text()
        )
        win.close()
        bridge.shutdown()
        if not ok:
            print("  FAIL: тексты не подхватились")
            print("  user:", win._user_label.text())
            print("  llm :", win._llm_label.text())
            print("  time:", win._timing_label.text())
            return False
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: {exc!r}")
        return False
    print("  OK")
    return True


def step8_state_change_icon() -> bool:
    print("\n[8/8] state_changed → StatusIndicator меняет иконку")
    print("-" * 70)
    try:
        from ui.pyside6.dashboard import DashboardWindow
        app, bridge = _make_app_and_bridge()
        win = DashboardWindow(bridge=bridge)
        bridge.state_changed.emit("listening", None)
        app.processEvents()
        icon_text = win._status._icon.text()
        ok = icon_text == "🔴"
        win.close()
        bridge.shutdown()
        if not ok:
            print(f"  FAIL: icon={icon_text!r}, ожидалось 🔴")
            return False
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: {exc!r}")
        return False
    print("  OK")
    return True


def main() -> int:
    print("=" * 70)
    print("Этап 4 — функциональный PySide6 Dashboard")
    print("=" * 70)

    results = [
        ("Импорты ui.pyside6.*", step1_imports()),
        ("PipelineBridge: методы", step2_bridge_methods()),
        ("PipelineBridge: сигналы", step3_bridge_signals()),
        ("DashboardWindow: 960x640 + DevicesPanel + disabled", step4_dashboard_builds()),
        ("ready() разблокирует кнопки", step5_ready_unlocks_buttons()),
        ("level_update → LevelMeter", step6_level_update()),
        ("turn_result → панель оборота", step7_turn_result()),
        ("state_changed → иконка", step8_state_change_icon()),
    ]

    print("\nИтог проверок:")
    for name, passed in results:
        print(f"  [{'OK' if passed else 'FAIL'}] {name}")

    if not all(p for _, p in results):
        print("\nНекоторые проверки не прошли. Этап не принят.")
        return 1

    print("\nЧек-лист (ручная часть):")
    print("  [ ] python main.py --ui pyside6 — окно 960x640 открылось,")
    print("      статус прошёл starting → calibrating → idle, кнопки активны")
    print("  [ ] правая колонка показывает текущий микрофон и выход Windows")
    print("  [ ] парные BT-устройства видны со своим зарядом (если есть)")
    print("  [ ] LevelMeter дрожит когда говоришь")
    print("  [ ] «🎤 Слушать» — полный turn, тайминги STT/LLM/TTS появились")
    print("  [ ] смена LLM-модели + «Применить» — статус «✓ ... прогрета»")
    print("  [ ] три точки health в статус-баре окрашены (после ~5с)")
    print("  [ ] python main.py (без флага) — старый Tkinter-UI работает")
    print("  [ ] pytest -q — зелёный")

    ans = input("\nПринимаем Этап 4? [y/N]: ").strip().lower()
    if ans == "y":
        print("Принято. Удалите check_stage_dashboard.py после коммита.")
        return 0
    print("Не принято.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
