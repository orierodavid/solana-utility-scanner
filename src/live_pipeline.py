"""End-to-end live scanner orchestration with early-entry timing detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import os
from dataclasses import dataclass
from typing import Protocol, Sequence

from .collector import CollectedToken, LiveSolanaCollector
from .models import Decision, RiskAssessment, UtilityEvidence
from .notifier import Alert
from .outcomes import AlertOutcomeRecord, JsonlOutcomeStore, OutcomeStore
from .pipeline import DecisionAlertPipeline, PipelineResult
from .timing import EarlySetupDetector
from .wallet_intelligence import WalletIntelligenceEngine

logger = logging.getLogger("solana-utility-scanner.live")


@dataclass(frozen=True)
class CandidateEvidence:
    utility: UtilityEvidence
    risk: RiskAssessment
    why_now: str
    catalyst_score: float = 0.0
    confidence: float | None = None
    invalidation_conditions: tuple[str, ...] = ()


class EvidenceProvider(Protocol):
    def enrich(self, candidate: CollectedToken) -> CandidateEvidence:
        ...


class AlertTransport(Protocol):
    def send(self, alert: Alert) -> object:
        ...


@dataclass(frozen=True)
class LiveRunResult:
    contract_address: str
    pipeline: PipelineResult | None
    notified: bool
    error: str | None = None
    wallet_score: float | None = None
    alert_type: str | None = None

    @property
    def should_notify(self) -> bool:
        return self.notified or (self.pipeline is not None and self.pipeline.should_notify)


class LiveScannerRunner:
    """Run live discovery while separating early-entry alerts from later signals."""

    def __init__(self, collector: LiveSolanaCollector | None = None, evidence_provider: EvidenceProvider | None = None, pipeline: DecisionAlertPipeline | None = None, transport: AlertTransport | None = None, wallet_engine: WalletIntelligenceEngine | None = None, outcome_store: OutcomeStore | None = None) -> None:
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
        self.buy_alert_cooldown_seconds = float(os.getenv("ALERT_COOLDOWN_SECONDS", "21600"))
        self.early_alert_cooldown_seconds = float(os.getenv("EARLY_ALERT_COOLDOWN_SECONDS", "1800"))
        if self.buy_alert_cooldown_seconds < 0 or self.early_alert_cooldown_seconds < 0:
            raise ValueError("Alert cooldowns must not be negative")
        self.timing_detector = EarlySetupDetector()

    def _recently_notified(self, mint: str, now: datetime, *, alert_type: str, cooldown_seconds: float) -> bool:
        if cooldown_seconds == 0:
            return False
        checker = getattr(self.outcome_store, "was_recently_notified", None)
        if not callable(checker):
            return False
        cutoff = now.astimezone(timezone.utc) - timedelta(seconds=cooldown_seconds)
        try:
            return bool(checker(mint, since=cutoff, alert_type=alert_type))
        except TypeError:
            return bool(checker(mint, since=cutoff))

    def _latest_snapshot(self, mint: str):
        getter = getattr(self.outcome_store, "latest_snapshot", None)
        return getter(mint) if callable(getter) else None

    def run_once(self) -> list[LiveRunResult]:
        results: list[LiveRunResult] = []
        candidates: Sequence[CollectedToken] = self.collector.collect()

        for candidate in candidates:
            mint = candidate.token.address
            try:
                evidence = self.evidence_provider.enrich(candidate)
                wallet = self.wallet_engine.analyze(candidate)
                why_now = f"{evidence.why_now} {wallet.summary}".strip()
                pipeline_result = self.pipeline.evaluate(
                    candidate.token, evidence.utility, evidence.risk,
                    catalyst_score=evidence.catalyst_score,
                    confidence=evidence.confidence,
                    why_now=why_now,
                    invalidation_conditions=evidence.invalidation_conditions,
                    wallet_intelligence_score=wallet.actionable_score,
                )

                notified = False
                alert_type: str | None = None
                alert_payload = pipeline_result.alert

                if alert_payload is not None:
                    alert_type = "EARLY_BUY" if pipeline_result.decision.decision is Decision.EARLY_BUY else "BUY"

                if alert_payload is None and evidence.confidence is not None and evidence.confidence >= 70:
                    timing = self.timing_detector.evaluate(
                        candidate.token, evidence.utility, evidence.risk,
                        previous=self._latest_snapshot(mint),
                        wallet_score=wallet.actionable_score,
                    )
                    if timing.qualified:
                        early_why_now = f"{why_now} Early timing signals: {'; '.join(timing.reasons)}"
                        alert_payload = self.pipeline.alert_builder.build_early_setup(
                            candidate.token, evidence.risk, timing, why_now=early_why_now,
                        )
                        alert_type = "EARLY_SETUP"

                if alert_payload is not None and self.transport is not None:
                    now = datetime.now(timezone.utc)
                    kind = alert_type or "BUY"
                    cooldown = self.buy_alert_cooldown_seconds if kind == "BUY" else self.early_alert_cooldown_seconds
                    if self._recently_notified(mint, now, alert_type=kind, cooldown_seconds=cooldown):
                        logger.info("%s alert suppressed by cooldown for %s", kind, mint)
                        alert_payload = None
                    else:
                        self.transport.send(Alert(text=alert_payload.text, contract_address=alert_payload.contract_address))
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
                    alert_type=alert_type or "BUY",
                )
                self.outcome_store.append(record)

                results.append(LiveRunResult(contract_address=mint, pipeline=pipeline_result, notified=notified, wallet_score=wallet.actionable_score, alert_type=alert_type))
            except Exception as exc:
                logger.warning("Candidate %s skipped: %s", mint, exc)
                results.append(LiveRunResult(contract_address=mint, pipeline=None, notified=False, error=str(exc)))

        return results
