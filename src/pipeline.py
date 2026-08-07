"""Decision-to-alert orchestration for one scanner candidate.

The pipeline deliberately stops before any notification transport. It produces
an alert payload only when validation, scoring, confidence, utility, and risk
rules all qualify the token.
"""

from __future__ import annotations

from dataclasses import dataclass

from .alerts import AlertBuilder, AlertPayload
from .decision import DecisionEngine, DecisionResult
from .models import RiskAssessment, TokenMarketData, UtilityEvidence
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

    def __init__(
        self,
        validator: TokenValidator | None = None,
        scoring_engine: ScoringEngine | None = None,
        decision_engine: DecisionEngine | None = None,
        alert_builder: AlertBuilder | None = None,
    ) -> None:
        self.validator = validator or TokenValidator()
        self.scoring_engine = scoring_engine or ScoringEngine()
        self.decision_engine = decision_engine or DecisionEngine()
        self.alert_builder = alert_builder or AlertBuilder()

    def evaluate(
        self,
        token: TokenMarketData,
        utility: UtilityEvidence,
        risk: RiskAssessment,
        *,
        catalyst_score: float = 0.0,
        confidence: float | None = None,
        why_now: str,
        invalidation_conditions: list[str] | tuple[str, ...] = (),
        wallet_intelligence_score: float | None = None,
    ) -> PipelineResult:
        """Evaluate one candidate and optionally create a qualified alert.

        ``confidence`` may be supplied by an upstream analyst. When omitted,
        the deterministic scoring engine's evidence-completeness confidence is
        used. Wallet intelligence is an evidence input to the existing
        100-point community bucket; it never bypasses hard filters.
        """
        validation = self.validator.validate(token, utility)
        score_result = self.scoring_engine.score(
            token,
            utility,
            risk,
            catalyst_score=catalyst_score,
            wallet_intelligence_score=wallet_intelligence_score,
        )
        effective_confidence = score_result.confidence if confidence is None else confidence
        decision = self.decision_engine.decide(
            token,
            utility,
            risk,
            score_result.breakdown,
            effective_confidence,
            validation,
        )

        alert = None
        if self.decision_engine.is_alertable(decision) and why_now.strip():
            alert = self.alert_builder.build(
                token,
                utility,
                risk,
                decision,
                why_now=why_now,
                invalidation_conditions=invalidation_conditions,
            )

        return PipelineResult(validation=validation, decision=decision, alert=alert)
