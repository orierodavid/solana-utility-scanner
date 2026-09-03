"""Integration tests for the deterministic scanner pipeline."""

from src.analyst import Analyst
from src.decision import DecisionEngine
from src.models import RiskAssessment, ScoreBreakdown, TokenAnalysis, TokenMarketData, UtilityEvidence, Decision
from src.notifier import build_alert
from src.alerts import AlertBuilder
from src.validator import TokenValidator


MINT = "So11111111111111111111111111111111111111112"


def make_token() -> TokenMarketData:
    return TokenMarketData(
        address=MINT,
        symbol="TEST",
        name="Test Utility",
        market_cap_usd=75_000,
        liquidity_usd=25_000,
        volume_24h_usd=150_000,
        price_usd=0.001,
        holders=500,
        holder_growth_24h_pct=20,
        volume_change_24h_pct=50,
        top_holder_concentration_pct=20,
        creator_holding_pct=5,
    )


def make_utility() -> UtilityEvidence:
    return UtilityEvidence(
        has_real_use_case=True,
        product_exists=True,
        token_is_used_by_product=True,
        active_development=True,
        evidence_urls=["https://example.com"],
    )


def make_risk() -> RiskAssessment:
    return RiskAssessment(
        rug_pull_risk=5,
        holder_concentration_risk=5,
        contract_risk=5,
        liquidity_risk=5,
        creator_wallet_risk=5,
    )


def make_score() -> ScoreBreakdown:
    return ScoreBreakdown(
        utility=20,
        market_structure=15,
        momentum=20,
        development=15,
        catalysts=10,
        community=10,
        risk=10,
    )


def make_analysis() -> TokenAnalysis:
    return TokenAnalysis(
        token=make_token(),
        utility=make_utility(),
        risk=make_risk(),
        score=make_score(),
        confidence=95,
        why_now="Strong volume and holder growth with verified utility evidence.",
        invalidation_conditions=["Material liquidity loss"],
    )


def test_pipeline_produces_actionable_early_alert_with_exact_mint():
    token = make_token()
    utility = make_utility()
    risk = make_risk()
    score = make_score()

    validation = TokenValidator().validate(token, utility)
    assert validation.passed, validation.reasons

    decision = DecisionEngine().decide(token, utility, risk, score, 95, validation)
    assert decision.decision is Decision.EARLY_BUY
    assert decision.actionable

    request = Analyst().build_request(token, utility, risk, score)
    payload = request.to_prompt_payload()
    assert payload["token"]["contract_address"] == MINT

    analysis = make_analysis()
    alert = build_alert(analysis, decision)
    assert alert is not None
    assert alert.contract_address == MINT
    assert f"Contract / Mint Address: {MINT}" in alert.text


def test_high_potential_lane_can_alert_without_verified_utility():
    token = make_token()
    utility = UtilityEvidence(
        has_real_use_case=False,
        product_exists=False,
        token_is_used_by_product=False,
        active_development=False,
        evidence_urls=[],
        notes="UTILITY_UNDER_INVESTIGATION: first-party evidence unavailable",
    )
    risk = make_risk()
    score = ScoreBreakdown(
        utility=0,
        market_structure=20,
        momentum=20,
        development=10,
        catalysts=10,
        community=10,
        risk=20,
    )
    validation = TokenValidator().validate(token, utility)
    assert validation.passed, validation.reasons

    decision = DecisionEngine().decide(token, utility, risk, score, 90, validation)
    assert decision.lane == "HIGH_POTENTIAL"
    assert decision.decision is Decision.BUY_CANDIDATE

    alert = AlertBuilder().build(
        token,
        utility,
        risk,
        decision,
        why_now="Strong market structure and momentum despite unavailable utility evidence.",
        invalidation_conditions=("Utility evidence contradicts the thesis.",),
    )
    assert alert.contract_address == MINT
    assert "SOLANA HIGH-POTENTIAL ALERT" in alert.text
    assert "Utility not independently verified" in alert.text
    assert MINT in alert.text


def test_unverified_utility_cannot_use_primary_utility_alert_lane():
    token = make_token()
    utility = UtilityEvidence(
        has_real_use_case=False,
        product_exists=False,
        token_is_used_by_product=False,
        active_development=False,
        evidence_urls=[],
    )
    validation = TokenValidator().validate(token, utility)
    decision = DecisionEngine().decide(token, utility, make_risk(), make_score(), 95, validation)
    assert decision.lane == "HIGH_POTENTIAL"
    assert decision.decision is Decision.BUY_CANDIDATE


def test_validator_rejects_outside_market_cap():
    token = make_token().model_copy(update={"market_cap_usd": 200_000})
    result = TokenValidator().validate(token, make_utility())
    assert not result.passed
    assert any("outside" in reason.lower() for reason in result.reasons)


def test_validator_rejects_missing_holder_concentration():
    token = make_token().model_copy(update={"top_holder_concentration_pct": None})
    result = TokenValidator().validate(token, make_utility())
    assert not result.passed


def test_decision_never_buys_after_validation_failure():
    token = make_token().model_copy(update={"liquidity_usd": 1_000})
    utility = make_utility()
    validation = TokenValidator().validate(token, utility)
    decision = DecisionEngine().decide(token, utility, make_risk(), make_score(), 100, validation)
    assert decision.decision is Decision.NO_TRADE


def test_ai_cannot_change_verified_contract_address():
    analyst = Analyst()
    try:
        analyst.validate_response(
            {"contract_address": "11111111111111111111111111111111", "why_now": "x", "confidence": 90},
            MINT,
        )
    except ValueError as exc:
        assert "contract address" in str(exc).lower()
    else:
        raise AssertionError("Mismatched contract address was accepted")


def test_notifier_refuses_non_actionable_decision():
    analysis = make_analysis()
    validation = TokenValidator().validate(analysis.token, analysis.utility)
    decision = DecisionEngine().decide(
        analysis.token, analysis.utility, analysis.risk, analysis.score, 60, validation
    )
    assert decision.decision is Decision.WAIT
    assert build_alert(analysis, decision) is None
