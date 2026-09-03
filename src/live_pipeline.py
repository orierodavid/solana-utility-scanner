"""End-to-end live scanner orchestration with monitored candidate retention."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
import logging,os
from dataclasses import dataclass
from typing import Protocol
from .collector import CollectedToken
from .models import Decision, RiskAssessment, UtilityEvidence
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
    def _fallback_evidence(self,candidate,reason):
        """Keep a candidate evaluable when project evidence is unavailable.

        Missing first-party evidence is an evidence state, not a discovery failure.
        The candidate enters the secondary high-potential lane with no fabricated
        utility claims; normal risk and market-cap gates still apply.
        """
        token=candidate.token
        security=candidate.security
        hc=token.top_holder_concentration_pct
        holder=70 if hc is None else 90 if hc>35 else 60 if hc>25 else 30 if hc>15 else 0
        ratio=token.liquidity_usd/max(token.market_cap_usd,1.0)
        liq=85 if ratio<.05 else 60 if ratio<.10 else 35 if ratio<.20 else 0
        contract=0
        reasons=[]
        if hc is None: reasons.append("Top-holder concentration could not be independently verified")
        if token.mint_authority_active is None or token.freeze_authority_active is None: contract=30; reasons.append("Token authority state is incomplete")
        else:
            if token.mint_authority_active: contract+=35; reasons.append("Mint authority is active")
            if token.freeze_authority_active: contract+=45; reasons.append("Freeze authority is active")
        rug=0; creator=0
        if security is None: rug=80; creator=70; reasons.append("Independent security report is unavailable")
        risk=RiskAssessment(rug_pull_risk=rug,holder_concentration_risk=holder,contract_risk=min(contract,100),liquidity_risk=liq,creator_wallet_risk=creator,hard_filter_failed=holder>=90 or liq>=85 or rug>=80 or contract>=80,reasons=tuple(dict.fromkeys(reasons)))
        utility=UtilityEvidence(has_real_use_case=False,product_exists=False,token_is_used_by_product=False,active_development=False,evidence_urls=[],notes=f"UTILITY_UNDER_INVESTIGATION: {reason}")
        return CandidateEvidence(utility=utility,risk=risk,why_now="First-party utility evidence is unavailable; evaluating this candidate only through the secondary high-potential lane using market, momentum and risk evidence.",confidence=None,catalyst_score=0.0,invalidation_conditions=("First-party/project evidence remains unavailable or contradicts the thesis.","Liquidity or holder concentration breaches a hard risk threshold.","Momentum or volume deteriorates enough to invalidate the current setup."))
    def run_once(self):
        results=[]
        for candidate in self.collector.collect():
            mint=candidate.token.address; was_watched=any(str(x.get("contract_address"))==mint for x in self.watchlist_store.entries())
            try:
                try:
                    evidence=self.evidence_provider.enrich(candidate)
                except Exception as evidence_exc:
                    from .evidence import EvidenceError
                    if isinstance(evidence_exc,EvidenceError):
                        logger.warning("Candidate %s has incomplete utility evidence; retaining for market/risk evaluation: %s",mint,evidence_exc)
                        evidence=self._fallback_evidence(candidate,str(evidence_exc))
                    else:
                        raise
                wallet=self.wallet_engine.analyze(candidate); why_now=f"{evidence.why_now} {wallet.summary}".strip()
                pr=self.pipeline.evaluate(candidate.token,evidence.utility,evidence.risk,catalyst_score=evidence.catalyst_score,confidence=evidence.confidence,why_now=why_now,invalidation_conditions=evidence.invalidation_conditions,wallet_intelligence_score=wallet.actionable_score)
                logger.info("CANDIDATE_EVAL mint=%s symbol=%s mc=%.2f liquidity=%.2f score=%.2f confidence=%.2f risk=%s decision=%s lane=%s utility_verified=%s",mint,candidate.token.symbol,candidate.token.market_cap_usd,candidate.token.liquidity_usd,pr.score,pr.confidence,evidence.risk.overall_risk,pr.decision.decision.value,pr.decision.lane,evidence.utility.verified)
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
