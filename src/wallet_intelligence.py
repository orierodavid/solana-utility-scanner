"""Conservative wallet-intelligence analysis for live Solana candidates.

This module does not pretend that a holder is "smart money" merely because
it owns a large balance. It uses source-backed holder snapshots and, when
available, repeated observations of the same wallet to identify accumulation
and concentration signals. No trade execution occurs here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Protocol, Sequence

from .collector import CollectedToken


@dataclass(frozen=True)
class WalletObservation:
    address: str
    ownership_pct: float
    observed_at: datetime
    source: str = "rugcheck"


@dataclass(frozen=True)
class WalletSnapshot:
    observed_at: datetime
    wallets: tuple[WalletObservation, ...]


@dataclass(frozen=True)
class WalletIntelligenceResult:
    """Measured wallet signals; not a claim of wallet profitability."""

    wallets_observed: int
    matched_historical_wallets: int
    distribution_score: float
    accumulation_score: float
    smart_money_score: float
    confidence: float
    signals: tuple[str, ...]
    risks: tuple[str, ...]

    @property
    def actionable_score(self) -> float:
        """0-10 contribution suitable for the existing community bucket."""
        return round(self.distribution_score * 0.04 + self.smart_money_score * 0.06, 2)

    @property
    def summary(self) -> str:
        if self.smart_money_score > 0:
            return (
                f"Wallet intelligence: {self.smart_money_score:.0f}/100 smart-money proxy "
                f"with {self.matched_historical_wallets} wallets observed repeatedly."
            )
        return (
            f"Wallet structure: {self.distribution_score:.0f}/100 distribution quality; "
            "no repeated-wallet accumulation history yet."
        )


class WalletHistoryStore(Protocol):
    def load(self, mint: str) -> tuple[WalletSnapshot, ...]:
        ...

    def append(self, mint: str, snapshot: WalletSnapshot) -> None:
        ...


class InMemoryWalletHistory:
    """Deterministic store used by tests and short-lived processes."""

    def __init__(self) -> None:
        self._data: dict[str, list[WalletSnapshot]] = {}

    def load(self, mint: str) -> tuple[WalletSnapshot, ...]:
        return tuple(self._data.get(mint, ()))

    def append(self, mint: str, snapshot: WalletSnapshot) -> None:
        self._data.setdefault(mint, []).append(snapshot)


class JsonlWalletHistory:
    """Small append-only history store for the live scanner."""

    def __init__(self, path: str | Path = "data/wallet_history.jsonl") -> None:
        self.path = Path(path)

    def load(self, mint: str) -> tuple[WalletSnapshot, ...]:
        if not self.path.exists():
            return ()
        snapshots: list[WalletSnapshot] = []
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    if payload.get("mint") != mint:
                        continue
                    observed_at = datetime.fromisoformat(payload["observed_at"])
                    wallets = tuple(
                        WalletObservation(
                            address=str(item["address"]),
                            ownership_pct=float(item["ownership_pct"]),
                            observed_at=observed_at,
                            source=str(item.get("source", "rugcheck")),
                        )
                        for item in payload.get("wallets", [])
                    )
                    snapshots.append(WalletSnapshot(observed_at=observed_at, wallets=wallets))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return ()
        return tuple(snapshots[-20:])

    def append(self, mint: str, snapshot: WalletSnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "mint": mint,
            "observed_at": snapshot.observed_at.isoformat(),
            "wallets": [
                {"address": wallet.address, "ownership_pct": wallet.ownership_pct, "source": wallet.source}
                for wallet in snapshot.wallets
            ],
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def _distribution_score(wallets: Sequence[WalletObservation]) -> float:
    if not wallets:
        return 0.0
    top = max(wallet.ownership_pct for wallet in wallets)
    # Lower concentration is healthier. This is a structure score, not a
    # profitability score and intentionally gives no bonus for a giant whale.
    if top <= 10:
        return 100.0
    if top <= 15:
        return 90.0
    if top <= 20:
        return 80.0
    if top <= 25:
        return 65.0
    if top <= 35:
        return 40.0
    return 10.0


def _accumulation_score(current: Sequence[WalletObservation], history: Sequence[WalletSnapshot]) -> tuple[float, int]:
    if not history:
        return 0.0, 0
    previous: dict[str, float] = {}
    for snapshot in history:
        for wallet in snapshot.wallets:
            previous[wallet.address] = wallet.ownership_pct

    deltas = [wallet.ownership_pct - previous[wallet.address] for wallet in current if wallet.address in previous]
    if not deltas:
        return 0.0, 0
    positive = sum(max(delta, 0.0) for delta in deltas)
    negative = sum(max(-delta, 0.0) for delta in deltas)
    net = positive - negative
    # One percentage point of net ownership movement is meaningful but not
    # enough to dominate the whole score. Cap aggressively against outliers.
    score = max(0.0, min(100.0, 50.0 + net * 10.0))
    return round(score, 2), len(deltas)


class WalletIntelligenceEngine:
    """Analyse holder structure and repeated-wallet accumulation evidence."""

    def __init__(self, history: WalletHistoryStore | None = None) -> None:
        self.history = history or JsonlWalletHistory()

    def analyze(self, candidate: CollectedToken) -> WalletIntelligenceResult:
        security = candidate.security
        now = candidate.token.observed_at.astimezone(timezone.utc)
        raw_holders = getattr(security, "top_holders", ()) if security is not None else ()
        wallets = tuple(
            WalletObservation(
                address=str(item.address),
                ownership_pct=float(item.ownership_pct),
                observed_at=now,
                source=item.source,
            )
            for item in raw_holders
            if item.address and item.ownership_pct >= 0
        )

        history = self.history.load(candidate.token.address)
        accumulation, matched = _accumulation_score(wallets, history)
        distribution = _distribution_score(wallets)
        has_history = matched > 0
        smart_money = round(distribution * 0.35 + accumulation * 0.65, 2) if has_history else 0.0

        signals: list[str] = []
        risks: list[str] = []
        if wallets:
            signals.append(f"Observed {len(wallets)} source-backed top-holder wallets.")
        if distribution >= 80:
            signals.append("Holder distribution is relatively healthy.")
        elif distribution < 40:
            risks.append("Holder concentration is materially elevated.")
        if has_history and accumulation > 60:
            signals.append("Repeated observations show net wallet accumulation.")
        elif has_history and accumulation < 40:
            risks.append("Repeated observations show net wallet distribution.")
        else:
            risks.append("No repeated-wallet accumulation history is available yet.")

        confidence = 0.0
        if wallets:
            confidence += 45.0
        if candidate.token.holders is not None:
            confidence += 20.0
        if candidate.token.top_holder_concentration_pct is not None:
            confidence += 20.0
        if has_history:
            confidence += 15.0

        result = WalletIntelligenceResult(
            wallets_observed=len(wallets),
            matched_historical_wallets=matched,
            distribution_score=distribution,
            accumulation_score=accumulation,
            smart_money_score=smart_money,
            confidence=round(min(confidence, 100.0), 2),
            signals=tuple(dict.fromkeys(signals)),
            risks=tuple(dict.fromkeys(risks)),
        )
        self.history.append(candidate.token.address, WalletSnapshot(observed_at=now, wallets=wallets))
        return result
