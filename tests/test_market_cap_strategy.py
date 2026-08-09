from datetime import datetime, timezone

from src.decision import DecisionEngine
from src.models import Decision, RiskAssessment, ScoreBreakdown, TokenMarketData, UtilityEvidence
from src.validator import ValidationResult


def token(mc: float) -> TokenMarketData:
    return TokenMarketData(
        address="Hn6Kdxs6cJrXDLvArAief8ueTgdZLkRacLPPUZo2pump",
        symbol="GLC",
        name="Goldcoin",
        market_cap_usd=mc,
        liquidity_usd=20_000,
        volume_24h_usd=500_000,
        volume_1h_usd=80_000,
        price_usd=0.001,
        buy_count_24h=600,
        sell_count_24h=400,
        buy_count_1h=90,
        sell_count_1h=50,
        price_change_1h_pct=18,
        price_change_5m_pct=3,
        token_age_hours=4,
        observed_at=datetime.now(timezone.utc),
    )


def utility() -> UtilityEvidence:
    return UtilityEvidence(
        has_real_use_case=True,
        product_exists=True,
        token_is_used_by_product=True,
        active_development=True,
        evidence_urls=["https://example.com"],
    )


def risk() -> RiskAssessment:
    return RiskAssessment(
        rug_pull_risk=10,
        holder_concentration_risk=10,
        contract_risk=10,
        liquidity_risk=10,
        creator_wallet_risk=10,
    )


def score(total: float) -> ScoreBreakdown:
    remaining_risk = max(0.0, min(10.0, total - 85.0))
    return ScoreBreakdown(
        utility=20,
        market_structure=15,
        momentum=15,
        development=15,
        catalysts=10,
        community=10,
        risk=remaining_risk,
    )


def validation() -> ValidationResult:
    return ValidationResult(passed=True, reasons=())


def test_market_cap_zones_target_early_pump_window() -> None:
    assert token(40_000).market_cap_zone.value == "EARLY_BUY"
    assert token(75_000).market_cap_zone.value == "EARLY_BUY"
    assert token(75_001).market_cap_zone.value == "CONFIRMATION"
    assert token(120_000).market_cap_zone.value == "CONFIRMATION"
    assert token(120_001).market_cap_zone.value == "LATE_CONFIRMATION"
    assert token(150_000).market_cap_zone.value == "LATE_CONFIRMATION"
    assert token(150_001).market_cap_zone.value == "OUTSIDE"


def test_early_buy_is_actionable_before_full_buy_candidate() -> None:
    result = DecisionEngine(early_buy_score=70, early_buy_confidence=70).decide(
        token(60_000), utility(), risk(), score(74), 72, validation()
    )
    assert result.decision is Decision.EARLY_BUY
    assert result.actionable is True
    assert DecisionEngine.is_alertable(result) is True


def test_late_token_is_missed_entry_not_buy_candidate() -> None:
    result = DecisionEngine().decide(
        token(130_000), utility(), risk(), score(95), 95, validation()
    )
    assert result.decision is Decision.MISSED_ENTRY
    assert result.actionable is False
    assert DecisionEngine.is_alertable(result) is False
