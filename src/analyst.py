"""Structured AI analysis and evidence synthesis for Solana candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .collector import CollectedToken
from .models import RiskAssessment, ScoreBreakdown, TokenMarketData, UtilityEvidence


@dataclass(frozen=True)
class AnalysisRequest:
    """Evidence package supplied to an AI provider."""

    token: TokenMarketData
    utility: UtilityEvidence
    risk: RiskAssessment
    score: ScoreBreakdown

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "token": {
                "name": self.token.name,
                "symbol": self.token.symbol,
                "chain": self.token.chain,
                "contract_address": self.token.address,
                "market_cap_usd": self.token.market_cap_usd,
                "market_cap_zone": self.token.market_cap_zone.value,
                "liquidity_usd": self.token.liquidity_usd,
                "volume_24h_usd": self.token.volume_24h_usd,
                "holders": self.token.holders,
                "holder_growth_24h_pct": self.token.holder_growth_24h_pct,
                "volume_change_24h_pct": self.token.volume_change_24h_pct,
            },
            "utility": self.utility.model_dump(),
            "risk": self.risk.model_dump(),
            "score": {**self.score.model_dump(), "total": self.score.total},
        }


class Analyst:
    """Build deterministic analysis instructions and validate AI output."""

    SYSTEM_INSTRUCTION = (
        "Analyze only the supplied evidence. Never invent data, URLs, catalysts, "
        "wallet activity, or contract addresses. Preserve the exact contract_address "
        "from the evidence. Market cap is a discovery filter, not a standalone buy "
        "signal. Explain why now, key risks, and invalidation conditions. Return JSON."
    )

    def build_request(self, token: TokenMarketData, utility: UtilityEvidence, risk: RiskAssessment, score: ScoreBreakdown) -> AnalysisRequest:
        return AnalysisRequest(token=token, utility=utility, risk=risk, score=score)

    def build_messages(self, request: AnalysisRequest) -> list[dict[str, Any]]:
        return [
            {"role": "system", "content": self.SYSTEM_INSTRUCTION},
            {"role": "user", "content": {
                "task": "Produce a concise trade thesis for this validated candidate.",
                "required_fields": ["contract_address", "why_now", "key_evidence", "key_risks", "invalidation_conditions", "confidence"],
                "evidence": request.to_prompt_payload(),
            }},
        ]

    @staticmethod
    def validate_response(response: Mapping[str, Any], expected_contract_address: str) -> dict[str, Any]:
        required = ("contract_address", "why_now", "confidence")
        missing = [field for field in required if field not in response]
        if missing:
            raise ValueError(f"AI response missing required fields: {', '.join(missing)}")
        if response["contract_address"] != expected_contract_address:
            raise ValueError("AI returned a contract address different from the verified mint address")
        confidence = response["confidence"]
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 100:
            raise ValueError("AI confidence must be a number from 0 to 100")
        if not isinstance(response["why_now"], str) or not response["why_now"].strip():
            raise ValueError("AI why_now must be a non-empty string")
        return dict(response)


@dataclass(frozen=True)
class AnalystFinding:
    """Conservative thesis synthesized only from measured evidence."""

    thesis: str
    risks: tuple[str, ...]
    catalysts: tuple[str, ...]
    confidence: float


class EvidenceAnalyst:
    """Turn source-backed evidence into a conservative live-scanner thesis."""

    def analyze(
        self,
        candidate: CollectedToken,
        utility: UtilityEvidence,
        risk: RiskAssessment,
        *,
        catalyst_signals: Sequence[str] = (),
    ) -> AnalystFinding:
        token = candidate.token
        thesis_parts = [
            f"{token.symbol} is inside the configured {token.market_cap_zone.value.lower()} market-cap zone at ${token.market_cap_usd:,.0f}.",
            f"Liquidity is ${token.liquidity_usd:,.0f} and 24h volume is ${token.volume_24h_usd:,.0f}.",
        ]
        if utility.verified:
            thesis_parts.append("Utility is supported by source-backed project evidence.")
        if token.holder_growth_24h_pct is not None and token.holder_growth_24h_pct > 0:
            thesis_parts.append(f"Holder growth is positive at {token.holder_growth_24h_pct:+.1f}% over 24h.")
        if token.buy_count_24h is not None and token.sell_count_24h is not None:
            total = token.buy_count_24h + token.sell_count_24h
            if total:
                pressure = token.buy_count_24h / total * 100
                thesis_parts.append(f"Observed buy pressure is {pressure:.1f}%.")

        risks = list(risk.reasons)
        if token.mint_authority_active:
            risks.append("Mint authority is active.")
        if token.freeze_authority_active:
            risks.append("Freeze authority is active.")
        if not risks:
            risks.append("No material risk finding was produced by the current evidence set.")

        catalysts = tuple(dict.fromkeys(catalyst_signals))
        confidence = max(0.0, 100.0 - min(50.0, len(risks) * 8.0))
        return AnalystFinding(
            thesis=" ".join(thesis_parts),
            risks=tuple(dict.fromkeys(risks)),
            catalysts=catalysts,
            confidence=confidence,
        )
