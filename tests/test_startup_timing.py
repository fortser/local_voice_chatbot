"""Startup journal contracts without Qt, audio or models."""

import json

import pytest

from utils.startup_timing import StartupTimings


def entries(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_initial_estimate_does_not_create_log(tmp_path):
    timing = StartupTimings(tmp_path / "logs" / "startup.jsonl")
    assert timing.estimate_seconds() == 25
    assert not timing.path.exists()


def test_estimate_survives_restart_and_uses_last_five_successes(tmp_path):
    timing = StartupTimings(tmp_path / "startup.jsonl")
    for seconds in (10, 20, 30, 40, 50, 60):
        timing.record(seconds, "ready")
    timing.record(500, "error")
    timing.record(1, "cancelled")
    restarted = StartupTimings(timing.path)
    assert restarted.recent_durations() == [20, 30, 40, 50, 60]
    assert restarted.estimate_seconds() == 40
    rows = entries(timing.path)
    assert len(rows) == 8
    assert rows[-1]["average_s"] == 40
    assert rows[-1]["sample_count"] == 5
    assert rows[0]["completed_at"]


def test_partial_and_invalid_records_do_not_break_estimate(tmp_path):
    timing = StartupTimings(tmp_path / "startup.jsonl")
    timing.path.write_text('\n'.join([
        '{"status":"ready","duration_s":20}',
        'broken', 'null', '[]',
        '{"status":"ready","duration_s":true}',
        '{"status":"ready","duration_s":-2}',
        '{"status":"ready","duration_s":0}',
        '{"status":"ready","duration_s":"12"}',
        '{"status":"ready","duration_s":NaN}',
        '{"status":"ready","duration_s":Infinity}',
        '{"status":"error","duration_s":100}',
        '{"status":"ready","duration_s":',
    ]), encoding="utf-8")
    assert timing.estimate_seconds() == 20
    timing.record(30, "ready")
    assert StartupTimings(timing.path).estimate_seconds() == 25


def test_unwritable_journal_does_not_block_startup(tmp_path, caplog):
    parent = tmp_path / "not-a-directory"
    parent.write_text("file", encoding="utf-8")
    timing = StartupTimings(parent / "startup.jsonl")
    timing.record(25, "ready")
    assert timing.estimate_seconds() == 25
    assert "Could not write startup journal" in caplog.text


@pytest.mark.parametrize("duration", [0, -1, float("inf"), float("nan")])
def test_invalid_duration_rejected(tmp_path, duration):
    timing = StartupTimings(tmp_path / "startup.jsonl")
    with pytest.raises(ValueError):
        timing.record(duration, "ready")
    assert not timing.path.exists()
