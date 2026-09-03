"""Deterministic two-lane opportunity scoring for TRUTH.

Utility is the primary thesis. A secondary high-potential lane can qualify a
non-utility token when market, momentum, catalyst/community and risk evidence
are unusually strong. Market cap is a priority signal, not an absolute $50K
cutoff, so exceptional early opportunities above $50K are not discarded.
"""
from __future__ import annotations
from dataclasses import dataclass
from .models import Decision, MarketCapZone, RiskAssessment, ScoreBreakdown, TokenMarketData, UtilityEvidence

BUY_THRESHOLD=85.0
WAIT_THRESHOLD=75.0
SECONDARY_BUY_THRESHOLD=88.0

@dataclass(frozen=True)
class ScoreResult:
    breakdown: ScoreBreakdown
    confidence: float
    decision: Decision
    lane: str = "UTILITY"

class ScoringEngine:
    """Calculate a transparent 100-point score across two discovery lanes."""
    def score(self,token:TokenMarketData,utility:UtilityEvidence,risk:RiskAssessment,*,catalyst_score:float=0.0,wallet_intelligence_score:float|None=None)->ScoreResult:
        if not 0.0<=catalyst_score<=10.0: raise ValueError("catalyst_score must be between 0 and 10")
        if wallet_intelligence_score is not None and not 0.0<=wallet_intelligence_score<=10.0: raise ValueError("wallet_intelligence_score must be between 0 and 10")
        breakdown=ScoreBreakdown(utility=self._utility_score(utility),market_structure=self._market_structure_score(token),momentum=self._momentum_score(token),development=self._development_score(utility),catalysts=catalyst_score,community=self._community_score(token,wallet_intelligence_score),risk=self._risk_score(risk))
        lane="UTILITY" if utility.verified else "HIGH_POTENTIAL"
        confidence=self._confidence(token,utility,risk,wallet_intelligence_score,lane)
        if token.market_cap_zone is MarketCapZone.OUTSIDE or risk.hard_filter_failed:
            decision=Decision.NO_TRADE
        elif token.market_cap_zone is MarketCapZone.LATE_CONFIRMATION:
            decision=Decision.MISSED_ENTRY
        elif lane=="HIGH_POTENTIAL" and breakdown.total>=SECONDARY_BUY_THRESHOLD and confidence>=80 and risk.overall_risk<=25:
            decision=Decision.BUY_CANDIDATE
        elif lane=="UTILITY" and breakdown.total>=BUY_THRESHOLD and confidence>=BUY_THRESHOLD and risk.overall_risk<=30:
            decision=Decision.BUY_CANDIDATE
        elif lane=="UTILITY" and token.market_cap_zone is MarketCapZone.EARLY_BUY and breakdown.total>=70 and confidence>=70 and risk.overall_risk<=30:
            decision=Decision.EARLY_BUY
        elif lane=="UTILITY" and token.market_cap_zone is MarketCapZone.CONFIRMATION and breakdown.total>=WAIT_THRESHOLD and confidence>=75 and risk.overall_risk<=30:
            decision=Decision.CONFIRMATION
        elif breakdown.total>=WAIT_THRESHOLD:
            decision=Decision.WAIT
        else:
            decision=Decision.NO_TRADE
        return ScoreResult(breakdown=breakdown,confidence=confidence,decision=decision,lane=lane)

    @staticmethod
    def _utility_score(u:UtilityEvidence)->float:
        return round(5.0*sum((u.has_real_use_case,u.product_exists,u.token_is_used_by_product,u.active_development)),2)
    @staticmethod
    def _market_structure_score(t:TokenMarketData)->float:
        if t.market_cap_zone is MarketCapZone.OUTSIDE or t.market_cap_zone is MarketCapZone.LATE_CONFIRMATION:return 0.0
        score=10.0 if t.market_cap_zone is MarketCapZone.EARLY_BUY else 7.0
        if t.market_cap_usd>0:
            lr=t.liquidity_usd/t.market_cap_usd
            if lr>=.30:score+=3
            elif lr>=.20:score+=2.5
            elif lr>=.10:score+=2
            elif lr>=.05:score+=1
            vr=t.volume_24h_usd/t.market_cap_usd
            if vr>=1:score+=2
            elif vr>=.50:score+=1.5
            elif vr>=.20:score+=1
            elif vr>=.10:score+=.5
        return round(min(score,15),2)
    @staticmethod
    def _momentum_score(t:TokenMarketData)->float:
        score=0.0;c=t.price_change_24h_pct
        if c is not None:
            if c>=30:score+=10
            elif c>=15:score+=8
            elif c>=5:score+=6
            elif c>=0:score+=4
            elif c>=-10:score+=2
        b,s=t.buy_count_24h,t.sell_count_24h
        if b is not None and s is not None and b+s>0:
            p=b/(b+s)*100
            if p>=65:score+=6
            elif p>=58:score+=5
            elif p>=52:score+=4
            elif p>=48:score+=2
        vc=t.volume_change_24h_pct
        if vc is not None:
            if vc>=50:score+=4
            elif vc>=20:score+=3
            elif vc>0:score+=2
            elif vc>=-20:score+=1
        return round(min(score,20),2)
    @staticmethod
    def _development_score(u:UtilityEvidence)->float:
        return round(min((10 if u.active_development else 0)+(3 if u.product_exists else 0)+(2 if u.token_is_used_by_product else 0),15),2)
    @staticmethod
    def _community_score(t:TokenMarketData,wallet:float|None=None)->float:
        base=0.0;h=t.holders
        if h is not None:
            if h>=1000:base+=5
            elif h>=500:base+=4
            elif h>=250:base+=3
            elif h>=100:base+=2
            elif h>0:base+=1
        g=t.holder_growth_24h_pct
        if g is not None:
            if g>=20:base+=3
            elif g>=10:base+=2
            elif g>0:base+=1
        c=t.top_holder_concentration_pct
        if c is not None:
            if c<=20:base+=2
            elif c<=30:base+=1
        base=min(base,10)
        if wallet is None:return round(base,2)
        return round(min(base*.4+max(0,min(wallet,10))*.6,10),2)
    @staticmethod
    def _risk_score(r:RiskAssessment)->float:return round(max(0,10-r.overall_risk/10),2)
    @staticmethod
    def _confidence(t:TokenMarketData,u:UtilityEvidence,r:RiskAssessment,wallet:float|None,lane:str)->float:
        checks=[t.market_cap_usd>0,t.liquidity_usd>0,t.volume_24h_usd>0,t.price_usd>0,t.price_change_24h_pct is not None,t.buy_count_24h is not None and t.sell_count_24h is not None,t.holders is not None,t.top_holder_concentration_pct is not None,t.token_age_hours is not None,not r.hard_filter_failed]
        if lane=="UTILITY":checks.extend([u.has_real_use_case,u.product_exists,u.token_is_used_by_product,u.active_development])
        if wallet is not None:checks.append(wallet>=0)
        return round(sum(checks)/len(checks)*100,2)
