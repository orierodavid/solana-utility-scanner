"""Decision-to-alert orchestration for one scanner candidate."""

from __future__ import annotations

from dataclasses import dataclass

from .alerts import AlertBuilder, AlertPayload
from .decision import DecisionEngine, DecisionResult
from .models import Decision, RiskAssessment, TokenMarketData, UtilityEvidence
from .scoring import ScoringEngine
from .validator import TokenValidator, ValidationResult


@dataclass(frozen=True)
class PipelineResult:
    """Complete output from one candidate through the decision boundary."""

    validation: ValidationResult
    decision: DecisionResult
    alert: AlertPayload | None

    @property
    def should_notify(self) -> bool:
        return self.alert is not None


class DecisionAlertPipeline:
    """Run validation -> scoring -> decision -> alert construction."""

    def __init__(self, validator: TokenValidator | None = None, scoring_engine: ScoringEngine | None = None, decision_engine: DecisionEngine | None = None, alert_builder: AlertBuilder | None = None) -> None:
        self.validator = validator or TokenValidator()
        self.scoring_engine = scoring_engine or ScoringEngine()
        self.decision_engine = decision_engine or DecisionEngine()
        self.alert_builder = alert_builder or AlertBuilder()

    @staticmethod
    def _build_early_buy_alert(token: TokenMarketData, utility: UtilityEvidence, risk: RiskAssessment, decision: DecisionResult, *, why_now: str, invalidation_conditions: list[str] | tuple[str, ...]) -> AlertPayload:
        """Construct the first-class EARLY_BUY payload."""
        if not utility.verified or risk.hard_filter_failed or decision.breakdown is None:
            raise ValueError("Early-buy alert prerequisites failed")
        buys = token.buy_count_24h or 0
        sells = token.sell_count_24h or 0
        total = buys + sells
        buy_pressure = f"{buys / total * 100:.1f}%" if total else "Unavailable"
        risks = risk.reasons or ["No hard risk-filter failures"]
        invalidation = list(invalidation_conditions) or ["Required setup evidence deteriorates or a mandatory risk filter fails"]
        text = "\n".join([
            "SOLANA UTILITY EARLY BUY ALERT", "",
            f"Token: {token.name} (${token.symbol})",
            f"Contract: {token.address}",
            f"Market Cap: ${token.market_cap_usd:,.0f}",
            f"Liquidity: ${token.liquidity_usd:,.0f}",
            f"24h Volume: ${token.volume_24h_usd:,.0f}",
            f"Token Age: {token.token_age_hours:.1f}h" if token.token_age_hours is not None else "Token Age: Unavailable", "",
            f"Opportunity Score: {decision.score:.2f}/100",
            f"Confidence: {decision.confidence:.2f}%",
            f"Buy/Sell Pressure: {buy_pressure}", "",
            "Decision: EARLY_BUY", "",
            f"Why Now: {why_now.strip()}", "",
            "Key Risks:", *[f"- {reason}" for reason in risks], "",
            "Invalidation Conditions:", *[f"- {condition}" for condition in invalidation],
        ])
        return AlertPayload(decision=Decision.EARLY_BUY, contract_address=token.address, text=text)

    def evaluate(self, token: TokenMarketData, utility: UtilityEvidence, risk: RiskAssessment, *, catalyst_score: float = 0.0, confidence: float | None = None, why_now: str, invalidation_conditions: list[str] | tuple[str, ...] = (), wallet_intelligence_score: float | None = None) -> PipelineResult:
        """Evaluate one candidate and optionally create a qualified alert."""
        validation = self.validator.validate(token, utility)
        score_result = self.scoring_engine.score(token, utility, risk, catalyst_score=catalyst_score, wallet_intelligence_score=wallet_intelligence_score)
        effective_confidence = score_result.confidence if confidence is None else confidence
        decision = self.decision_engine.decide(token, utility, risk, score_result.breakdown, effective_confidence, validation)

        alert = None
        if self.decision_engine.is_alertable(decision) and why_now.strip():
            if decision.decision is Decision.EARLY_BUY:
                alert = self._build_early_buy_alert(token, utility, risk, decision, why_now=why_now, invalidation_conditions=invalidation_conditions)
            else:
                alert = self.alert_builder.build(token, utility, risk, decision, why_now=why_now, invalidation_conditions=invalidation_conditions)

        return PipelineResult(validation=validation, decision=decision, alert=alert)
