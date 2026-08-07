"""End-to-end live scanner orchestration.

The runner connects live collection to real evidence verification and then to
the deterministic validation/scoring/decision/alert pipeline. Missing or
unverified evidence fails closed before notification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, Sequence

from .collector import CollectedToken, LiveSolanaCollector
from .models import RiskAssessment, UtilityEvidence
from .notifier import Alert
from .pipeline import DecisionAlertPipeline, PipelineResult


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

    @property
    def should_notify(self) -> bool:
        return self.pipeline is not None and self.pipeline.should_notify


class LiveScannerRunner:
    """Run one live discovery cycle without bypassing safety gates."""

    def __init__(
        self,
        collector: LiveSolanaCollector,
        evidence_provider: EvidenceProvider | None = None,
        pipeline: DecisionAlertPipeline | None = None,
        transport: AlertTransport | None = None,
    ) -> None:
        self.collector = collector
        if evidence_provider is None:
            # Lazy import prevents an import cycle: analyst.py validates against
            # CandidateEvidence from this module while the runner remains the
            # public orchestration boundary.
            from .analyst import RealEvidenceAnalyst

            evidence_provider = RealEvidenceAnalyst()
        self.evidence_provider = evidence_provider
        self.pipeline = pipeline or DecisionAlertPipeline()
        self.transport = transport

    def run_once(self) -> list[LiveRunResult]:
        """Collect candidates, verify evidence, evaluate them, and notify.

        Candidates with unavailable or unverifiable evidence are recorded as
        skipped and can never reach the notification transport.
        """
        results: list[LiveRunResult] = []
        candidates: Sequence[CollectedToken] = self.collector.collect()

        for candidate in candidates:
            mint = candidate.token.address
            try:
                evidence = self.evidence_provider.enrich(candidate)
                pipeline_result = self.pipeline.evaluate(
                    candidate.token,
                    evidence.utility,
                    evidence.risk,
                    catalyst_score=evidence.catalyst_score,
                    confidence=evidence.confidence,
                    why_now=evidence.why_now,
                    invalidation_conditions=evidence.invalidation_conditions,
                )

                notified = False
                if pipeline_result.alert is not None and self.transport is not None:
                    alert = Alert(
                        text=pipeline_result.alert.text,
                        contract_address=pipeline_result.alert.contract_address,
                    )
                    self.transport.send(alert)
                    notified = True

                results.append(
                    LiveRunResult(
                        contract_address=mint,
                        pipeline=pipeline_result,
                        notified=notified,
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
