"""Structured AI and real-evidence analysis for Solana utility-token candidates.

The AI-facing layer below is evidence-only. The live evidence analyst adds a
provider-backed verification stage so the scanner does not have to invent
utility, development, catalyst, risk, or contract data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import ipaddress
import re
import socket
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlparse

import requests

from .collector import CollectedToken
from .live_pipeline import CandidateEvidence
from .models import RiskAssessment, ScoreBreakdown, TokenMarketData, UtilityEvidence


@dataclass(frozen=True)
class AnalysisRequest:
    """Evidence package supplied to an AI provider."""

    token: TokenMarketData
    utility: UtilityEvidence
    risk: RiskAssessment
    score: ScoreBreakdown

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "token": {
                "name": self.token.name,
                "symbol": self.token.symbol,
                "chain": self.token.chain,
                "contract_address": self.token.address,
                "market_cap_usd": self.token.market_cap_usd,
                "market_cap_zone": self.token.market_cap_zone.value,
                "liquidity_usd": self.token.liquidity_usd,
                "volume_24h_usd": self.token.volume_24h_usd,
                "holders": self.token.holders,
                "holder_growth_24h_pct": self.token.holder_growth_24h_pct,
                "volume_change_24h_pct": self.token.volume_change_24h_pct,
            },
            "utility": self.utility.model_dump(),
            "risk": self.risk.model_dump(),
            "score": {**self.score.model_dump(), "total": self.score.total},
        }


class Analyst:
    """Build deterministic analysis instructions and validate AI output."""

    SYSTEM_INSTRUCTION = (
        "Analyze only the supplied evidence. Never invent data, URLs, catalysts, "
        "wallet activity, or contract addresses. Preserve the exact contract_address "
        "from the evidence. Market cap is a discovery filter, not a standalone buy "
        "signal. Explain why now, key risks, and invalidation conditions. Return JSON."
    )

    def build_request(self, token: TokenMarketData, utility: UtilityEvidence, risk: RiskAssessment, score: ScoreBreakdown) -> AnalysisRequest:
        return AnalysisRequest(token=token, utility=utility, risk=risk, score=score)

    def build_messages(self, request: AnalysisRequest) -> list[dict[str, Any]]:
        return [
            {"role": "system", "content": self.SYSTEM_INSTRUCTION},
            {"role": "user", "content": {
                "task": "Produce a concise trade thesis for this validated candidate.",
                "required_fields": ["contract_address", "why_now", "key_evidence", "key_risks", "invalidation_conditions", "confidence"],
                "evidence": request.to_prompt_payload(),
            }},
        ]

    @staticmethod
    def validate_response(response: Mapping[str, Any], expected_contract_address: str) -> dict[str, Any]:
        required = ("contract_address", "why_now", "confidence")
        missing = [field for field in required if field not in response]
        if missing:
            raise ValueError(f"AI response missing required fields: {', '.join(missing)}")
        if response["contract_address"] != expected_contract_address:
            raise ValueError("AI returned a contract address different from the verified mint address")
        confidence = response["confidence"]
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 100:
            raise ValueError("AI confidence must be a number from 0 to 100")
        if not isinstance(response["why_now"], str) or not response["why_now"].strip():
            raise ValueError("AI why_now must be a non-empty string")
        return dict(response)


class EvidenceFetchError(RuntimeError):
    """Raised when a source cannot be safely fetched or verified."""


@dataclass(frozen=True)
class EvidenceResponse:
    url: str
    status_code: int
    text: str
    content_type: str = ""
    observed_at: datetime | None = None


class EvidenceHttpClient(Protocol):
    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> EvidenceResponse:
        ...

    def get_json(self, url: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        ...


class RequestsEvidenceClient:
    """Read-only HTTP client with SSRF protections for untrusted project URLs."""

    def __init__(self, session: requests.Session | None = None, timeout: float = 12.0) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise EvidenceFetchError("Evidence URL must be an http(s) URL with a hostname")
        host = parsed.hostname.lower().rstrip(".")
        if host in {"localhost", "localhost.localdomain"}:
            raise EvidenceFetchError("Local evidence hosts are not allowed")
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
        except OSError as exc:
            raise EvidenceFetchError(f"Could not resolve evidence host: {host}") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                raise EvidenceFetchError("Private or non-public evidence destination rejected")

    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> EvidenceResponse:
        self._validate_url(url)
        try:
            response = self.session.get(
                url,
                headers={"User-Agent": "solana-utility-scanner/1.0", **(headers or {})},
                timeout=self.timeout,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise EvidenceFetchError(f"Evidence request failed: {exc}") from exc
        return EvidenceResponse(
            url=str(response.url),
            status_code=response.status_code,
            text=response.text[:500_000],
            content_type=response.headers.get("content-type", ""),
            observed_at=datetime.now(timezone.utc),
        )

    def get_json(self, url: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        response = self.get(url, headers=headers)
        try:
            payload = requests.models.complexjson.loads(response.text)
        except ValueError as exc:
            raise EvidenceFetchError(f"Expected JSON from {url}") from exc
        if not isinstance(payload, dict):
            raise EvidenceFetchError(f"Expected JSON object from {url}")
        return payload


def _strip_markup(text: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _profile_urls(profile: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    websites: list[str] = []
    githubs: list[str] = []
    raw_links = profile.get("links")
    if isinstance(raw_links, list):
        for item in raw_links:
            if isinstance(item, Mapping):
                url = item.get("url") or item.get("href")
                kind = str(item.get("type") or item.get("label") or "").lower()
            else:
                url = item if isinstance(item, str) else None
                kind = ""
            if not isinstance(url, str):
                continue
            if "github.com" in url.lower() or "github" in kind:
                githubs.append(url)
            elif url.startswith(("http://", "https://")):
                websites.append(url)
    for key in ("url", "website", "websiteUrl"):
        value = profile.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            websites.append(value)
    return list(dict.fromkeys(websites)), list(dict.fromkeys(githubs))


def _github_repo_api(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    return f"https://api.github.com/repos/{owner}/{repo}"


class RealEvidenceAnalyst:
    """Resolve live candidates into evidence-backed decision inputs.

    Utility is considered verified only when a reachable project source shows
    a product/use case and explicitly connects the token symbol/mint to token
    utility language, while recent GitHub activity verifies development.
    Security authorities and concentration are independently assessed from the
    collector's security source. No missing field is converted into a bullish
    assumption.
    """

    def __init__(
        self,
        http: EvidenceHttpClient | None = None,
        *,
        development_days: int = 180,
    ) -> None:
        if development_days <= 0:
            raise ValueError("development_days must be positive")
        self.http = http or RequestsEvidenceClient()
        self.development_days = development_days

    def enrich(self, candidate: CollectedToken) -> CandidateEvidence:
        if candidate.security is None:
            raise EvidenceFetchError("Security evidence is unavailable")
        utility, source_urls, development_verified = self._utility_evidence(candidate)
        risk = self._risk_assessment(candidate)
        catalyst_score, catalyst_text = self._catalyst_evidence(candidate)
        why_now = self._why_now(candidate, catalyst_text)
        confidence = self._confidence(candidate, utility, risk, source_urls, development_verified)

        if not utility.verified:
            raise EvidenceFetchError("Utility evidence is not sufficiently verified")
        if confidence < 85.0:
            raise EvidenceFetchError(f"Evidence confidence {confidence:.2f}% is below 85%")
        if not why_now.strip():
            raise EvidenceFetchError("No evidence-backed why-now thesis was produced")

        return CandidateEvidence(
            utility=utility,
            risk=risk,
            why_now=why_now,
            catalyst_score=catalyst_score,
            confidence=confidence,
            invalidation_conditions=self._invalidation_conditions(candidate, risk),
        )

    def _utility_evidence(self, candidate: CollectedToken) -> tuple[UtilityEvidence, list[str], bool]:
        websites, githubs = _profile_urls(candidate.profile)
        if not websites:
            raise EvidenceFetchError("No project website was supplied by the live token profile")

        evidence_urls: list[str] = []
        pages: list[str] = []
        for url in websites[:3]:
            try:
                response = self.http.get(url)
            except EvidenceFetchError:
                continue
            if 200 <= response.status_code < 400:
                evidence_urls.append(response.url)
                pages.append(_strip_markup(response.text))
        if not pages:
            raise EvidenceFetchError("Project website could not be verified")

        page_text = " ".join(pages).lower()
        symbol = candidate.token.symbol.lower()
        mint = candidate.token.address.lower()
        product_terms = (
            "app", "application", "platform", "protocol", "marketplace", "dashboard",
            "software", "product", "service", "api", "infrastructure", "tool",
        )
        usage_terms = (
            "utility", "token", "pay", "payment", "fee", "access", "stake", "staking",
            "governance", "reward", "rewards", "redeem", "discount", "membership",
            "used by", "powered by", "required to",
        )
        product_exists = any(term in page_text for term in product_terms)
        token_mention = mint in page_text or re.search(rf"\b{re.escape(symbol)}\b", page_text) is not None
        token_usage = token_mention and any(term in page_text for term in usage_terms)
        has_real_use_case = product_exists and token_usage

        development_verified = False
        for github_url in githubs[:3]:
            repo_api = _github_repo_api(github_url)
            if not repo_api:
                continue
            try:
                repo = self.http.get_json(repo_api, headers={"Accept": "application/vnd.github+json"})
            except EvidenceFetchError:
                continue
            pushed = self._parse_date(repo.get("pushed_at"))
            if pushed and datetime.now(timezone.utc) - pushed <= timedelta(days=self.development_days):
                development_verified = True
                evidence_urls.append(github_url)
                break

        utility = UtilityEvidence(
            has_real_use_case=has_real_use_case,
            product_exists=product_exists,
            token_is_used_by_product=token_usage,
            active_development=development_verified,
            evidence_urls=list(dict.fromkeys(evidence_urls)),
            notes=(
                "Reachable project source verified; product/use-case language="
                f"{product_exists}; token-use evidence={token_usage}; recent GitHub activity="
                f"{development_verified}."
            ),
        )
        return utility, evidence_urls, development_verified

    @staticmethod
    def _parse_date(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None

    def _risk_assessment(self, candidate: CollectedToken) -> RiskAssessment:
        token = candidate.token
        security = candidate.security
        assert security is not None
        reasons: list[str] = []

        concentration = token.top_holder_concentration_pct
        concentration_risk = (
            100 if concentration is None else min(100, max(0, round(max(0.0, concentration - 15.0) * 3.0)))
        )
        liquidity_ratio = token.liquidity_usd / token.market_cap_usd if token.market_cap_usd else 0.0
        liquidity_risk = 80 if liquidity_ratio < 0.05 else 50 if liquidity_ratio < 0.10 else 25 if liquidity_ratio < 0.20 else 10
        creator = token.creator_holding_pct
        creator_risk = 100 if creator is None else min(100, max(0, round(creator * 4.0)))

        contract_risk = 0
        if security.mint_authority_active:
            contract_risk = max(contract_risk, 75)
            reasons.append("Mint authority is active")
        if security.freeze_authority_active:
            contract_risk = max(contract_risk, 85)
            reasons.append("Freeze authority is active")
        if concentration is None:
            reasons.append("Top-holder concentration is unavailable")
        elif concentration > 35:
            reasons.append(f"Top-holder concentration is {concentration:.1f}%")
        if creator is not None and creator > 15:
            reasons.append(f"Creator holding is {creator:.1f}%")

        hard_fail = (
            concentration is None
            or concentration > 35
            or (creator is not None and creator > 15)
            or security.mint_authority_active is True
            or security.freeze_authority_active is True
        )
        if hard_fail:
            reasons.insert(0, "Mandatory security gate failed")

        risk_level = (security.risk_level or "").upper()
        rug_risk = 70 if risk_level in {"HIGH", "DANGER", "CRITICAL"} else 20
        return RiskAssessment(
            rug_pull_risk=rug_risk,
            holder_concentration_risk=concentration_risk,
            contract_risk=contract_risk,
            liquidity_risk=liquidity_risk,
            creator_wallet_risk=creator_risk,
            hard_filter_failed=hard_fail,
            reasons=list(dict.fromkeys(reasons)),
        )

    @staticmethod
    def _catalyst_evidence(candidate: CollectedToken) -> tuple[float, str]:
        token = candidate.token
        signals: list[str] = []
        score = 0.0
        if token.price_change_24h_pct is not None and token.price_change_24h_pct >= 15:
            score += 3.0
            signals.append(f"24h price is up {token.price_change_24h_pct:.1f}%")
        if token.volume_change_24h_pct is not None and token.volume_change_24h_pct >= 20:
            score += 3.0
            signals.append(f"24h volume is up {token.volume_change_24h_pct:.1f}%")
        if token.holder_growth_24h_pct is not None and token.holder_growth_24h_pct >= 10:
            score += 2.0
            signals.append(f"holders are up {token.holder_growth_24h_pct:.1f}%")
        buys, sells = token.buy_count_24h, token.sell_count_24h
        if buys is not None and sells is not None and buys + sells > 0:
            pressure = buys / (buys + sells) * 100
            if pressure >= 58:
                score += 2.0
                signals.append(f"buy pressure is {pressure:.1f}%")
        return min(score, 10.0), "; ".join(signals) if signals else "No verified short-term catalyst signal"

    @staticmethod
    def _why_now(candidate: CollectedToken, catalyst_text: str) -> str:
        token = candidate.token
        facts = [
            f"Verified utility evidence exists for {token.name} (${token.symbol})",
            f"market cap is ${token.market_cap_usd:,.0f}",
            f"liquidity is ${token.liquidity_usd:,.0f}",
        ]
        if catalyst_text != "No verified short-term catalyst signal":
            facts.append(catalyst_text)
        return "; ".join(facts) + "."

    @staticmethod
    def _confidence(
        candidate: CollectedToken,
        utility: UtilityEvidence,
        risk: RiskAssessment,
        source_urls: Sequence[str],
        development_verified: bool,
    ) -> float:
        token = candidate.token
        checks = [
            bool(source_urls),
            utility.has_real_use_case,
            utility.product_exists,
            utility.token_is_used_by_product,
            utility.active_development,
            development_verified,
            token.market_cap_usd > 0,
            token.liquidity_usd > 0,
            token.volume_24h_usd > 0,
            token.price_usd > 0,
            token.holders is not None,
            token.top_holder_concentration_pct is not None,
            token.token_age_hours is not None,
            candidate.security is not None,
            not risk.hard_filter_failed,
        ]
        return round(sum(checks) / len(checks) * 100, 2)

    @staticmethod
    def _invalidation_conditions(candidate: CollectedToken, risk: RiskAssessment) -> tuple[str, ...]:
        token = candidate.token
        conditions = [
            "Utility evidence becomes unverifiable or the project/product stops using the token",
            "Security authorities become active or mandatory holder-risk limits are breached",
            f"Liquidity falls materially below the current ${token.liquidity_usd:,.0f} observation",
        ]
        if risk.hard_filter_failed:
            conditions.insert(0, "Current security hard filter is already failed; do not trade")
        return tuple(conditions)
