from datetime import datetime, timezone

from src.models import Decision, RiskAssessment, TokenMarketData, UtilityEvidence
from src.pipeline import DecisionAlertPipeline


CONTRACT = "So11111111111111111111111111111111111111112"


def strong_token(**overrides) -> TokenMarketData:
    data = {
        "address": CONTRACT,
        "symbol": "UTIL",
        "name": "Utility Token",
        "market_cap_usd": 75_000,
        "liquidity_usd": 30_000,
        "volume_24h_usd": 80_000,
        "price_usd": 0.001,
        "holders": 1_000,
        "holder_growth_24h_pct": 20,
        "buy_count_24h": 700,
        "sell_count_24h": 300,
        "volume_change_24h_pct": 60,
        "price_change_24h_pct": 30,
        "token_age_hours": 24,
        "top_holder_concentration_pct": 15,
        "creator_holding_pct": 5,
        "mint_authority_active": False,
        "freeze_authority_active": False,
        "observed_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return TokenMarketData(**data)


def strong_utility() -> UtilityEvidence:
    return UtilityEvidence(
        has_real_use_case=True,
        product_exists=True,
        token_is_used_by_product=True,
        active_development=True,
        evidence_urls=["https://example.com/product"],
    )


def low_risk() -> RiskAssessment:
    return RiskAssessment(
        rug_pull_risk=0,
        holder_concentration_risk=0,
        contract_risk=0,
        liquidity_risk=0,
        creator_wallet_risk=0,
        hard_filter_failed=False,
    )


def test_early_buy_creates_alert_with_exact_contract():
    result = DecisionAlertPipeline().evaluate(
        strong_token(),
        strong_utility(),
        low_risk(),
        catalyst_score=10,
        why_now="Product launch is driving fresh usage and volume.",
        invalidation_conditions=["Utility usage falls materially"],
    )

    assert result.validation.passed
    assert result.decision.decision is Decision.EARLY_BUY
    assert result.decision.score == 100
    assert result.should_notify
    assert result.alert is not None
    assert result.alert.contract_address == CONTRACT
    assert f"Contract: {CONTRACT}" in result.alert.text
    assert "Decision: EARLY_BUY" in result.alert.text


def test_market_cap_outside_range_cannot_alert_even_with_perfect_score():
    result = DecisionAlertPipeline().evaluate(
        strong_token(market_cap_usd=151_000),
        strong_utility(),
        low_risk(),
        catalyst_score=10,
        why_now="Strong setup.",
    )

    assert not result.validation.passed
    assert result.decision.decision is Decision.NO_TRADE
    assert result.alert is None
    assert result.decision.score == 85


def test_failed_risk_filter_blocks_alert():
    risk = low_risk().model_copy(update={"hard_filter_failed": True, "reasons": ["Creator risk"]})
    result = DecisionAlertPipeline().evaluate(
        strong_token(),
        strong_utility(),
        risk,
        catalyst_score=10,
        why_now="Strong setup.",
    )

    assert result.decision.decision is Decision.NO_TRADE
    assert result.alert is None


def test_unverified_utility_blocks_alert():
    utility = strong_utility().model_copy(update={"token_is_used_by_product": False})
    result = DecisionAlertPipeline().evaluate(
        strong_token(),
        utility,
        low_risk(),
        catalyst_score=10,
        why_now="Strong setup.",
    )

    assert result.decision.decision is Decision.NO_TRADE
    assert result.alert is None


def test_wait_never_reaches_alert_channel():
    # Deliberately weak momentum keeps this setup below the 70-point EARLY_BUY
    # threshold. This test verifies that a genuinely non-actionable setup stays
    # out of the alert channel rather than exercising the early-buy path.
    result = DecisionAlertPipeline().evaluate(
        strong_token(
            price_change_24h_pct=-11,
            volume_change_24h_pct=-21,
            holders=250,
            holder_growth_24h_pct=None,
        ),
        strong_utility(),
        RiskAssessment(
            rug_pull_risk=8,
            holder_concentration_risk=8,
            contract_risk=8,
            liquidity_risk=8,
            creator_wallet_risk=8,
        ),
        catalyst_score=0,
        why_now="Momentum needs confirmation.",
    )

    assert result.decision.decision is Decision.WAIT
    assert result.alert is None
