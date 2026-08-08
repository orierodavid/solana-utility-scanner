"""Tests for the scanner runtime."""

from dataclasses import dataclass, field

import pytest

from src.runner import run_forever, run_once


@dataclass
class FakeResult:
    """Minimal result shape required by runtime + production health telemetry."""

    should_notify: bool
    pipeline: object | None = field(default_factory=object)
    notified: bool = False
    error: str | None = None


class FakeRunner:
    def __init__(self, cycles: int = 2):
        self.cycles = cycles
        self.calls = 0

    def run_once(self):
        self.calls += 1
        if self.calls >= self.cycles:
            raise StopIteration
        return [FakeResult(True), FakeResult(False)]


def test_single_cycle_runtime_executes_once():
    runner = FakeRunner(cycles=99)

    results = run_once(runner)

    assert runner.calls == 1
    assert len(results) == 2
    assert sum(result.should_notify for result in results) == 1


def test_runtime_repeats_cycles_and_waits_between_them():
    runner = FakeRunner(cycles=2)
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 2:
            raise StopIteration

    with pytest.raises(StopIteration):
        run_forever(runner, interval_seconds=10, sleep=fake_sleep)

    assert runner.calls == 2
    assert len(sleeps) == 2
    assert all(seconds >= 0 for seconds in sleeps)


def test_runtime_rejects_non_positive_interval():
    runner = FakeRunner()
    with pytest.raises(ValueError, match="greater than zero"):
        run_forever(runner, interval_seconds=0, sleep=lambda _: None)


def test_runtime_continues_after_cycle_failure():
    class FailingRunner:
        def __init__(self):
            self.calls = 0

        def run_once(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary provider failure")
            raise StopIteration

    runner = FailingRunner()
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 2:
            raise StopIteration

    with pytest.raises(StopIteration):
        run_forever(runner, interval_seconds=10, sleep=fake_sleep)

    assert runner.calls == 2
