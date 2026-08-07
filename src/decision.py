"""Deterministic final decision gate for the scanner."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Decision, MarketCapZone, RiskAssessment, ScoreBreakdown, TokenMarketData, UtilityEvidence
from .validator import ValidationResult


@dataclass(frozen=True)
class DecisionResult:
    decision: Decision
    score: float
    confidence: float
    reasons: tuple[str, ...]
    breakdown: ScoreBreakdown | None = None

    @property
    def actionable(self) -> bool:
        return self.decision is Decision.BUY_CANDIDATE


class DecisionEngine:
    """Convert validated evidence into BUY, WAIT, or NO_TRADE."""

    def __init__(self, buy_score: float = 85.0, buy_confidence: float = 85.0, wait_score: float = 75.0) -> None:
        if not 0 <= wait_score <= buy_score <= 100:
            raise ValueError("Scores must satisfy 0 <= wait_score <= buy_score <= 100")
        if not 0 <= buy_confidence <= 100:
            raise ValueError("buy_confidence must be between 0 and 100")
        self.buy_score = buy_score
        self.buy_confidence = buy_confidence
        self.wait_score = wait_score

    def decide(
        self,
        token: TokenMarketData,
        utility: UtilityEvidence,
        risk: RiskAssessment,
        score: ScoreBreakdown,
        confidence: float,
        validation: ValidationResult,
    ) -> DecisionResult:
        reasons: list[str] = []

        if not 0 <= confidence <= 100:
            raise ValueError("confidence must be between 0 and 100")

        if not validation.passed:
            reasons.extend(validation.reasons)
            return DecisionResult(Decision.NO_TRADE, score.total, confidence, tuple(reasons), score)

        if token.market_cap_zone is MarketCapZone.OUTSIDE:
            reasons.append("Market cap is outside the discovery range")
            return DecisionResult(Decision.NO_TRADE, score.total, confidence, tuple(reasons), score)

        if not utility.verified:
            reasons.append("Utility verification failed")
            return DecisionResult(Decision.NO_TRADE, score.total, confidence, tuple(reasons), score)

        if risk.hard_filter_failed:
            reasons.extend(risk.reasons or ["Hard risk filter failed"])
            return DecisionResult(Decision.NO_TRADE, score.total, confidence, tuple(reasons), score)

        if score.total >= self.buy_score and confidence >= self.buy_confidence:
            reasons.append("Score and confidence both meet actionable thresholds")
            return DecisionResult(Decision.BUY_CANDIDATE, score.total, confidence, tuple(reasons), score)

        if score.total >= self.wait_score:
            if score.total < self.buy_score:
                reasons.append(f"Score {score.total:.2f} is below buy threshold {self.buy_score:.2f}")
            if confidence < self.buy_confidence:
                reasons.append(f"Confidence {confidence:.2f} is below buy threshold {self.buy_confidence:.2f}")
            return DecisionResult(Decision.WAIT, score.total, confidence, tuple(reasons), score)

        reasons.append(f"Score {score.total:.2f} is below wait threshold {self.wait_score:.2f}")
        return DecisionResult(Decision.NO_TRADE, score.total, confidence, tuple(reasons), score)

    @staticmethod
    def is_alertable(result: DecisionResult) -> bool:
        """Enforce the master actionable threshold at the notification boundary."""
        return (
            result.decision is Decision.BUY_CANDIDATE
            and result.score >= 85.0
            and result.confidence >= 85.0
        )
