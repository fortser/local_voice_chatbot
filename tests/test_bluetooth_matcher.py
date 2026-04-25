"""Тесты эвристики bt_matches_audio — какие BT-устройства считаются
относящимися к текущим Windows audio-дефолтам.

Цель — отфильтровать на UI заряд только для аудио-периферии (наушники,
гарнитуры, колонки), а не всех спаренных гаджетов (клавиатуры, сенсоры).
"""

from __future__ import annotations

from utils.bluetooth_battery import bt_matches_audio


def test_wh1000xm4_matches_when_active_output() -> None:
    audio = ["Headphones (WH-1000XM4 Hands-Free AG)", "Microphone (WH-1000XM4)"]
    assert bt_matches_audio("WH-1000XM4", audio) is True


def test_airpods_pro_matches() -> None:
    audio = ["Headphones (AirPods Pro)"]
    assert bt_matches_audio("AirPods Pro", audio) is True


def test_jbl_speaker_matches() -> None:
    audio = ["JBL Flip 5 Stereo"]
    assert bt_matches_audio("JBL Flip 5", audio) is True


def test_bt_keyboard_does_not_match_typical_audio() -> None:
    audio = [
        "Микрофон (2- EPOS PC 8 USB)",
        "Динамики (Realtek High Definition Audio)",
    ]
    assert bt_matches_audio("BT KeyBoard", audio) is False


def test_xiaomi_sensor_does_not_match() -> None:
    audio = [
        "Микрофон (Realtek)",
        "Динамики (Realtek High Definition Audio)",
    ]
    assert bt_matches_audio("LYWSD03MMC", audio) is False


def test_no_audio_devices_means_no_match() -> None:
    assert bt_matches_audio("WH-1000XM4", []) is False


def test_generic_only_bt_name_returns_false() -> None:
    # «Bluetooth Audio Device» — все токены generic, нечем матчить.
    audio = ["Headphones (Bluetooth Audio Device)"]
    assert bt_matches_audio("Bluetooth Audio Device", audio) is False


def test_realtek_does_not_falsely_match_realtek_audio() -> None:
    # «Realtek» в generic-словаре — не должно ложно матчить.
    audio = ["Динамики (Realtek High Definition Audio)"]
    assert bt_matches_audio("Realtek BT Mouse", audio) is False
