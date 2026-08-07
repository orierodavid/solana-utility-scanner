"""End-to-end live scanner orchestration.

This module connects the read-only live collector to the deterministic
validation/scoring/decision/alert pipeline and, when configured, the guarded
Telegram transport. It is deliberately provider-neutral at the evidence
boundary: no utility, risk, catalyst, or thesis data is invented here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, Sequence

from .collector import CollectedToken, LiveSolanaCollector
from .models import RiskAssessment, UtilityEvidence
from .notifier import Alert
from .outcomes import AlertOutcomeRecord, NullOutcomeStore, OutcomeStore
from .pipeline import DecisionAlertPipeline, PipelineResult
from .wallet_intelligence import WalletIntelligenceEngine


logger = logging.getLogger("solana-utility-scanner.live")


@dataclass(frozen=True)
class CandidateEvidence:
    """Externally verified evidence required to evaluate one live candidate."""

    utility: UtilityEvidence
    risk: RiskAssessment
    why_now: str
    catalyst_score: float = 0.0
    confidence: float | None = None
    invalidation_conditions: tuple[str, ...] = ()


class EvidenceProvider(Protocol):
    """Resolve live candidate data into verified decision evidence."""

    def enrich(self, candidate: CollectedToken) -> CandidateEvidence:
        """Return evidence or raise if the candidate cannot be verified."""
        ...


class AlertTransport(Protocol):
    """Minimal transport contract used by the live runner."""

    def send(self, alert: Alert) -> object:
        """Deliver one already-qualified alert."""
        ...


@dataclass(frozen=True)
class LiveRunResult:
    """Result for one collected candidate."""

    contract_address: str
    pipeline: PipelineResult | None
    notified: bool
    error: str | None = None
    wallet_score: float | None = None

    @property
    def should_notify(self) -> bool:
        return self.pipeline is not None and self.pipeline.should_notify


class LiveScannerRunner:
    """Run one live discovery cycle without bypassing safety gates."""

    def __init__(
        self,
        collector: LiveSolanaCollector | None = None,
        evidence_provider: EvidenceProvider | None = None,
        pipeline: DecisionAlertPipeline | None = None,
        transport: AlertTransport | None = None,
        wallet_engine: WalletIntelligenceEngine | None = None,
        outcome_store: OutcomeStore | None = None,
    ) -> None:
        self.collector = collector or LiveSolanaCollector()
        if evidence_provider is None:
            from .evidence import LiveEvidenceProvider

            evidence_provider = LiveEvidenceProvider()
        self.evidence_provider = evidence_provider
        self.pipeline = pipeline or DecisionAlertPipeline()
        self.transport = transport
        self.wallet_engine = wallet_engine or WalletIntelligenceEngine()
        self.outcome_store = outcome_store or NullOutcomeStore()

    def run_once(self) -> list[LiveRunResult]:
        """Collect candidates, evaluate them, persist outcomes, and optionally deliver alerts.

        Any candidate whose evidence cannot be verified is fail-closed: it is
        recorded as an error and cannot reach the notification transport.
        Historical persistence is observational only and never changes the
        decision or alert result.
        """
        results: list[LiveRunResult] = []
        candidates: Sequence[CollectedToken] = self.collector.collect()

        for candidate in candidates:
            mint = candidate.token.address
            try:
                evidence = self.evidence_provider.enrich(candidate)
                wallet = self.wallet_engine.analyze(candidate)
                wallet_context = wallet.summary
                why_now = f"{evidence.why_now} {wallet_context}"
                pipeline_result = self.pipeline.evaluate(
                    candidate.token,
                    evidence.utility,
                    evidence.risk,
                    catalyst_score=evidence.catalyst_score,
                    confidence=evidence.confidence,
                    why_now=why_now,
                    invalidation_conditions=evidence.invalidation_conditions,
                    wallet_intelligence_score=wallet.actionable_score,
                )

                notified = False
                if pipeline_result.alert is not None and self.transport is not None:
                    alert = Alert(
                        text=pipeline_result.alert.text,
                        contract_address=pipeline_result.alert.contract_address,
                    )
                    self.transport.send(alert)
                    notified = True

                decision = pipeline_result.decision
                record = AlertOutcomeRecord.from_decision(
                    event_id=mint + ":" + candidate.token.observed_at.isoformat(),
                    token=candidate.token,
                    decision=decision.decision,
                    score=pipeline_result.decision.score,
                    confidence=decision.confidence,
                    risk_overall=decision.risk.overall_risk,
                    risk_hard_filter_failed=decision.risk.hard_filter_failed,
                    why_now=why_now,
                    invalidation_conditions=evidence.invalidation_conditions,
                    wallet_intelligence_score=wallet.actionable_score,
                    notified=notified,
                    observed_at=candidate.token.observed_at,
                )
                self.outcome_store.append(record)

                results.append(
                    LiveRunResult(
                        contract_address=mint,
                        pipeline=pipeline_result,
                        notified=notified,
                        wallet_score=wallet.actionable_score,
                    )
                )
            except Exception as exc:  # fail closed for one candidate, continue scan
                logger.warning("Candidate %s skipped: %s", mint, exc)
                results.append(
                    LiveRunResult(
                        contract_address=mint,
                        pipeline=None,
                        notified=False,
                        error=str(exc),
                    )
                )

        return results
