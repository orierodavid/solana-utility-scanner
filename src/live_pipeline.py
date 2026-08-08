"""End-to-end live scanner orchestration.

The runner connects live collection to real evidence verification and then to
validation, scoring, decision, historical recording, and guarded notification.
Missing or unverified evidence fails closed before notification.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import os
from dataclasses import dataclass
from typing import Protocol, Sequence

from .collector import CollectedToken, LiveSolanaCollector
from .models import RiskAssessment, UtilityEvidence
from .notifier import Alert
from .outcomes import AlertOutcomeRecord, JsonlOutcomeStore, OutcomeStore
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
        if transport is None and os.getenv("ENABLE_TELEGRAM_ALERTS", "").strip().lower() in {"1", "true", "yes"}:
            from .telegram import TelegramNotifier

            transport = TelegramNotifier()
        self.transport = transport
        self.wallet_engine = wallet_engine or WalletIntelligenceEngine()
        if outcome_store is None:
            outcome_path = os.getenv("OUTCOME_STORE_PATH", "data/outcomes.jsonl")
            outcome_store = JsonlOutcomeStore(outcome_path)
        self.outcome_store = outcome_store
        self.alert_cooldown_seconds = float(os.getenv("ALERT_COOLDOWN_SECONDS", "21600"))
        if self.alert_cooldown_seconds < 0:
            raise ValueError("ALERT_COOLDOWN_SECONDS must not be negative")

    def _recently_notified(self, mint: str, now: datetime) -> bool:
        if self.alert_cooldown_seconds == 0:
            return False
        checker = getattr(self.outcome_store, "was_recently_notified", None)
        if not callable(checker):
            return False
        cutoff = now.astimezone(timezone.utc) - timedelta(seconds=self.alert_cooldown_seconds)
        return bool(checker(mint, since=cutoff))

    def run_once(self) -> list[LiveRunResult]:
        """Collect candidates, evaluate them, persist outcomes, and optionally deliver alerts.

        Candidates with unavailable or unverifiable evidence are recorded as
        skipped and can never reach the notification transport. Qualified
        alerts are deduplicated using the persisted outcome history without
        changing the underlying score or decision.
        """
        results: list[LiveRunResult] = []
        candidates: Sequence[CollectedToken] = self.collector.collect()

        for candidate in candidates:
            mint = candidate.token.address
            try:
                evidence = self.evidence_provider.enrich(candidate)
                wallet = self.wallet_engine.analyze(candidate)
                why_now = f"{evidence.why_now} {wallet.summary}"
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
                    now = datetime.now(timezone.utc)
                    if self._recently_notified(mint, now):
                        logger.info("Alert suppressed by cooldown for %s", mint)
                    else:
                        alert = Alert(
                            text=pipeline_result.alert.text,
                            contract_address=pipeline_result.alert.contract_address,
                        )
                        self.transport.send(alert)
                        notified = True

                decision = pipeline_result.decision
                if decision.breakdown is None:
                    raise RuntimeError("Decision result did not contain a score breakdown")

                record = AlertOutcomeRecord.from_decision(
                    event_id=mint + ":" + candidate.token.observed_at.isoformat(),
                    token=candidate.token,
                    decision=decision.decision,
                    score=decision.breakdown,
                    confidence=decision.confidence,
                    risk_overall=evidence.risk.overall_risk,
                    risk_hard_filter_failed=evidence.risk.hard_filter_failed,
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
