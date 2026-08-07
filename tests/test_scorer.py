from src.models import RiskAssessment, TokenMarketData, UtilityEvidence
from src.scorer import OpportunityScorer, ScoringInputs


MINT = "So11111111111111111111111111111111111111112"


def make_token(**overrides):
    data = {
        "address": MINT,
        "symbol": "UTL",
        "name": "Utility Token",
        "market_cap_usd": 75_000,
        "liquidity_usd": 40_000,
        "volume_24h_usd": 300_000,
        "price_usd": 0.01,
        "holders": 500,
        "holder_growth_24h_pct": 30,
    }
    data.update(overrides)
    return TokenMarketData(**data)


def make_utility():
    return UtilityEvidence(
        has_real_use_case=True,
        product_exists=True,
        token_is_used_by_product=True,
        active_development=True,
    )


def make_risk():
    return RiskAssessment(
        rug_pull_risk=5,
        holder_concentration_risk=5,
        contract_risk=5,
        liquidity_risk=5,
        creator_wallet_risk=5,
    )


def test_score_stays_within_100_point_bounds():
    score = OpportunityScorer().score(
        make_token(),
        make_utility(),
        make_risk(),
        ScoringInputs(
            utility_quality=1,
            development_quality=1,
            catalyst_strength=1,
            community_quality=1,
            buy_pressure_pct=70,
            smart_money_score=1,
            price_momentum_score=1,
        ),
    )
    assert 0 <= score.total <= 100
    assert score.utility == 20
    assert score.development == 15
    assert score.catalysts == 10
    assert score.community == 10


def test_primary_market_cap_zone_gets_higher_structure_score():
    scorer = OpportunityScorer()
    primary = scorer.score(make_token(), make_utility(), make_risk())
    outside = scorer.score(
        make_token(market_cap_usd=200_000), make_utility(), make_risk()
    )
    assert outside.market_structure < primary.market_structure


def test_missing_momentum_data_does_not_create_fake_momentum():
    score = OpportunityScorer().score(
        make_token(volume_24h_usd=0, holder_growth_24h_pct=None),
        make_utility(),
        make_risk(),
    )
    assert score.momentum == 0
