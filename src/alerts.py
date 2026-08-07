"""Alert payload construction for qualified scanner decisions.

The notifier layer is intentionally separate from transport. This module only
builds a deterministic alert payload; Telegram/API credentials are not needed
until a transport adapter is added.
"""

from __future__ import annotations

from dataclasses import dataclass

from .decision import DecisionResult
from .models import Decision, RiskAssessment, TokenMarketData, UtilityEvidence


@dataclass(frozen=True)
class AlertPayload:
    """Immutable notification payload with the exact token mint preserved."""

    decision: Decision
    contract_address: str
    text: str


class AlertBuilder:
    """Build alerts only for fully qualified BUY_CANDIDATE decisions."""

    @staticmethod
    def _risk_level(risk: RiskAssessment) -> str:
        overall = risk.overall_risk
        if overall < 30:
            return "LOW"
        if overall < 60:
            return "MEDIUM"
        return "HIGH"

    def build(
        self,
        token: TokenMarketData,
        utility: UtilityEvidence,
        risk: RiskAssessment,
        result: DecisionResult,
        *,
        why_now: str,
        invalidation_conditions: list[str] | tuple[str, ...] = (),
    ) -> AlertPayload:
        """Build a notification payload from the already-validated decision.

        The contract address is read directly from ``token.address``. There is
        deliberately no caller-supplied address parameter, preventing an alert
        from accidentally carrying a symbol/name lookup or stale address.
        """
        if result.decision is not Decision.BUY_CANDIDATE:
            raise ValueError("Only BUY_CANDIDATE decisions can produce alerts")
        if not why_now.strip():
            raise ValueError("why_now is required for an actionable alert")
        if not utility.verified:
            raise ValueError("Utility evidence must be verified before alerting")
        if risk.hard_filter_failed:
            raise ValueError("Hard risk filters must pass before alerting")
        if token.market_cap_zone.value == "OUTSIDE":
            raise ValueError("Token is outside the configured market-cap range")

        buys = token.buy_count_24h or 0
        sells = token.sell_count_24h or 0
        trade_count = buys + sells
        buy_pressure = (buys / trade_count * 100) if trade_count else None
        buy_pressure_text = f"{buy_pressure:.1f}%" if buy_pressure is not None else "Unavailable"
        holder_growth = (
            f"{token.holder_growth_24h_pct:.1f}%"
            if token.holder_growth_24h_pct is not None
            else "Unavailable"
        )
        catalyst = result.score_result.breakdown.catalysts
        risks = risk.reasons or ["No hard risk-filter failures"]
        invalidation = list(invalidation_conditions) or ["Required setup evidence deteriorates or a mandatory risk filter fails"]

        text = "\n".join(
            [
                "SOLANA UTILITY TRADE ALERT",
                "",
                f"Token: {token.name} (${token.symbol})",
                f"Contract: {token.address}",
                f"Market Cap: ${token.market_cap_usd:,.0f}",
                f"Liquidity: ${token.liquidity_usd:,.0f}",
                f"24h Volume: ${token.volume_24h_usd:,.0f}",
                f"Token Age: {token.token_age_hours:.1f}h" if token.token_age_hours is not None else "Token Age: Unavailable",
                "",
                f"Opportunity Score: {result.score:.2f}/100",
                f"Risk Level: {self._risk_level(risk)}",
                f"Confidence: {result.confidence:.2f}%",
                "",
                f"Momentum: {result.score_result.breakdown.momentum:.2f}/20",
                f"Holder Growth: {holder_growth}",
                f"Buy/Sell Pressure: {buy_pressure_text}",
                f"Catalyst Score: {catalyst:.2f}/10",
                "",
                "Decision: BUY_CANDIDATE",
                "",
                f"Why Now: {why_now.strip()}",
                "",
                "Key Risks:",
                *[f"- {reason}" for reason in risks],
                "",
                "Invalidation Conditions:",
                *[f"- {condition}" for condition in invalidation],
            ]
        )
        return AlertPayload(
            decision=result.decision,
            # Preserve the exact mint collected from the Solana data source.
            contract_address=token.address,
            text=text,
        )
