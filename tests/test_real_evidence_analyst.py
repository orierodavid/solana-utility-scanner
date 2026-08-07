"""Tests for the provider-backed evidence/analyst stage."""

from datetime import datetime, timezone

import pytest

from src.analyst import EvidenceFetchError, EvidenceResponse, RealEvidenceAnalyst
from src.collector import CollectedToken, SecurityData
from src.models import TokenMarketData


MINT = "So11111111111111111111111111111111111111112"


class FakeEvidenceClient:
    def __init__(self, website_text: str | None = None, github_pushed_at: str | None = None):
        self.website_text = website_text
        self.github_pushed_at = github_pushed_at

    def get(self, url: str, *, headers=None):
        if self.website_text is None:
            raise EvidenceFetchError("website unavailable")
        return EvidenceResponse(
            url=url,
            status_code=200,
            text=self.website_text,
            content_type="text/html",
            observed_at=datetime.now(timezone.utc),
        )

    def get_json(self, url: str, *, headers=None):
        return {
            "full_name": "example/project",
            "pushed_at": self.github_pushed_at,
        }


def make_candidate(*, profile=True, security=True, creator=5.0):
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
        creator_holding_pct=creator,
    )
    sec = SecurityData(
        holders=500,
        top_holder_concentration_pct=20,
        mint_authority_active=False,
        freeze_authority_active=False,
        risk_score=5,
        risk_level="LOW",
        raw={},
    ) if security else None
    return CollectedToken(
        token=token,
        security=sec,
        profile=(
            {
                "links": [
                    {"type": "website", "url": "https://project.example"},
                    {"type": "github", "url": "https://github.com/example/project"},
                ]
            }
            if profile else {}
        ),
    )


def test_real_evidence_analyst_verifies_utility_development_and_live_signals():
    website = (
        "<html><title>Test Utility Platform</title>"
        "<body>Our application is a live marketplace. The TEST token is used "
        "to pay platform fees and access premium services. Utility token rewards "
        "are active.</body></html>"
    )
    client = FakeEvidenceClient(website, "2026-08-06T12:00:00Z")
    result = RealEvidenceAnalyst(client).enrich(make_candidate())

    assert result.utility.verified is True
    assert result.utility.product_exists is True
    assert result.utility.token_is_used_by_product is True
    assert result.utility.active_development is True
    assert result.catalyst_score == 10.0
    assert result.confidence == 100.0
    assert "Contract" not in result.why_now
    assert "Verified utility evidence" in result.why_now
    assert result.risk.hard_filter_failed is False


def test_real_evidence_analyst_rejects_missing_security_data():
    client = FakeEvidenceClient("<body>TEST token platform utility</body>", "2026-08-06T12:00:00Z")
    with pytest.raises(EvidenceFetchError, match="Security evidence"):
        RealEvidenceAnalyst(client).enrich(make_candidate(security=False))


def test_real_evidence_analyst_rejects_unverified_token_usage():
    website = "<body>Our application is a marketplace. No token is used here.</body>"
    client = FakeEvidenceClient(website, "2026-08-06T12:00:00Z")
    with pytest.raises(EvidenceFetchError, match="Utility evidence"):
        RealEvidenceAnalyst(client).enrich(make_candidate())


def test_real_evidence_analyst_fail_closes_active_mint_authority():
    website = "<body>TEST token platform utility pay fees</body>"
    client = FakeEvidenceClient(website, "2026-08-06T12:00:00Z")
    candidate = make_candidate()
    candidate = CollectedToken(
        token=candidate.token,
        security=SecurityData(
            holders=500,
            top_holder_concentration_pct=20,
            mint_authority_active=True,
            freeze_authority_active=False,
            risk_score=5,
            risk_level="LOW",
            raw={},
        ),
        profile=candidate.profile,
    )

    result = RealEvidenceAnalyst(client).enrich(candidate)

    assert result.risk.hard_filter_failed is True
    assert "Mint authority is active" in result.risk.reasons


def test_real_evidence_analyst_rejects_missing_project_website():
    client = FakeEvidenceClient("<body>TEST token platform utility pay fees</body>", "2026-08-06T12:00:00Z")
    with pytest.raises(EvidenceFetchError, match="No project website"):
        RealEvidenceAnalyst(client).enrich(make_candidate(profile=False))


def test_real_evidence_analyst_requires_recent_development():
    website = "<body>TEST token platform utility pay fees</body>"
    client = FakeEvidenceClient(website, "2020-01-01T12:00:00Z")
    with pytest.raises(EvidenceFetchError, match="Recent development"):
        RealEvidenceAnalyst(client).enrich(make_candidate())
