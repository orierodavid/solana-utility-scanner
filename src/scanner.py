"""Command-line entry point for one live Solana discovery cycle."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict

from .collector import CollectorConfig, CollectorError, LiveSolanaCollector


logger = logging.getLogger("solana-utility-scanner")


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc


def build_collector() -> LiveSolanaCollector:
    """Build a collector from safe, non-secret environment settings."""
    config = CollectorConfig(
        min_market_cap_usd=_float_env("MIN_MARKET_CAP_USD", 50_000),
        max_market_cap_usd=_float_env("MAX_MARKET_CAP_USD", 150_000),
        min_liquidity_usd=_float_env("MIN_LIQUIDITY_USD", 10_000),
        require_security_data=os.getenv("REQUIRE_SECURITY_DATA", "true").lower() == "true",
    )
    return LiveSolanaCollector(config=config)


def run_once() -> list[dict[str, object]]:
    """Run one read-only live scan and return JSON-safe candidate records."""
    collector = build_collector()
    collected = collector.collect()
    records: list[dict[str, object]] = []
    for item in collected:
        records.append(
            {
                "contract_address": item.token.address,
                "symbol": item.token.symbol,
                "name": item.token.name,
                "market_cap_usd": item.token.market_cap_usd,
                "market_cap_zone": item.token.market_cap_zone.value,
                "liquidity_usd": item.token.liquidity_usd,
                "volume_24h_usd": item.token.volume_24h_usd,
                "price_usd": item.token.price_usd,
                "holders": item.token.holders,
                "top_holder_concentration_pct": item.token.top_holder_concentration_pct,
                "mint_authority_active": item.token.mint_authority_active,
                "freeze_authority_active": item.token.freeze_authority_active,
                "risk_score": item.security.risk_score if item.security else None,
                "risk_level": item.security.risk_level if item.security else None,
                "profile": dict(item.profile),
            }
        )
    return records


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    try:
        records = run_once()
    except (CollectorError, ValueError) as exc:
        logger.error("Live scan failed: %s", exc)
        return 1

    print(json.dumps(records, indent=2, sort_keys=True))
    logger.info("Live scan complete: %d market candidates", len(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
