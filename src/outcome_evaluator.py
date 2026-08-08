"""Measure realized market outcomes for previously recorded scanner decisions."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import requests

from .collector import DexScreenerClient


@dataclass(frozen=True)
class OutcomeMeasurement:
    event_id: str
    contract_address: str
    decision: str
    score: float
    observed_at: datetime
    horizon_hours: int
    baseline_price_usd: float
    current_price_usd: float
    return_pct: float
    measured_at: datetime

    def to_json(self) -> str:
        payload = asdict(self)
        payload["observed_at"] = self.observed_at.isoformat()
        payload["measured_at"] = self.measured_at.isoformat()
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _already_measured(path: Path) -> set[tuple[str, int]]:
    return {
        (str(row.get("event_id")), int(row["horizon_hours"]))
        for row in _load_records(path)
        if row.get("event_id") is not None and row.get("horizon_hours") is not None
    }


def evaluate_outcomes(
    history_path: str | Path,
    measurement_path: str | Path,
    *,
    horizons_hours: tuple[int, ...] = (1, 6, 24),
    now: datetime | None = None,
    client: DexScreenerClient | None = None,
) -> list[OutcomeMeasurement]:
    """Measure eligible historical decisions using current DEX Screener prices.

    A horizon is measured only after enough wall-clock time has elapsed. Each
    event/horizon is written once, so repeated evaluator runs are idempotent.
    """
    history = Path(history_path)
    measurement = Path(measurement_path)
    records = _load_records(history)
    existing = _already_measured(measurement)
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    client = client or DexScreenerClient()

    eligible: list[dict[str, Any]] = []
    for row in records:
        try:
            observed = datetime.fromisoformat(str(row["observed_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)
            baseline = float(row["price_usd"])
            if baseline <= 0:
                continue
            event_id = str(row["event_id"])
            address = str(row["contract_address"])
        except (KeyError, TypeError, ValueError):
            continue
        for horizon in horizons_hours:
            if (event_id, horizon) in existing:
                continue
            if current_time - observed >= timedelta(hours=horizon):
                eligible.append({
                    "event_id": event_id,
                    "address": address,
                    "observed": observed,
                    "baseline": baseline,
                    "decision": str(row.get("decision", "unknown")),
                    "score": float(row.get("score", 0.0)),
                    "horizon": horizon,
                })

    if not eligible:
        return []

    addresses = [item["address"] for item in eligible]
    pairs = client.token_pairs(addresses)
    prices: dict[str, float] = {}
    for pair in pairs:
        address = pair.get("baseToken", {}).get("address") if isinstance(pair.get("baseToken"), dict) else None
        price = pair.get("priceUsd")
        try:
            if address and price is not None:
                value = float(price)
                if value > 0:
                    prices[str(address)] = value
        except (TypeError, ValueError):
            continue

    results: list[OutcomeMeasurement] = []
    measurement.parent.mkdir(parents=True, exist_ok=True)
    with measurement.open("a", encoding="utf-8") as handle:
        for item in eligible:
            current_price = prices.get(item["address"])
            if current_price is None:
                continue
            result = OutcomeMeasurement(
                event_id=item["event_id"],
                contract_address=item["address"],
                decision=item["decision"],
                score=item["score"],
                observed_at=item["observed"],
                horizon_hours=item["horizon"],
                baseline_price_usd=item["baseline"],
                current_price_usd=current_price,
                return_pct=((current_price / item["baseline"]) - 1.0) * 100.0,
                measured_at=current_time,
            )
            handle.write(result.to_json() + "\n")
            results.append(result)

    return results
