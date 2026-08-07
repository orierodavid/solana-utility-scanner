"""Deterministic opportunity scoring for early-stage Solana utility tokens.

Market cap determines eligibility, not the trade decision. The score combines
utility, market structure, momentum, development, catalysts, community, and
risk evidence into a transparent 0-100 opportunity score.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log10

from .models import RiskAssessment, ScoreBreakdown, TokenMarketData, UtilityEvidence


@dataclass(frozen=True)
class ScoringInputs:
    """Evidence not directly represented by TokenMarketData."""

    utility_quality: float = 0.0
    development_quality: float = 0.0
    catalyst_strength: float = 0.0
    community_quality: float = 0.0
    buy_pressure_pct: float | None = None
    smart_money_score: float = 0.0
    price_momentum_score: float = 0.0


class OpportunityScorer:
    """Calculate the transparent 100-point opportunity score."""

    def score(
        self,
        token: TokenMarketData,
        utility: UtilityEvidence,
        risk: RiskAssessment,
        inputs: ScoringInputs | None = None,
    ) -> ScoreBreakdown:
        inputs = inputs or ScoringInputs()
        return ScoreBreakdown(
            utility=self._utility(utility, inputs),
            market_structure=self._market_structure(token, risk),
            momentum=self._momentum(token, inputs),
            development=round(self._bounded(inputs.development_quality) * 15, 2),
            catalysts=round(self._bounded(inputs.catalyst_strength) * 10, 2),
            community=round(self._bounded(inputs.community_quality) * 10, 2),
            risk=round(max(0.0, 10.0 - risk.overall_risk / 10.0), 2),
        )

    @staticmethod
    def _bounded(value: float) -> float:
        return max(0.0, min(1.0, value))

    def _utility(self, utility: UtilityEvidence, inputs: ScoringInputs) -> float:
        evidence = sum(
            [
                utility.has_real_use_case,
                utility.product_exists,
                utility.token_is_used_by_product,
                utility.active_development,
            ]
        ) / 4.0
        quality = self._bounded(inputs.utility_quality)
        return round(((evidence * 0.6) + (quality * 0.4)) * 20, 2)

    def _market_structure(self, token: TokenMarketData, risk: RiskAssessment) -> float:
        if 50_000 <= token.market_cap_usd <= 100_000:
            mc_score = 1.0
        elif 100_000 < token.market_cap_usd <= 150_000:
            mc_score = 0.8
        else:
            mc_score = 0.0

        liquidity_ratio = token.liquidity_usd / max(token.market_cap_usd, 1.0)
        liquidity_score = min(1.0, liquidity_ratio / 0.50)
        structure_quality = (
            mc_score * 0.35
            + liquidity_score * 0.40
            + (1 - risk.overall_risk / 100) * 0.25
        )
        return round(structure_quality * 15, 2)

    def _momentum(self, token: TokenMarketData, inputs: ScoringInputs) -> float:
        volume_score = self._volume_score(token)
        holder_score = self._growth_score(token.holder_growth_24h_pct)
        buy_score = self._buy_pressure_score(inputs.buy_pressure_pct)
        momentum = (
            volume_score * 0.30
            + holder_score * 0.20
            + buy_score * 0.20
            + self._bounded(inputs.smart_money_score) * 0.15
            + self._bounded(inputs.price_momentum_score) * 0.15
        )
        return round(momentum * 20, 2)

    @staticmethod
    def _volume_score(token: TokenMarketData) -> float:
        if token.market_cap_usd <= 0 or token.volume_24h_usd <= 0:
            return 0.0
        ratio = token.volume_24h_usd / token.market_cap_usd
        return min(1.0, log10(1 + ratio * 10) / 2.0)

    @staticmethod
    def _growth_score(growth_pct: float | None) -> float:
        if growth_pct is None or growth_pct <= 0:
            return 0.0
        return min(1.0, growth_pct / 50.0)

    @staticmethod
    def _buy_pressure_score(buy_pressure_pct: float | None) -> float:
        if buy_pressure_pct is None:
            return 0.0
        return max(0.0, min(1.0, (buy_pressure_pct - 50.0) / 30.0))


def calculate_score(
    token: TokenMarketData,
    utility: UtilityEvidence,
    risk: RiskAssessment,
    inputs: ScoringInputs | None = None,
) -> ScoreBreakdown:
    """Convenience wrapper for the application pipeline."""
    return OpportunityScorer().score(token, utility, risk, inputs)
