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
        return self.decision in {Decision.EARLY_BUY, Decision.BUY_CANDIDATE}


class DecisionEngine:
    """Convert validated evidence into an entry-timed trade decision."""

    def __init__(self, buy_score: float = 85.0, buy_confidence: float = 85.0, wait_score: float = 75.0,
                 early_buy_score: float = 70.0, early_buy_confidence: float = 70.0,
                 confirmation_score: float = 75.0, confirmation_confidence: float = 75.0) -> None:
        if not 0 <= wait_score <= buy_score <= 100:
            raise ValueError("Scores must satisfy 0 <= wait_score <= buy_score <= 100")
        for value, name in ((buy_confidence, "buy_confidence"), (early_buy_confidence, "early_buy_confidence"),
                            (confirmation_confidence, "confirmation_confidence")):
            if not 0 <= value <= 100:
                raise ValueError(f"{name} must be between 0 and 100")
        if not 0 <= early_buy_score <= 100 or not 0 <= confirmation_score <= 100:
            raise ValueError("Early and confirmation scores must be between 0 and 100")
        self.buy_score = buy_score
        self.buy_confidence = buy_confidence
        self.wait_score = wait_score
        self.early_buy_score = early_buy_score
        self.early_buy_confidence = early_buy_confidence
        self.confirmation_score = confirmation_score
        self.confirmation_confidence = confirmation_confidence

    def decide(self, token: TokenMarketData, utility: UtilityEvidence, risk: RiskAssessment,
               score: ScoreBreakdown, confidence: float, validation: ValidationResult) -> DecisionResult:
        reasons: list[str] = []
        if not 0 <= confidence <= 100:
            raise ValueError("confidence must be between 0 and 100")
        if not validation.passed:
            reasons.extend(validation.reasons)
            return DecisionResult(Decision.NO_TRADE, score.total, confidence, tuple(reasons), score)

        zone = token.market_cap_zone
        if zone is MarketCapZone.OUTSIDE:
            reasons.append("Market cap is outside the $40K-$150K strategy range")
            return DecisionResult(Decision.NO_TRADE, score.total, confidence, tuple(reasons), score)
        if not utility.verified:
            reasons.append("Utility verification failed")
            return DecisionResult(Decision.NO_TRADE, score.total, confidence, tuple(reasons), score)
        if risk.hard_filter_failed:
            reasons.extend(risk.reasons or ["Hard risk filter failed"])
            return DecisionResult(Decision.NO_TRADE, score.total, confidence, tuple(reasons), score)

        if zone is MarketCapZone.LATE_CONFIRMATION:
            reasons.append("Token is above the preferred entry window; treat this as a missed-entry reminder, not a fresh buy")
            return DecisionResult(Decision.MISSED_ENTRY, score.total, confidence, tuple(reasons), score)
        if zone is MarketCapZone.EARLY_BUY and score.total >= self.early_buy_score and confidence >= self.early_buy_confidence:
            reasons.append("Token is inside the $40K-$75K early-entry zone and meets the early-buy thresholds")
            return DecisionResult(Decision.EARLY_BUY, score.total, confidence, tuple(reasons), score)
        if zone is MarketCapZone.CONFIRMATION and score.total >= self.confirmation_score and confidence >= self.confirmation_confidence:
            reasons.append("Token is in the $75K-$120K confirmation zone; the early-entry window has passed")
            return DecisionResult(Decision.CONFIRMATION, score.total, confidence, tuple(reasons), score)
        if zone is MarketCapZone.CONFIRMATION and score.total >= self.buy_score and confidence >= self.buy_confidence:
            reasons.append("Strong score confirmed, but the preferred early-entry window has passed")
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
        if result.decision is Decision.EARLY_BUY:
            return result.score >= 70.0 and result.confidence >= 70.0
        if result.decision is Decision.BUY_CANDIDATE:
            return result.score >= 85.0 and result.confidence >= 85.0
        return False
