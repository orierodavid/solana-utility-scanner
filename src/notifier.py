"""Alert formatting and notification safety for actionable Solana trades."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .decision import DecisionResult
from .models import Decision, TokenAnalysis


@dataclass(frozen=True)
class Alert:
    """Immutable notification payload."""

    text: str
    contract_address: str


class NotificationError(ValueError):
    """Raised when an alert cannot be safely constructed or delivered."""


def build_alert(analysis: TokenAnalysis, decision: DecisionResult) -> Alert | None:
    """Build an actionable alert for EARLY_BUY or BUY_CANDIDATE.

    The exact verified mint is always taken from TokenMarketData.
    """
    if decision.decision not in {Decision.EARLY_BUY, Decision.BUY_CANDIDATE}:
        return None
    minimum = 70 if decision.decision is Decision.EARLY_BUY else 85
    if decision.score < minimum or decision.confidence < minimum:
        raise NotificationError("Actionable alert requires the decision's score and confidence threshold")

    address = analysis.token.address
    if not address or address != analysis.contract_address:
        raise NotificationError("Verified contract address is missing or inconsistent")

    early = decision.decision is Decision.EARLY_BUY
    title = "🚨 SOLANA UTILITY EARLY BUY" if early else "🚨 SOLANA UTILITY TRADE CANDIDATE"
    label = "🟢 EARLY BUY" if early else "🟢 BUY CANDIDATE"
    text = "\n".join(
        [
            title,
            "",
            f"Token: {analysis.token.name} (${analysis.token.symbol})",
            f"Contract / Mint Address: {address}",
            f"Market Cap: ${analysis.token.market_cap_usd:,.0f}",
            f"Liquidity: ${analysis.token.liquidity_usd:,.0f}",
            f"24h Volume: ${analysis.token.volume_24h_usd:,.0f}",
            f"Opportunity Score: {decision.score:.2f}/100",
            f"Confidence: {decision.confidence:.2f}%",
            "",
            f"Decision: {label}",
            f"Why Now: {analysis.why_now}",
            "",
            "Key Risks:",
            *([f"- {reason}" for reason in analysis.risk.reasons] or ["- No specific risk reason recorded"]),
            "",
            "Invalidation Conditions:",
            *([f"- {item}" for item in analysis.invalidation_conditions] or ["- None recorded"]),
        ]
    )

    if address not in text:
        raise NotificationError("Contract address integrity check failed")

    return Alert(text=text, contract_address=address)


def send_alert(alert: Alert, sender: Callable[[str], object]) -> object:
    """Send an already-validated alert through a provider callback."""
    if not alert.contract_address or alert.contract_address not in alert.text:
        raise NotificationError("Refusing to send an alert without its exact contract address")
    return sender(alert.text)


def telegram_payload(alert: Alert) -> Mapping[str, str]:
    """Return a Telegram payload with the exact mint rendered copy-friendly."""
    if not alert.contract_address or alert.contract_address not in alert.text:
        raise NotificationError("Invalid alert payload")

    contract_label = f"Contract / Mint Address: {alert.contract_address}"
    formatted_label = f"Contract / Mint Address: <code>{alert.contract_address}</code>"
    text = alert.text.replace(contract_label, formatted_label, 1)

    return {"text": text, "parse_mode": "HTML"}
