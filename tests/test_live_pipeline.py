"""Tests for the end-to-end live scanner runner."""

from dataclasses import dataclass
from datetime import datetime, timezone

from src.collector import CollectedToken, SecurityData
from src.live_pipeline import CandidateEvidence, LiveScannerRunner
from src.models import RiskAssessment, TokenMarketData, UtilityEvidence, Decision


MINT = "So11111111111111111111111111111111111111112"


def make_candidate() -> CollectedToken:
    token = TokenMarketData(
        address=MINT,
        symbol="TEST",
        name="Test Utility",
        market_cap_usd=75_000,
        liquidity_usd=25_000,
        volume_24h_usd=150_000,
        price_usd=0.001,
        holders=500,
        holder_growth_24h_pct=20,
        buy_count_24h=80,
        sell_count_24h=20,
        volume_change_24h_pct=50,
        price_change_24h_pct=20,
        token_age_hours=72,
        top_holder_concentration_pct=20,
        creator_holding_pct=5,
    )
    security = SecurityData(
        holders=500,
        top_holder_concentration_pct=20,
        mint_authority_active=False,
        freeze_authority_active=False,
        risk_score=5,
        risk_level="LOW",
        raw={},
    )
    return CollectedToken(token=token, security=security, profile={})


def make_evidence() -> CandidateEvidence:
    return CandidateEvidence(
        utility=UtilityEvidence(
            has_real_use_case=True,
            product_exists=True,
            token_is_used_by_product=True,
            active_development=True,
            evidence_urls=["https://example.com"],
        ),
        risk=RiskAssessment(
            rug_pull_risk=5,
            holder_concentration_risk=5,
            contract_risk=5,
            liquidity_risk=5,
            creator_wallet_risk=5,
        ),
        why_now="Verified utility with strong live liquidity, volume, and buy pressure.",
        confidence=95,
        catalyst_score=10,
        invalidation_conditions=("Material liquidity loss",),
    )


class FakeCollector:
    def collect(self):
        return [make_candidate()]


class FakeEvidenceProvider:
    def enrich(self, candidate):
        return make_evidence()


@dataclass
class FakeTransport:
    alerts: list = None

    def __post_init__(self):
        self.alerts = [] if self.alerts is None else self.alerts

    def send(self, alert):
        self.alerts.append(alert)
        return {"ok": True}


class RecentlyNotifiedStore:
    def __init__(self):
        self.records = []

    def append(self, record):
        self.records.append(record)

    def was_recently_notified(self, contract_address, *, since: datetime):
        return contract_address == MINT and since <= datetime.now(timezone.utc)


def test_live_runner_sends_only_qualified_alert_with_exact_mint():
    transport = FakeTransport()
    runner = LiveScannerRunner(FakeCollector(), FakeEvidenceProvider(), transport=transport)

    results = runner.run_once()

    assert len(results) == 1
    result = results[0]
    assert result.pipeline is not None
    assert result.pipeline.decision.decision is Decision.EARLY_BUY
    assert result.notified is True
    assert result.alert_type == "EARLY_BUY"
    assert len(transport.alerts) == 1
    assert transport.alerts[0].contract_address == MINT
    assert f"Contract: {MINT}" in transport.alerts[0].text
    assert "Decision: EARLY_BUY" in transport.alerts[0].text


def test_live_runner_suppresses_recent_duplicate_alert():
    transport = FakeTransport()
    store = RecentlyNotifiedStore()
    runner = LiveScannerRunner(
        FakeCollector(),
        FakeEvidenceProvider(),
        transport=transport,
        outcome_store=store,
    )

    results = runner.run_once()

    assert results[0].pipeline is not None
    assert results[0].pipeline.decision.decision is Decision.EARLY_BUY
    assert results[0].notified is False
    assert transport.alerts == []
    assert len(store.records) == 1
    assert store.records[0].notified is False


def test_live_runner_fail_closes_when_evidence_provider_fails():
    class FailingProvider:
        def enrich(self, candidate):
            raise RuntimeError("verification unavailable")

    transport = FakeTransport()
    runner = LiveScannerRunner(FakeCollector(), FailingProvider(), transport=transport)

    results = runner.run_once()

    assert results[0].pipeline is None
    assert results[0].notified is False
    assert results[0].error == "verification unavailable"
    assert transport.alerts == []


def test_live_runner_never_notifies_non_actionable_result():
    class WeakProvider:
        def enrich(self, candidate):
            evidence = make_evidence()
            return CandidateEvidence(
                utility=evidence.utility,
                risk=evidence.risk,
                why_now=evidence.why_now,
                catalyst_score=0,
                confidence=60,
            )

    transport = FakeTransport()
    runner = LiveScannerRunner(FakeCollector(), WeakProvider(), transport=transport)

    results = runner.run_once()

    assert results[0].pipeline is not None
    assert results[0].pipeline.decision.decision is Decision.WAIT
    assert results[0].notified is False
    assert transport.alerts == []
