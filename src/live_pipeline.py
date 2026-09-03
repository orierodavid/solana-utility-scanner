"""End-to-end live scanner orchestration with monitored candidate retention."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
import logging,os
from dataclasses import dataclass
from typing import Protocol
from .collector import CollectedToken
from .models import Decision
from .notifier import Alert
from .outcomes import AlertOutcomeRecord,JsonlOutcomeStore
from .pipeline import DecisionAlertPipeline,PipelineResult
from .timing import EarlySetupDetector
from .wallet_intelligence import WalletIntelligenceEngine
from .watchlist import WatchlistStore
logger=logging.getLogger("solana-utility-scanner.live")
@dataclass(frozen=True)
class CandidateEvidence:
    utility:object; risk:object; why_now:str; catalyst_score:float=0.0; confidence:float|None=None; invalidation_conditions:tuple[str,...]=()
class EvidenceProvider(Protocol):
    def enrich(self,candidate:CollectedToken)->CandidateEvidence: ...
class AlertTransport(Protocol):
    def send(self,alert:Alert)->object: ...
@dataclass(frozen=True)
class LiveRunResult:
    contract_address:str; pipeline:PipelineResult|None; notified:bool; error:str|None=None; wallet_score:float|None=None; alert_type:str|None=None; delivery_error:str|None=None; re_evaluated:bool=False
    @property
    def should_notify(self): return self.notified or (self.pipeline is not None and self.pipeline.should_notify)
class LiveScannerRunner:
    def __init__(self,collector=None,evidence_provider=None,pipeline=None,transport=None,wallet_engine=None,outcome_store=None,watchlist_store=None):
        if collector is None:
            from .broad_discovery import BroadLiveSolanaCollector
            collector=BroadLiveSolanaCollector(watchlist_path=os.getenv("WATCHLIST_STORE_PATH","data/watchlist.json"))
        self.collector=collector
        if evidence_provider is None:
            from .evidence import LiveEvidenceProvider; evidence_provider=LiveEvidenceProvider()
        self.evidence_provider=evidence_provider; self.pipeline=pipeline or DecisionAlertPipeline(); self.transport=transport
        if transport is None and os.getenv("ENABLE_TELEGRAM_ALERTS","").strip().lower() in {"1","true","yes"}:
            from .telegram import TelegramNotifier; self.transport=TelegramNotifier()
        self.wallet_engine=wallet_engine or WalletIntelligenceEngine(); self.outcome_store=outcome_store or JsonlOutcomeStore(os.getenv("OUTCOME_STORE_PATH","data/outcomes.jsonl")); self.watchlist_store=watchlist_store or WatchlistStore(os.getenv("WATCHLIST_STORE_PATH","data/watchlist.json")); self.buy_alert_cooldown_seconds=float(os.getenv("ALERT_COOLDOWN_SECONDS","21600")); self.early_alert_cooldown_seconds=float(os.getenv("EARLY_ALERT_COOLDOWN_SECONDS","1800")); self.timing_detector=EarlySetupDetector()
    def _recently_notified(self,mint,now,kind,cooldown):
        if cooldown==0:return False
        checker=getattr(self.outcome_store,"was_recently_notified",None)
        if not callable(checker):return False
        try:return bool(checker(mint,since=now-timedelta(seconds=cooldown),alert_type=kind))
        except TypeError:return bool(checker(mint,since=now-timedelta(seconds=cooldown)))
    def _latest_snapshot(self,mint):
        getter=getattr(self.outcome_store,"latest_snapshot",None); return getter(mint) if callable(getter) else None
    def _watch(self,candidate,reason,**extra):
        t=candidate.token; self.watchlist_store.upsert(t.address,symbol=t.symbol,name=t.name,market_cap_usd=t.market_cap_usd,liquidity_usd=t.liquidity_usd,volume_24h_usd=t.volume_24h_usd,token_age_hours=t.token_age_hours,profile=candidate.profile,rejection_reason=reason,**extra)
    def run_once(self):
        results=[]
        for candidate in self.collector.collect():
            mint=candidate.token.address; was_watched=any(str(x.get("contract_address"))==mint for x in self.watchlist_store.entries())
            try:
                evidence=self.evidence_provider.enrich(candidate); wallet=self.wallet_engine.analyze(candidate); why_now=f"{evidence.why_now} {wallet.summary}".strip()
                pr=self.pipeline.evaluate(candidate.token,evidence.utility,evidence.risk,catalyst_score=evidence.catalyst_score,confidence=evidence.confidence,why_now=why_now,invalidation_conditions=evidence.invalidation_conditions,wallet_intelligence_score=wallet.actionable_score)
                payload=pr.alert; kind=None
                if payload is not None: kind="EARLY_BUY" if pr.decision.decision is Decision.EARLY_BUY else "BUY"
                if payload is None and evidence.confidence is not None and evidence.confidence>=70:
                    timing=self.timing_detector.evaluate(candidate.token,evidence.utility,evidence.risk,previous=self._latest_snapshot(mint),wallet_score=wallet.actionable_score)
                    if timing.qualified: payload=self.pipeline.alert_builder.build_early_setup(candidate.token,evidence.risk,timing,why_now=f"{why_now} Early timing signals: {'; '.join(timing.reasons)}"); kind="EARLY_SETUP"
                notified=False; delivery_error=None
                if payload is not None and self.transport is not None:
                    now=datetime.now(timezone.utc); cooldown=self.buy_alert_cooldown_seconds if kind=="BUY" else self.early_alert_cooldown_seconds
                    if not self._recently_notified(mint,now,kind or "BUY",cooldown):
                        try:
                            self.transport.send(Alert(text=payload.text,contract_address=payload.contract_address)); notified=True
                            logger.info("ALERT_SENT mint=%s type=%s score=%.2f confidence=%.2f",mint,kind,pr.score,pr.confidence)
                        except Exception as exc:
                            delivery_error=f"{type(exc).__name__}: {exc}"; logger.error("ALERT_DELIVERY_FAILED mint=%s type=%s error=%s",mint,kind,delivery_error)
                    else: payload=None; logger.info("ALERT_SUPPRESSED mint=%s type=%s reason=cooldown",mint,kind)
                d=pr.decision
                if d.breakdown is None: raise RuntimeError("Decision result did not contain a score breakdown")
                if payload is None: self._watch(candidate,delivery_error or (d.reasons[0] if d.reasons else d.decision.value),decision=d.decision.value,score=d.score,confidence=d.confidence,risk_overall=evidence.risk.overall_risk,utility_verified=evidence.utility.verified,evidence_urls=list(evidence.utility.evidence_urls),delivery_error=delivery_error,re_evaluated=was_watched)
                else: self.watchlist_store.remove(mint)
                self.outcome_store.append(AlertOutcomeRecord.from_decision(event_id=mint+":"+candidate.token.observed_at.isoformat(),token=candidate.token,decision=d.decision,score=d.breakdown,confidence=d.confidence,risk_overall=evidence.risk.overall_risk,risk_hard_filter_failed=evidence.risk.hard_filter_failed,why_now=why_now,invalidation_conditions=evidence.invalidation_conditions,wallet_intelligence_score=wallet.actionable_score,notified=notified,observed_at=candidate.token.observed_at,alert_type=kind or "BUY",lane=d.lane,utility_verified=evidence.utility.verified))
                results.append(LiveRunResult(mint,pr,notified,delivery_error,wallet_score=wallet.actionable_score,alert_type=kind,re_evaluated=was_watched))
            except Exception as exc:
                logger.warning("Candidate %s skipped: %s",mint,exc); self._watch(candidate,str(exc),decision="EVIDENCE_PENDING",re_evaluated=was_watched); results.append(LiveRunResult(mint,None,False,error=str(exc),re_evaluated=was_watched))
        return results
