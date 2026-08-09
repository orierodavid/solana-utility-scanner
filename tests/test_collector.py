from datetime import datetime, timezone

from src.collector import (
    CollectorConfig,
    CollectedToken,
    LiveSolanaCollector,
    SecurityData,
    _best_pair,
    _token_from_pair,
)


MINT = "So11111111111111111111111111111111111111112"
OTHER = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def pair(market_cap=75_000, liquidity=20_000):
    return {
        "chainId": "solana",
        "dexId": "raydium",
        "pairAddress": "9xQeWvG816bUx9EPfD9xGvKjZr7M6Xv8f6d1kYf2h8wS",
        "baseToken": {"address": MINT, "name": "Utility Token", "symbol": "UTIL"},
        "quoteToken": {"address": OTHER, "name": "USD Coin", "symbol": "USDC"},
        "priceUsd": "0.00075",
        "marketCap": market_cap,
        "liquidity": {"usd": liquidity},
        "volume": {"h24": 45_000},
        "txns": {"h24": {"buys": 120, "sells": 80}},
        "priceChange": {"h24": 18.5},
        "pairCreatedAt": 1_751_300_000_000,
    }


def security():
    return SecurityData(
        holders=250,
        top_holder_concentration_pct=18.0,
        mint_authority_active=False,
        freeze_authority_active=False,
        risk_score=12.0,
        risk_level="Good",
        raw={},
    )


def test_best_pair_selects_highest_liquidity():
    low = pair(liquidity=12_000)
    high = pair(liquidity=35_000)
    assert _best_pair([low, high], MINT) == high


def test_pair_is_mapped_to_token_market_data():
    observed = datetime(2026, 8, 7, tzinfo=timezone.utc)
    token = _token_from_pair(pair(), MINT, observed)
    assert token.address == MINT
    assert token.market_cap_usd == 75_000
    assert token.liquidity_usd == 20_000
    assert token.volume_24h_usd == 45_000
    assert token.buy_count_24h == 120
    assert token.sell_count_24h == 80
    assert token.price_change_24h_pct == 18.5
    assert token.volume_change_24h_pct is None
    assert token.market_cap_zone.value == "EARLY_BUY"


class FakeDex:
    def latest_solana_profiles(self):
        return [
            {"chainId": "solana", "tokenAddress": MINT, "description": "utility"},
            {"chainId": "ethereum", "tokenAddress": "0xabc"},
        ]

    def token_pairs(self, mint_addresses):
        assert mint_addresses == [MINT]
        return [pair()]


class FakeRugCheck:
    def token_report(self, mint_address):
        assert mint_address == MINT
        return security()


def test_live_collector_filters_and_enriches():
    collector = LiveSolanaCollector(
        config=CollectorConfig(min_market_cap_usd=50_000, max_market_cap_usd=150_000),
        dex=FakeDex(),
        rugcheck=FakeRugCheck(),
    )
    results = collector.collect()
    assert len(results) == 1
    assert isinstance(results[0], CollectedToken)
    assert results[0].token.address == MINT
    assert results[0].token.holders == 250
    assert results[0].token.top_holder_concentration_pct == 18.0
    assert results[0].token.mint_authority_active is False
    assert results[0].token.freeze_authority_active is False


def test_live_collector_excludes_market_caps_outside_range():
    class DexOutside(FakeDex):
        def token_pairs(self, mint_addresses):
            return [pair(market_cap=151_000)]

    collector = LiveSolanaCollector(
        config=CollectorConfig(min_market_cap_usd=50_000, max_market_cap_usd=150_000),
        dex=DexOutside(),
        rugcheck=FakeRugCheck(),
    )
    assert collector.collect() == []
