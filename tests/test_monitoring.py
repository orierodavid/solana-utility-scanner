"""Tests for production scan health validation."""

from datetime import datetime, timedelta, timezone

import pytest

from src.monitoring import build_scan_health, validate_health, write_health_record


class Result:
    def __init__(self, pipeline=True, notify=False, error=None):
        self.pipeline = object() if pipeline else None
        self.notified = notify
        self.error = error

    @property
    def should_notify(self):
        return self.pipeline is not None and self.notified


def test_build_health_reports_success():
    start = datetime.now(timezone.utc)
    end = start + timedelta(seconds=2)
    health = build_scan_health(start, end, [Result(notify=True), Result(notify=False)])

    assert health.healthy is True
    assert health.degraded is False
    assert health.candidates == 2
    assert health.evaluated == 2
    assert health.alerts_qualified == 1
    assert health.alerts_sent == 1
    assert health.candidates_failed == 0
    assert health.duration_seconds == 2


def test_health_records_are_machine_readable(tmp_path):
    start = datetime.now(timezone.utc)
    health = build_scan_health(start, start + timedelta(seconds=1), [Result()])
    path = tmp_path / "health.jsonl"

    write_health_record(path, health)

    assert path.exists()
    assert '"healthy": true' in path.read_text(encoding="utf-8")
    assert '"degraded": false' in path.read_text(encoding="utf-8")


def test_failed_candidate_degrades_but_does_not_fail_whole_scan():
    start = datetime.now(timezone.utc)
    health = build_scan_health(
        start,
        start + timedelta(seconds=1),
        [Result(), Result(error="provider failed")],
    )

    assert health.healthy is True
    assert health.degraded is True
    assert health.candidates_failed == 1
    validate_health(health)


def test_slow_scan_fails_validation():
    start = datetime.now(timezone.utc)
    health = build_scan_health(start, start + timedelta(seconds=240), [Result()])

    assert health.healthy is False
    with pytest.raises(RuntimeError, match="four-minute"):
        validate_health(health)
