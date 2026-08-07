"""Live data collection for the Solana utility-token scanner.

The collector is deliberately read-only: it discovers market candidates from
DEX Screener and enriches them with RugCheck security/holder data. It never
places trades and never invents a mint address.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import requests

from .models import TokenMarketData


DEXSCREENER_BASE_URL = "https://api.dexscreener.com"
RUGCHECK_BASE_URL = "https://api.rugcheck.xyz"
SOLANA_CHAIN = "solana"


class CollectorError(RuntimeError):
    """Raised when a live provider cannot return trustworthy data."""


@dataclass(frozen=True)
class CollectorConfig:
    """Runtime settings for the read-only collector."""

    min_market_cap_usd: float = 50_000.0
    max_market_cap_usd: float = 150_000.0
    min_liquidity_usd: float = 10_000.0
    request_timeout_seconds: float = 15.0
    max_profile_tokens: int = 30
    require_security_data: bool = True

    def __post_init__(self) -> None:
        if self.min_market_cap_usd < 0 or self.max_market_cap_usd < self.min_market_cap_usd:
            raise ValueError("Invalid market-cap range")
        if self.min_liquidity_usd < 0:
            raise ValueError("min_liquidity_usd cannot be negative")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if not 1 <= self.max_profile_tokens <= 30:
            raise ValueError("max_profile_tokens must be between 1 and 30")


@dataclass(frozen=True)
class SecurityData:
    """Security fields collected independently from market data."""

    holders: int | None
    top_holder_concentration_pct: float | None
    mint_authority_active: bool | None
    freeze_authority_active: bool | None
    risk_score: float | None
    risk_level: str | None
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class CollectedToken:
    """A market token plus its independently sourced security data."""

    token: TokenMarketData
    security: SecurityData | None
    profile: Mapping[str, Any]


class DexScreenerClient:
    """Small client for the public DEX Screener API."""

    def __init__(self, session: requests.Session | None = None, timeout: float = 15.0) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

    def latest_solana_profiles(self) -> list[Mapping[str, Any]]:
        payload = self._get_json("/token-profiles/latest/v1")
        if not isinstance(payload, list):
            raise CollectorError("DEX Screener returned an unexpected profile payload")
        return [item for item in payload if isinstance(item, dict) and item.get("chainId") == SOLANA_CHAIN]

    def token_pairs(self, mint_addresses: Sequence[str]) -> list[Mapping[str, Any]]:
        addresses = list(dict.fromkeys(mint_addresses))
        if not addresses:
            return []
        if len(addresses) > 30:
            raise ValueError("DEX Screener accepts at most 30 token addresses per request")
        payload = self._get_json(f"/tokens/v1/{SOLANA_CHAIN}/{','.join(addresses)}")
        if not isinstance(payload, list):
            raise CollectorError("DEX Screener returned an unexpected pair payload")
        return [item for item in payload if isinstance(item, dict) and item.get("chainId") == SOLANA_CHAIN]

    def _get_json(self, path: str) -> Any:
        try:
            response = self.session.get(f"{DEXSCREENER_BASE_URL}{path}", timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise CollectorError(f"DEX Screener request failed: {exc}") from exc


class RugCheckClient:
    """Client for the public RugCheck token report endpoint."""

    def __init__(self, session: requests.Session | None = None, timeout: float = 15.0) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

    def token_report(self, mint_address: str) -> SecurityData:
        try:
            response = self.session.get(
                f"{RUGCHECK_BASE_URL}/v1/tokens/{mint_address}/report",
                headers={"accept": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise CollectorError(f"RugCheck request failed for {mint_address}: {exc}") from exc

        if not isinstance(payload, dict):
            raise CollectorError("RugCheck returned an unexpected report payload")

        top_holders = payload.get("topHolders") or []
        holder_pcts = [float(h["pct"]) for h in top_holders if isinstance(h, dict) and h.get("pct") is not None]
        holders = payload.get("totalHolders") or payload.get("holders")
        if holders is not None:
            try:
                holders = int(holders)
            except (TypeError, ValueError):
                holders = None

        token_section = payload.get("token") if isinstance(payload.get("token"), dict) else {}
        mint_authority = token_section.get("mintAuthority")
        freeze_authority = token_section.get("freezeAuthority")
        risks = payload.get("risks") if isinstance(payload.get("risks"), list) else []
        risk_score = payload.get("score_normalised", payload.get("score"))
        try:
            risk_score = float(risk_score) if risk_score is not None else None
        except (TypeError, ValueError):
            risk_score = None

        return SecurityData(
            holders=holders,
            top_holder_concentration_pct=max(holder_pcts) if holder_pcts else None,
            mint_authority_active=mint_authority is not None,
            freeze_authority_active=freeze_authority is not None,
            risk_score=risk_score,
            risk_level=str(payload.get("riskLevel")) if payload.get("riskLevel") is not None else None,
            raw={"risks": risks, "mint": payload.get("mint"), "report": payload},
        )


def _best_pair(pairs: Sequence[Mapping[str, Any]], mint: str) -> Mapping[str, Any] | None:
    token_pairs = [
        pair
        for pair in pairs
        if pair.get("baseToken", {}).get("address") == mint or pair.get("quoteToken", {}).get("address") == mint
    ]
    if not token_pairs:
        return None

    def liquidity(pair: Mapping[str, Any]) -> float:
        value = pair.get("liquidity", {}).get("usd")
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    return max(token_pairs, key=liquidity)


def _token_from_pair(pair: Mapping[str, Any], mint: str, observed_at: datetime) -> TokenMarketData:
    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}
    token = base if base.get("address") == mint else quote
    symbol = str(token.get("symbol") or "UNKNOWN")
    name = str(token.get("name") or symbol)

    def number(value: Any, default: float = 0.0) -> float:
        try:
            return float(value if value is not None else default)
        except (TypeError, ValueError):
            return default

    txns = pair.get("txns") or {}
    h24 = txns.get("h24") or {}
    volume = pair.get("volume") or {}
    changes = pair.get("priceChange") or {}
    price_usd = number(pair.get("priceUsd"))
    market_cap = number(pair.get("marketCap"))
    liquidity_usd = number((pair.get("liquidity") or {}).get("usd"))
    volume_24h = number(volume.get("h24"))
    buy_count = int(number(h24.get("buys"))) if h24.get("buys") is not None else None
    sell_count = int(number(h24.get("sells"))) if h24.get("sells") is not None else None

    pair_created_at = pair.get("pairCreatedAt")
    token_age_hours = None
    if pair_created_at:
        try:
            created = datetime.fromtimestamp(float(pair_created_at) / 1000, tz=timezone.utc)
            token_age_hours = max(0.0, (observed_at - created).total_seconds() / 3600)
        except (TypeError, ValueError, OverflowError):
            token_age_hours = None

    return TokenMarketData(
        address=mint,
        symbol=symbol,
        name=name,
        chain=SOLANA_CHAIN,
        market_cap_usd=market_cap,
        liquidity_usd=liquidity_usd,
        volume_24h_usd=volume_24h,
        price_usd=price_usd,
        buy_count_24h=buy_count,
        sell_count_24h=sell_count,
        price_change_24h_pct=number(changes.get("h24")) if changes.get("h24") is not None else None,
        token_age_hours=token_age_hours,
        observed_at=observed_at,
    )


class LiveSolanaCollector:
    """Discover and enrich live Solana tokens in the configured MC range."""

    def __init__(
        self,
        config: CollectorConfig | None = None,
        dex: DexScreenerClient | None = None,
        rugcheck: RugCheckClient | None = None,
    ) -> None:
        self.config = config or CollectorConfig()
        self.dex = dex or DexScreenerClient(timeout=self.config.request_timeout_seconds)
        self.rugcheck = rugcheck or RugCheckClient(timeout=self.config.request_timeout_seconds)

    def collect(self) -> list[CollectedToken]:
        raw_profiles = self.dex.latest_solana_profiles()
        # Enforce the Solana-chain invariant at the collector boundary as well.
        # This protects the scanner if an adapter/mock returns mixed-chain data.
        profiles = [
            profile
            for profile in raw_profiles
            if isinstance(profile, Mapping)
            and profile.get("chainId") == SOLANA_CHAIN
            and profile.get("tokenAddress")
        ][: self.config.max_profile_tokens]
        mints = list(dict.fromkeys(str(p["tokenAddress"]) for p in profiles))
        pairs = self.dex.token_pairs(mints)
        observed_at = datetime.now(timezone.utc)
        profile_by_mint = {str(p["tokenAddress"]): p for p in profiles}
        results: list[CollectedToken] = []

        for mint in mints:
            pair = _best_pair(pairs, mint)
            if pair is None:
                continue
            token = _token_from_pair(pair, mint, observed_at)
            if not self.config.min_market_cap_usd <= token.market_cap_usd <= self.config.max_market_cap_usd:
                continue
            if token.liquidity_usd < self.config.min_liquidity_usd:
                continue

            security: SecurityData | None = None
            try:
                security = self.rugcheck.token_report(mint)
            except CollectorError:
                if self.config.require_security_data:
                    continue

            if security is not None:
                token = token.model_copy(
                    update={
                        "holders": security.holders,
                        "top_holder_concentration_pct": security.top_holder_concentration_pct,
                        "mint_authority_active": security.mint_authority_active,
                        "freeze_authority_active": security.freeze_authority_active,
                    }
                )

            results.append(
                CollectedToken(token=token, security=security, profile=profile_by_mint.get(mint, {}))
            )

        return results


def collect_live_tokens(**kwargs: Any) -> list[CollectedToken]:
    """Convenience entry point for one live discovery cycle."""
    return LiveSolanaCollector(**kwargs).collect()
