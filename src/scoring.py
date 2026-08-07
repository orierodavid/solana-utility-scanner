"""Deterministic trade-opportunity scoring for the Solana utility-token scanner.

The scoring engine is deliberately transparent and side-effect free. It never
places trades, invents missing evidence, or treats market cap as a buy signal.
A token must first satisfy the hard market-cap/utility/risk gates in the
analysis model before a BUY_CANDIDATE decision can be produced.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    Decision,
    RiskAssessment,
    ScoreBreakdown,
    TokenMarketData,
    UtilityEvidence,
)


BUY_THRESHOLD = 85.0
WAIT_THRESHOLD = 75.0


@dataclass(frozen=True)
class ScoreResult:
    """Transparent score plus decision-ready metadata."""

    breakdown: ScoreBreakdown
    confidence: float
    decision: Decision


class ScoringEngine:
    """Calculate the scanner's 100-point opportunity score.

    Weighting:
      utility          20
      market_structure 15
      momentum         20
      development      15
      catalysts        10
      community        10 (holder/community structure plus wallet intelligence)
      risk             10

    Unknown values receive no points. This is intentional: the engine must
    never manufacture bullish evidence merely because a provider omitted data.
    """

    def score(
        self,
        token: TokenMarketData,
        utility: UtilityEvidence,
        risk: RiskAssessment,
        *,
        catalyst_score: float = 0.0,
        wallet_intelligence_score: float | None = None,
    ) -> ScoreResult:
        if not 0.0 <= catalyst_score <= 10.0:
            raise ValueError("catalyst_score must be between 0 and 10")
        if wallet_intelligence_score is not None and not 0.0 <= wallet_intelligence_score <= 10.0:
            raise ValueError("wallet_intelligence_score must be between 0 and 10")

        breakdown = ScoreBreakdown(
            utility=self._utility_score(utility),
            market_structure=self._market_structure_score(token),
            momentum=self._momentum_score(token),
            development=self._development_score(utility),
            catalysts=catalyst_score,
            community=self._community_score(token, wallet_intelligence_score),
            risk=self._risk_score(risk),
        )

        confidence = self._confidence(token, utility, risk, wallet_intelligence_score)
        if token.market_cap_zone.value == "OUTSIDE" or risk.hard_filter_failed or not utility.verified:
            decision = Decision.NO_TRADE
        elif breakdown.total >= BUY_THRESHOLD and confidence >= BUY_THRESHOLD:
            decision = Decision.BUY_CANDIDATE
        elif breakdown.total >= WAIT_THRESHOLD:
            decision = Decision.WAIT
        else:
            decision = Decision.NO_TRADE

        return ScoreResult(breakdown=breakdown, confidence=confidence, decision=decision)

    @staticmethod
    def _utility_score(utility: UtilityEvidence) -> float:
        return round(
            5.0 * sum(
                (
                    utility.has_real_use_case,
                    utility.product_exists,
                    utility.token_is_used_by_product,
                    utility.active_development,
                )
            ),
            2,
        )

    @staticmethod
    def _market_structure_score(token: TokenMarketData) -> float:
        if token.market_cap_zone.value == "OUTSIDE":
            return 0.0

        score = 0.0
        if token.market_cap_zone.value == "PRIMARY":
            score += 10.0
        elif token.market_cap_zone.value == "SECONDARY":
            score += 7.0

        if token.market_cap_usd > 0:
            liquidity_ratio = token.liquidity_usd / token.market_cap_usd
            if liquidity_ratio >= 0.30:
                score += 3.0
            elif liquidity_ratio >= 0.20:
                score += 2.5
            elif liquidity_ratio >= 0.10:
                score += 2.0
            elif liquidity_ratio >= 0.05:
                score += 1.0

            volume_ratio = token.volume_24h_usd / token.market_cap_usd
            if volume_ratio >= 1.0:
                score += 2.0
            elif volume_ratio >= 0.50:
                score += 1.5
            elif volume_ratio >= 0.20:
                score += 1.0
            elif volume_ratio >= 0.10:
                score += 0.5
        return round(min(score, 15.0), 2)

    @staticmethod
    def _momentum_score(token: TokenMarketData) -> float:
        score = 0.0
        change = token.price_change_24h_pct
        if change is not None:
            if change >= 30:
                score += 10.0
            elif change >= 15:
                score += 8.0
            elif change >= 5:
                score += 6.0
            elif change >= 0:
                score += 4.0
            elif change >= -10:
                score += 2.0

        buys = token.buy_count_24h
        sells = token.sell_count_24h
        if buys is not None and sells is not None and buys + sells > 0:
            buy_pressure = buys / (buys + sells) * 100
            if buy_pressure >= 65:
                score += 6.0
            elif buy_pressure >= 58:
                score += 5.0
            elif buy_pressure >= 52:
                score += 4.0
            elif buy_pressure >= 48:
                score += 2.0

        volume_change = token.volume_change_24h_pct
        if volume_change is not None:
            if volume_change >= 50:
                score += 4.0
            elif volume_change >= 20:
                score += 3.0
            elif volume_change > 0:
                score += 2.0
            elif volume_change >= -20:
                score += 1.0

        return round(min(score, 20.0), 2)

    @staticmethod
    def _development_score(utility: UtilityEvidence) -> float:
        score = 10.0 if utility.active_development else 0.0
        score += 3.0 if utility.product_exists else 0.0
        score += 2.0 if utility.token_is_used_by_product else 0.0
        return round(min(score, 15.0), 2)

    @staticmethod
    def _community_score(token: TokenMarketData, wallet_intelligence_score: float | None = None) -> float:
        base = 0.0
        holders = token.holders
        if holders is not None:
            if holders >= 1000:
                base += 5.0
            elif holders >= 500:
                base += 4.0
            elif holders >= 250:
                base += 3.0
            elif holders >= 100:
                base += 2.0
            elif holders > 0:
                base += 1.0

        growth = token.holder_growth_24h_pct
        if growth is not None:
            if growth >= 20:
                base += 3.0
            elif growth >= 10:
                base += 2.0
            elif growth > 0:
                base += 1.0

        concentration = token.top_holder_concentration_pct
        if concentration is not None:
            if concentration <= 20:
                base += 2.0
            elif concentration <= 30:
                base += 1.0

        base = min(base, 10.0)
        if wallet_intelligence_score is None:
            return round(base, 2)

        # Wallet intelligence is deliberately blended into the existing
        # 10-point community bucket, rather than creating points out of thin
        # air. This keeps the total score exactly 100 points.
        wallet_component = max(0.0, min(wallet_intelligence_score, 10.0))
        blended = base * 0.4 + wallet_component * 0.6
        return round(min(blended, 10.0), 2)

    @staticmethod
    def _risk_score(risk: RiskAssessment) -> float:
        return round(max(0.0, 10.0 - risk.overall_risk / 10.0), 2)

    @staticmethod
    def _confidence(
        token: TokenMarketData,
        utility: UtilityEvidence,
        risk: RiskAssessment,
        wallet_intelligence_score: float | None = None,
    ) -> float:
        """Estimate evidence completeness, not probability of profit."""
        checks = [
            token.market_cap_usd > 0,
            token.liquidity_usd > 0,
            token.volume_24h_usd > 0,
            token.price_usd > 0,
            token.price_change_24h_pct is not None,
            token.buy_count_24h is not None and token.sell_count_24h is not None,
            token.holders is not None,
            token.top_holder_concentration_pct is not None,
            token.token_age_hours is not None,
            utility.has_real_use_case,
            utility.product_exists,
            utility.token_is_used_by_product,
            utility.active_development,
            not risk.hard_filter_failed,
        ]
        if wallet_intelligence_score is not None:
            checks.append(wallet_intelligence_score >= 0)
        return round(sum(checks) / len(checks) * 100, 2)
