"""Minimal production health/validation telemetry for the live scanner."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScanHealth:
    started_at: datetime
    finished_at: datetime
    candidates: int
    evaluated: int
    alerts_qualified: int
    alerts_sent: int
    candidates_failed: int
    duration_seconds: float

    @property
    def healthy(self) -> bool:
        # Candidate-level failures are degraded data, not a failed scan cycle.
        return self.duration_seconds < 240

    @property
    def degraded(self) -> bool:
        return self.candidates_failed > 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["started_at"] = self.started_at.isoformat()
        payload["finished_at"] = self.finished_at.isoformat()
        payload["healthy"] = self.healthy
        payload["degraded"] = self.degraded
        return payload


def build_scan_health(started_at: datetime, finished_at: datetime, results: list[Any]) -> ScanHealth:
    duration = max(0.0, (finished_at - started_at).total_seconds())
    return ScanHealth(
        started_at=started_at.astimezone(timezone.utc),
        finished_at=finished_at.astimezone(timezone.utc),
        candidates=len(results),
        evaluated=sum(result.pipeline is not None for result in results),
        alerts_qualified=sum(result.should_notify for result in results),
        alerts_sent=sum(result.notified for result in results),
        candidates_failed=sum(result.error is not None for result in results),
        duration_seconds=duration,
    )


def write_health_record(path: str | Path, health: ScanHealth) -> None:
    """Append one machine-readable health record without changing decisions."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(health.to_dict(), sort_keys=True) + "\n")


def validate_health(health: ScanHealth) -> None:
    """Fail only when the scanner cycle itself is unhealthy."""
    if health.duration_seconds >= 240:
        raise RuntimeError("scan exceeded the four-minute production budget")
