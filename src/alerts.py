"""Alert payload construction for qualified and early-stage scanner signals."""

from __future__ import annotations

from dataclasses import dataclass

from .decision import DecisionResult
from .models import Decision, RiskAssessment, TokenMarketData, UtilityEvidence
from .timing import EarlySetupSignal


@dataclass(frozen=True)
class AlertPayload:
    """Immutable notification payload with the exact token mint preserved."""

    decision: Decision
    contract_address: str
    text: str


class AlertBuilder:
    """Build deterministic BUY and early-setup notifications."""

    @staticmethod
    def _risk_level(risk: RiskAssessment) -> str:
        overall = risk.overall_risk
        if overall < 30:
            return "LOW"
        if overall < 60:
            return "MEDIUM"
        return "HIGH"

    def build(self, token: TokenMarketData, utility: UtilityEvidence, risk: RiskAssessment, result: DecisionResult, *, why_now: str, invalidation_conditions: list[str] | tuple[str, ...] = ()) -> AlertPayload:
        if result.decision is not Decision.BUY_CANDIDATE:
            raise ValueError("Only BUY_CANDIDATE decisions can produce alerts")
        if not why_now.strip() or risk.hard_filter_failed or token.market_cap_zone.value == "OUTSIDE" or result.breakdown is None:
            raise ValueError("BUY alert prerequisites failed")

        is_high_potential = result.lane == "HIGH_POTENTIAL"
        if not is_high_potential and not utility.verified:
            raise ValueError("Utility BUY alert requires verified utility evidence")

        buys = token.buy_count_24h or 0
        sells = token.sell_count_24h or 0
        trade_count = buys + sells
        buy_pressure = (buys / trade_count * 100) if trade_count else None
        buy_pressure_text = f"{buy_pressure:.1f}%" if buy_pressure is not None else "Unavailable"
        holder_growth = f"{token.holder_growth_24h_pct:.1f}%" if token.holder_growth_24h_pct is not None else "Unavailable"
        risks = risk.reasons or ["No hard risk-filter failures"]
        invalidation = list(invalidation_conditions) or ["Required setup evidence deteriorates or a mandatory risk filter fails"]

        if is_high_potential:
            title = "SOLANA HIGH-POTENTIAL ALERT"
            lane_text = "HIGH_POTENTIAL — Utility not independently verified"
            decision_text = "BUY_CANDIDATE (SECONDARY LANE)"
        else:
            title = "SOLANA UTILITY TRADE ALERT"
            lane_text = "UTILITY — Verified utility"
            decision_text = "BUY_CANDIDATE"

        text = "\n".join([
            title, "",
            f"Token: {token.name} (${token.symbol})",
            f"Contract: {token.address}",
            f"Market Cap: ${token.market_cap_usd:,.0f}",
            f"Liquidity: ${token.liquidity_usd:,.0f}",
            f"24h Volume: ${token.volume_24h_usd:,.0f}",
            f"Token Age: {token.token_age_hours:.1f}h" if token.token_age_hours is not None else "Token Age: Unavailable", "",
            f"Opportunity Score: {result.score:.2f}/100",
            f"Risk Level: {self._risk_level(risk)}",
            f"Confidence: {result.confidence:.2f}%",
            f"Lane: {lane_text}", "",
            f"Momentum: {result.breakdown.momentum:.2f}/20",
            f"Holder Growth: {holder_growth}",
            f"Buy/Sell Pressure: {buy_pressure_text}",
            f"Catalyst Score: {result.breakdown.catalysts:.2f}/10", "",
            f"Decision: {decision_text}", "", f"Why Now: {why_now.strip()}", "",
            "Key Risks:", *[f"- {reason}" for reason in risks], "",
            "Invalidation Conditions:", *[f"- {condition}" for condition in invalidation],
        ])
        return AlertPayload(decision=result.decision, contract_address=token.address, text=text)

    def build_early_setup(self, token: TokenMarketData, risk: RiskAssessment, signal: EarlySetupSignal, *, why_now: str) -> AlertPayload:
        """Build a pre-pump WATCH alert without falsely calling it a BUY."""
        if not signal.qualified:
            raise ValueError("Early setup signal is not qualified")
        if risk.hard_filter_failed or token.market_cap_zone.value == "OUTSIDE":
            raise ValueError("Early alert prerequisites failed")

        buy_pressure = None
        if token.buy_count_1h is not None and token.sell_count_1h is not None:
            total = token.buy_count_1h + token.sell_count_1h
            if total:
                buy_pressure = token.buy_count_1h / total * 100

        volume_acceleration = "Unavailable"
        if token.volume_1h_usd is not None and token.volume_24h_usd > 0:
            baseline = token.volume_24h_usd / 24
            if baseline > 0:
                volume_acceleration = f"{token.volume_1h_usd / baseline:.1f}x"

        risks = risk.reasons or ["No hard risk-filter failures"]
        text = "\n".join([
            "SOLANA UTILITY EARLY SETUP", "",
            f"Token: {token.name} (${token.symbol})",
            f"Contract: {token.address}",
            f"Market Cap: ${token.market_cap_usd:,.0f}",
            f"Liquidity: ${token.liquidity_usd:,.0f}",
            f"24h Volume: ${token.volume_24h_usd:,.0f}",
            f"Token Age: {token.token_age_hours:.1f}h" if token.token_age_hours is not None else "Token Age: Unavailable", "",
            f"Early Setup Score: {signal.score:.2f}/100",
            f"Risk Level: {self._risk_level(risk)}",
            f"1h Volume Acceleration: {volume_acceleration}",
            f"1h Buy Pressure: {buy_pressure:.1f}%" if buy_pressure is not None else "1h Buy Pressure: Unavailable",
            f"1h Price Change: {token.price_change_1h_pct:.1f}%" if token.price_change_1h_pct is not None else "1h Price Change: Unavailable", "",
            "Decision: WATCH_FOR_CONFIRMATION", "", f"Why Now: {why_now.strip()}", "",
            "Early Signals:", *[f"- {reason}" for reason in signal.reasons], "",
            "Key Risks:", *[f"- {reason}" for reason in risks], "",
            "Invalidation Conditions:", *[f"- {condition}" for condition in signal.invalidation_conditions],
        ])
        return AlertPayload(decision=Decision.WAIT, contract_address=token.address, text=text)
