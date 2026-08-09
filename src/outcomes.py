"""Historical recording for scanner decisions, timing, and alert deduplication."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from typing import Any, Mapping, Protocol

from .models import Decision, ScoreBreakdown, TokenMarketData


@dataclass(frozen=True)
class AlertOutcomeRecord:
    """Immutable snapshot of a decision at alert/observation time."""

    event_id: str
    observed_at: datetime
    contract_address: str
    symbol: str
    name: str
    decision: Decision
    score: float
    score_breakdown: dict[str, float]
    confidence: float
    market_cap_usd: float
    liquidity_usd: float
    volume_24h_usd: float
    price_usd: float
    token_age_hours: float | None
    holders: int | None
    holder_growth_24h_pct: float | None
    buy_count_24h: int | None
    sell_count_24h: int | None
    volume_change_24h_pct: float | None
    price_change_24h_pct: float | None
    top_holder_concentration_pct: float | None
    creator_holding_pct: float | None
    wallet_intelligence_score: float | None
    risk_overall: int
    risk_hard_filter_failed: bool
    why_now: str
    invalidation_conditions: list[str] = field(default_factory=list)
    notified: bool = False
    alert_type: str = "BUY"

    @classmethod
    def from_decision(
        cls,
        *,
        event_id: str,
        token: TokenMarketData,
        decision: Decision,
        score: ScoreBreakdown,
        confidence: float,
        risk_overall: int,
        risk_hard_filter_failed: bool,
        why_now: str,
        invalidation_conditions: list[str] | tuple[str, ...] = (),
        wallet_intelligence_score: float | None = None,
        notified: bool = False,
        observed_at: datetime | None = None,
        alert_type: str = "BUY",
    ) -> "AlertOutcomeRecord":
        return cls(
            event_id=event_id,
            observed_at=(observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc),
            contract_address=token.address,
            symbol=token.symbol,
            name=token.name,
            decision=decision,
            score=score.total,
            score_breakdown=score.model_dump(),
            confidence=confidence,
            market_cap_usd=token.market_cap_usd,
            liquidity_usd=token.liquidity_usd,
            volume_24h_usd=token.volume_24h_usd,
            price_usd=token.price_usd,
            token_age_hours=token.token_age_hours,
            holders=token.holders,
            holder_growth_24h_pct=token.holder_growth_24h_pct,
            buy_count_24h=token.buy_count_24h,
            sell_count_24h=token.sell_count_24h,
            volume_change_24h_pct=token.volume_change_24h_pct,
            price_change_24h_pct=token.price_change_24h_pct,
            top_holder_concentration_pct=token.top_holder_concentration_pct,
            creator_holding_pct=token.creator_holding_pct,
            wallet_intelligence_score=wallet_intelligence_score,
            risk_overall=risk_overall,
            risk_hard_filter_failed=risk_hard_filter_failed,
            why_now=why_now,
            invalidation_conditions=list(invalidation_conditions),
            notified=notified,
            alert_type=alert_type,
        )

    def to_json(self) -> str:
        payload = asdict(self)
        payload["observed_at"] = self.observed_at.isoformat()
        payload["decision"] = self.decision.value
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class OutcomeStore(Protocol):
    def append(self, record: AlertOutcomeRecord) -> None:
        ...

    def was_recently_notified(self, contract_address: str, *, since: datetime, alert_type: str = "BUY") -> bool:
        ...

    def latest_snapshot(self, contract_address: str) -> Mapping[str, Any] | None:
        ...


class JsonlOutcomeStore:
    """Append-only JSONL store suitable for the first production deployment."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def append(self, record: AlertOutcomeRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = record.to_json() + "\n"
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()

    def _read_payloads(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        payloads: list[dict[str, Any]] = []
        for line in lines:
            try:
                payload = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
        return payloads

    def was_recently_notified(
        self,
        contract_address: str,
        *,
        since: datetime,
        alert_type: str = "BUY",
    ) -> bool:
        cutoff = since.astimezone(timezone.utc)
        with self._lock:
            payloads = self._read_payloads()
        for payload in reversed(payloads):
            if payload.get("contract_address") != contract_address or payload.get("notified") is not True:
                continue
            if payload.get("alert_type", "BUY") != alert_type:
                continue
            observed = payload.get("observed_at")
            if not isinstance(observed, str):
                continue
            try:
                observed_at = datetime.fromisoformat(observed.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                continue
            return observed_at >= cutoff
        return False

    def latest_snapshot(self, contract_address: str) -> Mapping[str, Any] | None:
        with self._lock:
            payloads = self._read_payloads()
        for payload in reversed(payloads):
            if payload.get("contract_address") == contract_address:
                return payload
        return None


class NullOutcomeStore:
    def append(self, record: AlertOutcomeRecord) -> None:
        return None

    def was_recently_notified(
        self,
        contract_address: str,
        *,
        since: datetime,
        alert_type: str = "BUY",
    ) -> bool:
        return False

    def latest_snapshot(self, contract_address: str) -> Mapping[str, Any] | None:
        return None
