from datetime import datetime, timezone

from src.collector import CollectedToken, HolderSnapshot, SecurityData
from src.models import TokenMarketData
from src.wallet_intelligence import InMemoryWalletHistory, WalletIntelligenceEngine


MINT = "So11111111111111111111111111111111111111112"
WALLET_A = "11111111111111111111111111111111"
WALLET_B = "22222222222222222222222222222222"


def candidate(pct_a: float, pct_b: float) -> CollectedToken:
    observed = datetime.now(timezone.utc)
    token = TokenMarketData(
        address=MINT,
        symbol="UTIL",
        name="Utility Token",
        market_cap_usd=75_000,
        liquidity_usd=20_000,
        volume_24h_usd=45_000,
        price_usd=0.001,
        holders=250,
        top_holder_concentration_pct=max(pct_a, pct_b),
        observed_at=observed,
    )
    security = SecurityData(
        holders=250,
        top_holder_concentration_pct=max(pct_a, pct_b),
        mint_authority_active=False,
        freeze_authority_active=False,
        risk_score=10,
        risk_level="Good",
        raw={},
        top_holders=(
            HolderSnapshot(WALLET_A, pct_a),
            HolderSnapshot(WALLET_B, pct_b),
        ),
    )
    return CollectedToken(token=token, security=security, profile={})


def test_first_observation_is_conservative_about_smart_money():
    engine = WalletIntelligenceEngine(InMemoryWalletHistory())
    result = engine.analyze(candidate(8.0, 7.0))

    assert result.wallets_observed == 2
    assert result.distribution_score == 100.0
    assert result.smart_money_score == 0.0
    assert result.matched_historical_wallets == 0
    assert "No repeated-wallet accumulation history" in result.summary


def test_repeated_observations_detect_net_accumulation():
    history = InMemoryWalletHistory()
    engine = WalletIntelligenceEngine(history)

    engine.analyze(candidate(8.0, 7.0))
    result = engine.analyze(candidate(10.0, 6.0))

    assert result.matched_historical_wallets == 2
    assert result.accumulation_score == 70.0
    assert result.smart_money_score > 0
    assert any("net wallet accumulation" in signal for signal in result.signals)


def test_wallet_score_is_capped_to_existing_ten_point_bucket():
    engine = WalletIntelligenceEngine(InMemoryWalletHistory())
    result = engine.analyze(candidate(12.0, 10.0))
    assert 0 <= result.actionable_score <= 10
