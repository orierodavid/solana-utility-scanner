"""Hard eligibility and safety validation for Solana utility tokens."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import TokenMarketData, UtilityEvidence


@dataclass(frozen=True)
class ValidationResult:
    """Deterministic result of the hard-filter stage."""

    passed: bool
    reasons: tuple[str, ...]

    @property
    def hard_filter_failed(self) -> bool:
        return not self.passed


class TokenValidator:
    """Apply mandatory eligibility and data-quality rules.

    Utility verification is not a hard validation failure. TRUTH has a
    secondary HIGH_POTENTIAL lane, so an evidence outage must not prevent a
    candidate from reaching market and risk analysis.
    """

    def __init__(
        self,
        min_liquidity_usd: float = 10_000.0,
        min_holders: int = 50,
        max_top_holder_concentration_pct: float = 35.0,
        max_creator_holding_pct: float = 15.0,
    ) -> None:
        if min_liquidity_usd < 0:
            raise ValueError("min_liquidity_usd cannot be negative")
        if min_holders < 0:
            raise ValueError("min_holders cannot be negative")
        if not 0 <= max_top_holder_concentration_pct <= 100:
            raise ValueError("max_top_holder_concentration_pct must be 0-100")
        if not 0 <= max_creator_holding_pct <= 100:
            raise ValueError("max_creator_holding_pct must be 0-100")
        self.min_liquidity_usd = min_liquidity_usd
        self.min_holders = min_holders
        self.max_top_holder_concentration_pct = max_top_holder_concentration_pct
        self.max_creator_holding_pct = max_creator_holding_pct

    def validate(
        self,
        token: TokenMarketData,
        utility: UtilityEvidence | None = None,
    ) -> ValidationResult:
        reasons: list[str] = []

        if token.chain != "solana":
            reasons.append("Token is not on Solana")
        if not token.address:
            reasons.append("Missing token mint address")

        if token.market_cap_zone.value == "OUTSIDE":
            reasons.append("Market cap is outside the $50k-$150k discovery range")

        if token.liquidity_usd < self.min_liquidity_usd:
            reasons.append(
                f"Liquidity ${token.liquidity_usd:,.0f} is below minimum ${self.min_liquidity_usd:,.0f}"
            )

        if token.volume_24h_usd <= 0:
            reasons.append("Missing or zero 24h trading volume")
        if token.price_usd <= 0:
            reasons.append("Missing or zero token price")

        if token.holders is None:
            reasons.append("Holder count is unavailable")
        elif token.holders < self.min_holders:
            reasons.append(f"Holder count {token.holders} is below minimum {self.min_holders}")

        if token.top_holder_concentration_pct is None:
            reasons.append("Top-holder concentration is unavailable")
        elif token.top_holder_concentration_pct > self.max_top_holder_concentration_pct:
            reasons.append(
                f"Top-holder concentration {token.top_holder_concentration_pct:.1f}% exceeds "
                f"maximum {self.max_top_holder_concentration_pct:.1f}%"
            )

        if token.creator_holding_pct is not None and token.creator_holding_pct > self.max_creator_holding_pct:
            reasons.append(
                f"Creator holding {token.creator_holding_pct:.1f}% exceeds "
                f"maximum {self.max_creator_holding_pct:.1f}%"
            )

        # Utility evidence is handled as a lane/evidence state by the decision
        # engine. Never fabricate utility; simply do not hard-drop the token.
        return ValidationResult(passed=not reasons, reasons=tuple(reasons))


def validate_token(
    token: TokenMarketData,
    utility: UtilityEvidence | None = None,
    **kwargs: float | int,
) -> ValidationResult:
    """Convenience function for the application pipeline."""
    return TokenValidator(**kwargs).validate(token, utility)


def summarize_failures(results: Iterable[ValidationResult]) -> list[str]:
    """Return unique validation failures while preserving encounter order."""
    seen: set[str] = set()
    failures: list[str] = []
    for result in results:
        for reason in result.reasons:
            if reason not in seen:
                seen.add(reason)
                failures.append(reason)
    return failures
