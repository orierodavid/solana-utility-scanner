"""Read-only analytics for TRUTH live decision telemetry."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DecisionTelemetry:
    observations: int
    notified: int
    utility_observations: int
    high_potential_observations: int
    utility_verified: int
    early_buys: int
    buy_candidates: int
    confirmations: int
    waits: int
    no_trades: int
    missed_entries: int

    @property
    def notification_rate(self) -> float:
        return self.notified / self.observations if self.observations else 0.0


def load_records(path: str | Path) -> list[dict[str, Any]]:
    """Load valid JSONL records, ignoring missing/corrupt lines."""
    target = Path(path)
    if not target.exists():
        return []
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def summarize(records: list[dict[str, Any]]) -> DecisionTelemetry:
    decisions = Counter(str(record.get("decision", "")) for record in records)
    lanes = Counter(str(record.get("lane", "UTILITY")).upper() for record in records)
    return DecisionTelemetry(
        observations=len(records),
        notified=sum(record.get("notified") is True for record in records),
        utility_observations=lanes["UTILITY"],
        high_potential_observations=lanes["HIGH_POTENTIAL"],
        utility_verified=sum(record.get("utility_verified") is True for record in records),
        early_buys=decisions["EARLY_BUY"],
        buy_candidates=decisions["BUY_CANDIDATE"],
        confirmations=decisions["CONFIRMATION"],
        waits=decisions["WAIT"],
        no_trades=decisions["NO_TRADE"],
        missed_entries=decisions["MISSED_ENTRY"],
    )


def render_report(records: list[dict[str, Any]]) -> str:
    """Produce a compact operator report without changing scanner decisions."""
    summary = summarize(records)
    return "\n".join(
        (
            "TRUTH LIVE TELEMETRY",
            f"observations={summary.observations}",
            f"notified={summary.notified}",
            f"notification_rate={summary.notification_rate:.2%}",
            f"utility_observations={summary.utility_observations}",
            f"high_potential_observations={summary.high_potential_observations}",
            f"utility_verified={summary.utility_verified}",
            f"early_buys={summary.early_buys}",
            f"buy_candidates={summary.buy_candidates}",
            f"confirmations={summary.confirmations}",
            f"waits={summary.waits}",
            f"no_trades={summary.no_trades}",
            f"missed_entries={summary.missed_entries}",
        )
    )
