from src.models import RiskAssessment, TokenMarketData, UtilityEvidence
from src.scoring import BUY_THRESHOLD, ScoringEngine


MINT = "So11111111111111111111111111111111111111112"


def token(**overrides):
    data = {
        "address": MINT,
        "symbol": "UTIL",
        "name": "Utility Token",
        "chain": "solana",
        "market_cap_usd": 75_000,
        "liquidity_usd": 25_000,
        "volume_24h_usd": 75_000,
        "price_usd": 0.001,
        "holders": 1_000,
        "holder_growth_24h_pct": 20,
        "buy_count_24h": 700,
        "sell_count_24h": 300,
        "volume_change_24h_pct": 50,
        "price_change_24h_pct": 30,
        "token_age_hours": 48,
        "top_holder_concentration_pct": 20,
    }
    data.update(overrides)
    return TokenMarketData(**data)


def utility(**overrides):
    data = {
        "has_real_use_case": True,
        "product_exists": True,
        "token_is_used_by_product": True,
        "active_development": True,
        "evidence_urls": ["https://example.com/product"],
    }
    data.update(overrides)
    return UtilityEvidence(**data)


def risk(**overrides):
    data = {
        "rug_pull_risk": 0,
        "holder_concentration_risk": 0,
        "contract_risk": 0,
        "liquidity_risk": 0,
        "creator_wallet_risk": 0,
    }
    data.update(overrides)
    return RiskAssessment(**data)


def test_strong_candidate_scores_85_or_higher_and_is_buy_candidate():
    result = ScoringEngine().score(token(), utility(), risk(), catalyst_score=10)

    assert result.breakdown.total == 100
    assert result.breakdown.utility == 20
    assert result.breakdown.market_structure == 15
    assert result.breakdown.momentum == 20
    assert result.breakdown.development == 15
    assert result.breakdown.catalysts == 10
    assert result.breakdown.community == 10
    assert result.breakdown.risk == 10
    assert result.confidence == 100
    assert result.breakdown.total >= BUY_THRESHOLD
    assert result.decision.value == "BUY_CANDIDATE"


def test_market_cap_is_not_enough_for_buy_decision():
    result = ScoringEngine().score(
        token(price_change_24h_pct=0, buy_count_24h=50, sell_count_24h=50, holders=None,
              holder_growth_24h_pct=None, top_holder_concentration_pct=None),
        utility(has_real_use_case=False, product_exists=False, token_is_used_by_product=False,
                active_development=False),
        risk(rug_pull_risk=60, holder_concentration_risk=60, contract_risk=60,
             liquidity_risk=60, creator_wallet_risk=60),
    )

    assert result.decision.value == "NO_TRADE"
    assert result.breakdown.total < BUY_THRESHOLD


def test_outside_market_cap_cannot_be_buy_candidate_even_with_strong_signals():
    result = ScoringEngine().score(token(market_cap_usd=151_000), utility(), risk(), catalyst_score=10)

    assert result.decision.value == "NO_TRADE"
    assert result.breakdown.market_structure == 0


def test_unknown_evidence_does_not_receive_points():
    result = ScoringEngine().score(
        token(holders=None, holder_growth_24h_pct=None, top_holder_concentration_pct=None,
              volume_change_24h_pct=None, price_change_24h_pct=None),
        utility(),
        risk(),
    )

    assert result.breakdown.momentum == 6
    assert result.breakdown.community == 0
    assert result.confidence < 100


def test_catalyst_score_is_bounded():
    try:
        ScoringEngine().score(token(), utility(), risk(), catalyst_score=10.1)
    except ValueError as exc:
        assert "catalyst_score" in str(exc)
    else:
        raise AssertionError("Expected catalyst_score validation error")
