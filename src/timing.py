"""Early-setup timing engine for the Solana utility scanner.

The normal score answers "is this token attractive now?". This module answers
"is the market structure beginning to accelerate while the move is still
reasonably early?". It is deliberately conservative: utility and hard-risk
gates remain mandatory, and a token with an already-excessive short-term price
move is treated as late rather than early.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Any

from .models import RiskAssessment, TokenMarketData, UtilityEvidence


@dataclass(frozen=True)
class EarlySetupSignal:
    """A deterministic early-stage signal independent of the BUY decision."""

    score: float
    qualified: bool
    late: bool
    reasons: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]


class EarlySetupDetector:
    """Detect accelerating setups before the normal BUY threshold is reached."""

    def __init__(
        self,
        *,
        minimum_score: float = 70.0,
        maximum_age_hours: float = 24.0,
        minimum_liquidity_usd: float = 10_000.0,
    ) -> None:
        self.minimum_score = minimum_score
        self.maximum_age_hours = maximum_age_hours
        self.minimum_liquidity_usd = minimum_liquidity_usd

    @staticmethod
    def _buy_pressure(buys: int | None, sells: int | None) -> float | None:
        if buys is None or sells is None or buys + sells <= 0:
            return None
        return buys / (buys + sells) * 100

    @staticmethod
    def _positive_growth(current: float, previous: Any) -> float:
        try:
            previous_value = float(previous)
        except (TypeError, ValueError):
            return 0.0
        if previous_value <= 0:
            return 0.0
        return (current - previous_value) / previous_value * 100

    def evaluate(
        self,
        token: TokenMarketData,
        utility: UtilityEvidence,
        risk: RiskAssessment,
        *,
        previous: Mapping[str, Any] | None = None,
        wallet_score: float | None = None,
    ) -> EarlySetupSignal:
        reasons: list[str] = []
        score = 0.0

        if token.market_cap_zone.value == "OUTSIDE":
            return EarlySetupSignal(0.0, False, False, ("Market cap is outside the configured discovery range",), ())
        if token.liquidity_usd < self.minimum_liquidity_usd:
            return EarlySetupSignal(0.0, False, False, ("Liquidity is below the early-setup minimum",), ())
        if not utility.verified:
            return EarlySetupSignal(0.0, False, False, ("Utility verification is incomplete",), ())
        if risk.hard_filter_failed:
            return EarlySetupSignal(0.0, False, False, ("A hard risk filter failed",), tuple(risk.reasons))

        age_ok = token.token_age_hours is None or token.token_age_hours <= self.maximum_age_hours
        if age_ok:
            score += 10
            reasons.append("Token is still inside the early-age window")

        volume_acceleration = 0.0
        if token.volume_1h_usd is not None and token.volume_24h_usd > 0:
            baseline = token.volume_24h_usd / 24.0
            if baseline > 0:
                volume_acceleration = token.volume_1h_usd / baseline
                if volume_acceleration >= 3.0:
                    score += 30
                    reasons.append(f"1h volume is {volume_acceleration:.1f}x its 24h hourly baseline")
                elif volume_acceleration >= 2.0:
                    score += 24
                    reasons.append(f"1h volume is {volume_acceleration:.1f}x its 24h hourly baseline")
                elif volume_acceleration >= 1.5:
                    score += 17
                    reasons.append(f"1h volume is {volume_acceleration:.1f}x its 24h hourly baseline")

        buy_pressure = self._buy_pressure(token.buy_count_1h, token.sell_count_1h)
        if buy_pressure is not None:
            if buy_pressure >= 60:
                score += 20
                reasons.append(f"1h buy pressure is {buy_pressure:.1f}%")
            elif buy_pressure >= 55:
                score += 15
                reasons.append(f"1h buy pressure is {buy_pressure:.1f}%")
            elif buy_pressure >= 52:
                score += 8

        price_1h = token.price_change_1h_pct
        price_5m = token.price_change_5m_pct
        late = bool((price_1h is not None and price_1h > 15) or (price_5m is not None and price_5m > 8))
        if late:
            reasons.append("Short-term price expansion is already too large for an early-entry alert")
        elif price_1h is not None:
            if 2 <= price_1h <= 10:
                score += 15
                reasons.append(f"1h price momentum is positive but not yet extended ({price_1h:.1f}%)")
            elif 0 <= price_1h < 2:
                score += 8
                reasons.append("1h price momentum is beginning to turn positive")
            elif -2 <= price_1h < 0:
                score += 3

        if token.market_cap_usd > 0 and token.volume_24h_usd / token.market_cap_usd >= 0.5:
            score += 10
            reasons.append("24h turnover is already meaningful relative to market cap")

        if previous:
            mc_growth = self._positive_growth(token.market_cap_usd, previous.get("market_cap_usd"))
            volume_growth = self._positive_growth(token.volume_24h_usd, previous.get("volume_24h_usd"))
            price_growth = self._positive_growth(token.price_usd, previous.get("price_usd"))
            if mc_growth >= 3:
                score += 5
                reasons.append(f"Market cap accelerated {mc_growth:.1f}% since the previous scan")
            if volume_growth >= 10:
                score += 5
                reasons.append(f"24h volume accelerated {volume_growth:.1f}% since the previous scan")
            if 2 <= price_growth <= 12:
                score += 5
                reasons.append(f"Price advanced {price_growth:.1f}% since the previous scan")

        if wallet_score is not None:
            score += max(0.0, min(wallet_score, 10.0)) * 0.5

        score = round(min(score, 100.0), 2)
        qualified = age_ok and not late and score >= self.minimum_score
        invalidation = (
            "1h volume acceleration falls back toward baseline",
            "Buy pressure falls below the configured early-entry level",
            "Price becomes materially extended before confirmation",
            "Liquidity deteriorates or a hard security filter fails",
        )
        return EarlySetupSignal(score, qualified, late, tuple(reasons), invalidation)
