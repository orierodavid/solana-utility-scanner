"""Tests for source-backed evidence and analyst synthesis."""

from dataclasses import dataclass

from src.collector import CollectedToken, SecurityData
from src.evidence import EvidenceDocument, EvidenceError, LiveEvidenceProvider
from src.models import TokenMarketData


MINT = "So11111111111111111111111111111111111111112"


def candidate() -> CollectedToken:
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
    return CollectedToken(
        token=token,
        security=security,
        profile={
            "url": "https://project.example",
            "links": [{"type": "github", "url": "https://github.com/example/project"}],
        },
    )


@dataclass
class FakeWeb:
    text: str

    def fetch(self, url: str):
        return EvidenceDocument(
            url=url,
            status_code=200,
            text=self.text,
            fetched_at=candidate().token.observed_at,
            content_type="text/html",
        )


class FakeGitHub:
    def repository_activity(self, url: str):
        return url, 3, 1


GOOD_TEXT = (
    "Test Utility is a utility platform and application. The TEST token is used to pay fees, "
    "access the platform, and receive rewards. The product is a live protocol with documentation "
    "and a dashboard. The team released an integration update and roadmap upgrade this week. "
    f"Verified Solana token mint: {MINT}. "
) * 2


def test_real_evidence_provider_verifies_utility_and_development():
    provider = LiveEvidenceProvider(web=FakeWeb(GOOD_TEXT), github=FakeGitHub())

    evidence = provider.enrich(candidate())

    assert evidence.utility.verified is True
    assert evidence.utility.product_exists is True
    assert evidence.utility.token_is_used_by_product is True
    assert evidence.utility.active_development is True
    assert evidence.utility.evidence_urls
    assert evidence.confidence >= 85
    assert evidence.catalyst_score > 0
    assert "Contract" not in evidence.why_now


def test_real_evidence_provider_rejects_superficial_meme_project():
    meme_text = (
        "Only Memes Over Finance is a memecoin and community meme built for fun and viral culture. "
        "The meme token has a roadmap, community, social links, a platform, and an application coming soon. "
        "Buy the token, hold the token, and join the community. This is a meme coin first and foremost. "
    ) * 3
    provider = LiveEvidenceProvider(web=FakeWeb(meme_text), github=FakeGitHub())

    try:
        provider.enrich(candidate())
    except EvidenceError as exc:
        assert "meme" in str(exc).lower() or "utility" in str(exc).lower()
    else:
        raise AssertionError("Provider must reject a superficial meme/speculative project")


def test_real_evidence_provider_rejects_generic_utility_claim_without_token_function():
    generic_text = (
        "Test Utility is a utility platform and application. The platform has documentation and a dashboard. "
        "The project has a roadmap, community rewards, partnerships and active development. "
        "However, the TEST token has no documented function in the product. "
    ) * 3
    provider = LiveEvidenceProvider(web=FakeWeb(generic_text), github=FakeGitHub())

    try:
        provider.enrich(candidate())
    except EvidenceError as exc:
        assert "utility" in str(exc).lower()
    else:
        raise AssertionError("Provider must require an explicit functional token relationship")


def test_real_evidence_provider_fails_closed_without_utility_proof():
    weak_text = "A token community page with a price chart and social links, but no product or token utility documentation. " * 3
    provider = LiveEvidenceProvider(web=FakeWeb(weak_text), github=FakeGitHub())

    try:
        provider.enrich(candidate())
    except EvidenceError as exc:
        assert "utility" in str(exc).lower()
    else:
        raise AssertionError("Provider must fail closed when utility cannot be verified")


def test_real_evidence_provider_marks_thin_liquidity_as_high_risk():
    item = candidate()
    thin_token = item.token.model_copy(update={"liquidity_usd": 3_000})
    thin_candidate = CollectedToken(token=thin_token, security=item.security, profile=item.profile)
    provider = LiveEvidenceProvider(web=FakeWeb(GOOD_TEXT), github=FakeGitHub())

    evidence = provider.enrich(thin_candidate)

    assert evidence.risk.liquidity_risk >= 85
    assert evidence.risk.hard_filter_failed is True
