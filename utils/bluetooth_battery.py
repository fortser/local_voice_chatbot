"""Чтение заряда Bluetooth-устройств через PowerShell PnP-property.

Использует тот же DEVPKEY ``{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2``,
что и «Параметры → Bluetooth и другие устройства» Windows. Без сторонних
зависимостей: ``Get-PnpDevice`` и ``Get-PnpDeviceProperty`` входят в состав
Windows 10/11 PowerShell.

Не все BT-устройства сообщают заряд (нужна поддержка HFP-Battery /
BLE-Battery в драйвере). Те, что не сообщили — просто не появятся в выдаче.

CLI: ``python -m utils.bluetooth_battery`` — печатает таблицу.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass

# Слова, общие для аудио-устройств и BT-имён, не несущие идентификационной
# нагрузки. Сюда же — host-API'и sounddevice (MME/WASAPI/WDM-KS/DirectSound),
# чтобы они не порождали ложные совпадения.
_GENERIC_TOKENS = frozenset(
    {
        "bluetooth", "bt", "audio", "device", "devices", "stereo", "mono",
        "hands", "free", "handsfree", "headphones", "headset", "speakers",
        "speaker", "microphone", "mic", "input", "output", "primary",
        "default", "ag", "hfp", "a2dp", "le",
        "mme", "wasapi", "wdm", "ks", "ds", "directsound", "sound",
        "analog", "digital", "high", "definition", "realtek", "intel",
        "amd", "nvidia", "usb",
    }
)


def _norm_tokens(name: str) -> set[str]:
    """Разбить имя устройства на «специфичные» токены (нижний регистр, ≥3 символа,
    не входящие в :data:`_GENERIC_TOKENS`).

    Используется для сопоставления BT-имени и имени аудио-устройства Windows.
    """
    if not name:
        return set()
    text = re.sub(r"[^a-z0-9]+", " ", name.lower())
    return {
        tok
        for tok in text.split()
        if len(tok) >= 3 and tok not in _GENERIC_TOKENS
    }


def bt_matches_audio(bt_name: str, audio_names: list[str]) -> bool:
    """True, если ``bt_name`` пересекается специфичными токенами хотя бы с одним
    из ``audio_names`` — то есть BT-устройство присутствует среди текущих
    Windows-дефолтов ввода/вывода.

    Эвристика: общий generic-словарь отрезает «Bluetooth», «Hands-Free»,
    «Stereo», host-API'и и слова производителей, оставляя модельные токены
    (``WH-1000XM4`` → ``1000xm4``, ``AirPods Pro`` → ``airpods``, ``pro``).
    """
    bt_tokens = _norm_tokens(bt_name)
    if not bt_tokens:
        return False
    for audio in audio_names:
        if _norm_tokens(audio) & bt_tokens:
            return True
    return False

logger = logging.getLogger(__name__)

_BATTERY_DEVPKEY = "{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2"

# Сужаем enumeration до BT-веток PnP-дерева по префиксу InstanceId
# (BTHENUM/BTHHFENUM/BTHLE…) вместо обхода всех 300+ устройств. Это режет
# холодную стоимость WMI/PnP property-чтения на порядок: первый вызов
# укладывается в 2–5 с вместо 25–30 с. Class='Bluetooth' использовать нельзя
# — он не включает дочерние HFP/A2DP-узлы, на которых у части гарнитур
# (Borofone/AirPods/Philips) лежит DEVPKEY заряда.
#
# $ProgressPreference='SilentlyContinue' гасит Write-Progress
# Get-PnpDeviceProperty — иначе полоска прогресса PowerShell течёт в host
# приложения и слегка тормозит сам pipeline.
_PS_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$ProgressPreference='SilentlyContinue';"
    "$key='" + _BATTERY_DEVPKEY + "';"
    "$bt = Get-PnpDevice -PresentOnly | "
    "  Where-Object { $_.InstanceId -match '^(BTHENUM|BTHHFENUM|BTHLEDevice|BTHLE)\\\\' };"
    "$names=@{};"
    "$bt | ForEach-Object { $names[$_.InstanceId]=$_.FriendlyName };"
    "$out = $bt | "
    "  Get-PnpDeviceProperty -KeyName $key | "
    "  Where-Object { $_.Type -ne 'Empty' -and $_.Data -ne $null } | "
    "  ForEach-Object { "
    "    [pscustomobject]@{ Name=$names[$_.InstanceId]; Battery=[int]$_.Data; } "
    "  };"
    "$out | ConvertTo-Json -Compress"
)


@dataclass(frozen=True)
class BluetoothBattery:
    name: str
    percent: int


def get_battery_levels(timeout: float = 20.0) -> list[BluetoothBattery]:
    """Вернуть список ``BluetoothBattery`` для BT-устройств с известным зарядом.

    При любой ошибке (PowerShell не нашёлся, таймаут, парс-ошибка) — пустой
    список и WARNING в логи. UI не должен падать из-за этого.
    """
    try:
        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _PS_SCRIPT,
            ],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        logger.warning("PowerShell not available — BT battery disabled")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("BT battery PowerShell call timed out")
        return []
    except Exception:
        logger.exception("BT battery PowerShell call failed")
        return []

    raw = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("BT battery: malformed JSON from PowerShell: %r", raw[:200])
        return []

    # ConvertTo-Json: один объект → dict, несколько → list.
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    out: list[BluetoothBattery] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or "").strip()
        battery = item.get("Battery")
        if not name or battery is None:
            continue
        try:
            pct = int(battery)
        except (TypeError, ValueError):
            continue
        if 0 <= pct <= 100:
            out.append(BluetoothBattery(name=name, percent=pct))
    return out


def _cli() -> int:
    items = get_battery_levels()
    if not items:
        print("Нет BT-устройств с известным зарядом.")
        return 0
    print(f"{'Устройство':<40}  {'Заряд':>6}")
    print("-" * 50)
    for it in items:
        print(f"{it.name[:40]:<40}  {it.percent:>5}%")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
