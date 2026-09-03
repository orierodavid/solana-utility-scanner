"""Deterministic final decision gate for the two-lane TRUTH scanner."""
from __future__ import annotations
from dataclasses import dataclass
from .models import Decision, MarketCapZone, RiskAssessment, ScoreBreakdown, TokenMarketData, UtilityEvidence
from .validator import ValidationResult

@dataclass(frozen=True)
class DecisionResult:
    decision: Decision
    score: float
    confidence: float
    reasons: tuple[str,...]
    breakdown: ScoreBreakdown|None=None
    lane: str="UTILITY"
    @property
    def actionable(self)->bool:return self.decision in {Decision.EARLY_BUY,Decision.BUY_CANDIDATE}

class DecisionEngine:
    def __init__(self,buy_score:float=85.0,buy_confidence:float=85.0,wait_score:float=75.0,early_buy_score:float=70.0,early_buy_confidence:float=70.0,confirmation_score:float=75.0,confirmation_confidence:float=75.0,early_buy_max_risk:int=30,secondary_buy_score:float=88.0,secondary_buy_confidence:float=80.0,secondary_max_risk:int=25)->None:
        self.buy_score=buy_score;self.buy_confidence=buy_confidence;self.wait_score=wait_score;self.early_buy_score=early_buy_score;self.early_buy_confidence=early_buy_confidence;self.confirmation_score=confirmation_score;self.confirmation_confidence=confirmation_confidence;self.early_buy_max_risk=early_buy_max_risk;self.secondary_buy_score=secondary_buy_score;self.secondary_buy_confidence=secondary_buy_confidence;self.secondary_max_risk=secondary_max_risk
    def decide(self,token:TokenMarketData,utility:UtilityEvidence,risk:RiskAssessment,score:ScoreBreakdown,confidence:float,validation:ValidationResult)->DecisionResult:
        reasons:list[str]=[];lane="UTILITY" if utility.verified else "HIGH_POTENTIAL"
        if not validation.passed:
            reasons.extend(validation.reasons);return DecisionResult(Decision.NO_TRADE,score.total,confidence,tuple(reasons),score,lane)
        zone=token.market_cap_zone
        if zone is MarketCapZone.OUTSIDE:
            reasons.append("Market cap is outside the early-opportunity range");return DecisionResult(Decision.NO_TRADE,score.total,confidence,tuple(reasons),score,lane)
        if risk.hard_filter_failed:
            reasons.extend(risk.reasons or ["Hard risk filter failed"]);return DecisionResult(Decision.NO_TRADE,score.total,confidence,tuple(reasons),score,lane)
        if zone is MarketCapZone.LATE_CONFIRMATION:
            reasons.append("Token is above the preferred early-entry window");return DecisionResult(Decision.MISSED_ENTRY,score.total,confidence,tuple(reasons),score,lane)
        if lane=="UTILITY":
            if zone is MarketCapZone.EARLY_BUY and score.total>=self.early_buy_score and confidence>=self.early_buy_confidence and risk.overall_risk<=self.early_buy_max_risk:
                reasons.append("Primary utility lane: early-entry thresholds met");return DecisionResult(Decision.EARLY_BUY,score.total,confidence,tuple(reasons),score,lane)
            if zone is MarketCapZone.CONFIRMATION and score.total>=self.confirmation_score and confidence>=self.confirmation_confidence and risk.overall_risk<=self.early_buy_max_risk:
                reasons.append("Primary utility lane: strong confirmation");return DecisionResult(Decision.CONFIRMATION,score.total,confidence,tuple(reasons),score,lane)
            if score.total>=self.buy_score and confidence>=self.buy_confidence:
                reasons.append("Primary utility lane: full buy threshold met");return DecisionResult(Decision.BUY_CANDIDATE,score.total,confidence,tuple(reasons),score,lane)
        else:
            if zone is MarketCapZone.EARLY_BUY and score.total>=self.secondary_buy_score and confidence>=self.secondary_buy_confidence and risk.overall_risk<=self.secondary_max_risk:
                reasons.append("Secondary high-potential lane: exceptional early opportunity");return DecisionResult(Decision.EARLY_BUY,score.total,confidence,tuple(reasons),score,lane)
            if score.total>=self.secondary_buy_score and confidence>=self.secondary_buy_confidence and risk.overall_risk<=self.secondary_max_risk:
                reasons.append("Secondary high-potential lane: exceptional opportunity");return DecisionResult(Decision.BUY_CANDIDATE,score.total,confidence,tuple(reasons),score,lane)
        if score.total>=self.wait_score:
            reasons.append(f"Score {score.total:.2f} is below the actionable threshold for the {lane} lane");return DecisionResult(Decision.WAIT,score.total,confidence,tuple(reasons),score,lane)
        reasons.append(f"Score {score.total:.2f} is below wait threshold {self.wait_score:.2f}");return DecisionResult(Decision.NO_TRADE,score.total,confidence,tuple(reasons),score,lane)
    @staticmethod
    def is_alertable(result:DecisionResult)->bool:
        if result.decision is Decision.EARLY_BUY:return result.score>=70 and result.confidence>=70
        if result.decision is Decision.BUY_CANDIDATE:return result.score>=85 and result.confidence>=85
        return False
