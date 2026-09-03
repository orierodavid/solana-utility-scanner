"""Regression coverage for evidence outages in the live scanner."""

from src.collector import CollectedToken, SecurityData
from src.evidence import EvidenceError
from src.live_pipeline import LiveScannerRunner
from src.models import TokenMarketData


class MemoryWatchlist:
    def __init__(self):
        self.items = {}

    def entries(self):
        return list(self.items.values())

    def upsert(self, address, **kwargs):
        self.items[address] = {"contract_address": address, **kwargs}

    def remove(self, address):
        self.items.pop(address, None)


class MemoryOutcomes:
    def append(self, record):
        pass

    def was_recently_notified(self, contract_address, *, since, alert_type=None):
        return False

    def latest_snapshot(self, contract_address):
        return None


class Collector:
    def collect(self):
        token = TokenMarketData(
            address="So11111111111111111111111111111111111111112",
            symbol="TEST",
            name="Test Candidate",
            market_cap_usd=55_000,
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
            mint_authority_active=False,
            freeze_authority_active=False,
        )
        security = SecurityData(
            holders=500,
            top_holder_concentration_pct=20,
            mint_authority_active=False,
            freeze_authority_active=False,
            risk_score=5,
            risk_level="LOW",
            raw={"risks": []},
        )
        return [CollectedToken(token=token, security=security, profile={})]


class EvidenceOutage:
    def enrich(self, candidate):
        raise EvidenceError("No usable first-party project evidence could be fetched")


def test_evidence_outage_does_not_drop_candidate_from_evaluation():
    runner = LiveScannerRunner(
        Collector(),
        EvidenceOutage(),
        outcome_store=MemoryOutcomes(),
        watchlist_store=MemoryWatchlist(),
    )

    results = runner.run_once()

    assert len(results) == 1
    assert results[0].pipeline is not None
    assert results[0].pipeline.decision.lane == "HIGH_POTENTIAL"
    assert results[0].pipeline.decision.decision.value in {
        "BUY_CANDIDATE",
        "WAIT",
        "NO_TRADE",
        "CONFIRMATION",
        "MISSED_ENTRY",
    }
    assert results[0].error is None
