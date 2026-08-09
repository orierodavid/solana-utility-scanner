from src.models import RiskAssessment, TokenMarketData, UtilityEvidence
from src.timing import EarlySetupDetector


MINT = "So11111111111111111111111111111111111111112"


def token(**overrides):
    data = {
        "address": MINT,
        "symbol": "GLC",
        "name": "Goldcoin",
        "market_cap_usd": 75_000,
        "liquidity_usd": 25_000,
        "volume_24h_usd": 240_000,
        "volume_1h_usd": 30_000,
        "price_usd": 0.001,
        "buy_count_1h": 65,
        "sell_count_1h": 35,
        "price_change_1h_pct": 5,
        "price_change_5m_pct": 1,
        "token_age_hours": 4,
    }
    data.update(overrides)
    return TokenMarketData(**data)


def utility():
    return UtilityEvidence(
        has_real_use_case=True,
        product_exists=True,
        token_is_used_by_product=True,
        active_development=True,
    )


def risk():
    return RiskAssessment(
        rug_pull_risk=0,
        holder_concentration_risk=0,
        contract_risk=0,
        liquidity_risk=0,
        creator_wallet_risk=0,
    )


def test_detects_early_acceleration_before_buy_candidate():
    signal = EarlySetupDetector().evaluate(token(), utility(), risk(), wallet_score=5)

    assert signal.qualified is True
    assert signal.late is False
    assert signal.score >= 70
    assert any("1h volume" in reason for reason in signal.reasons)


def test_rejects_already_extended_short_term_move():
    signal = EarlySetupDetector().evaluate(token(price_change_1h_pct=20), utility(), risk(), wallet_score=5)

    assert signal.qualified is False
    assert signal.late is True


def test_uses_previous_scan_to_detect_acceleration():
    previous = {
        "market_cap_usd": 70_000,
        "volume_24h_usd": 200_000,
        "price_usd": 0.00095,
    }
    signal = EarlySetupDetector().evaluate(token(volume_24h_usd=240_000), utility(), risk(), previous=previous)

    assert signal.qualified is True
    assert any("Market cap accelerated" in reason for reason in signal.reasons) or any("volume accelerated" in reason for reason in signal.reasons)
