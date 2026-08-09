"""Real, source-backed evidence collection for live Solana candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import requests

from .collector import CollectedToken
from .models import RiskAssessment, UtilityEvidence

UTILITY_TERMS = (
    "utility", "used to", "use the token", "token is used", "powered by",
    "staking", "governance", "access", "payment", "fee", "discount",
    "rewards", "membership", "protocol", "platform", "marketplace",
    "infrastructure", "api", "terminal", "application",
)
PRODUCT_TERMS = (
    "app", "application", "platform", "product", "protocol", "dashboard",
    "marketplace", "mainnet", "testnet", "demo", "docs", "documentation",
)
PRODUCT_STRONG_TERMS = (
    "live product", "live platform", "live protocol", "live application",
    "public beta", "public testnet", "mainnet", "testnet", "dashboard",
    "documentation", "docs", "api", "sdk", "app", "application",
    "marketplace", "protocol",
)
TOKEN_FUNCTION_PATTERNS = (
    r"\b{symbol}\b.{0,100}\b(?:used|use|required|needed|pay|payment|access|stake|staking|govern|governance|redeem|redeemable|fee|fees|reward|rewards)\b",
    r"\b(?:used|use|required|needed|pay|payment|access|stake|staking|govern|governance|redeem|redeemable|fee|fees|reward|rewards)\b.{0,100}\b{symbol}\b",
)
SPECULATIVE_MEME_TERMS = (
    "meme coin", "memecoin", "meme token", "for the memes", "just for fun",
    "community meme", "viral meme", "internet meme", "culture coin",
    "culture token", "purely speculative", "speculation only", "no utility",
)
CATALYST_TERMS = (
    "launch", "launched", "release", "released", "integration", "integrated",
    "partnership", "partner", "listing", "mainnet", "testnet", "upgrade",
    "roadmap", "update", "version", "v2", "v3",
)
RISK_TERMS = {
    "mint": 25, "freeze": 25, "authority": 10, "blacklist": 20,
    "honeypot": 60, "rug": 60, "scam": 80, "bundled": 20,
    "sniper": 15, "concentration": 20,
}

class EvidenceError(RuntimeError):
    """Raised when live evidence cannot be established safely."""

class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.parts: list[str] = []; self._skip = 0
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}: self._skip += 1
    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._skip: self._skip -= 1
    def handle_data(self, data: str) -> None:
        if not self._skip:
            text = " ".join(data.split())
            if text: self.parts.append(text)

@dataclass(frozen=True)
class EvidenceDocument:
    url: str
    status_code: int
    text: str
    fetched_at: datetime
    content_type: str = ""
    @property
    def usable(self) -> bool:
        return self.status_code == 200 and len(self.text) >= 120

class WebEvidenceClient:
    def __init__(self, session: requests.Session | None = None, timeout: float = 8.0) -> None:
        self.session = session or requests.Session(); self.timeout = timeout
    def fetch(self, url: str) -> EvidenceDocument | None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc: return None
        try:
            response = self.session.get(url, headers={"User-Agent": "solana-utility-scanner/1.0", "Accept": "text/html,application/xhtml+xml"}, timeout=self.timeout, allow_redirects=True)
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                text = response.text[:2000] if response.ok else ""
            else:
                parser = _TextExtractor(); parser.feed(response.text[:500_000]); text = " ".join(parser.parts)
            return EvidenceDocument(url=response.url, status_code=response.status_code, text=text[:100_000], fetched_at=datetime.now(timezone.utc), content_type=content_type)
        except requests.RequestException:
            return None

class GitHubEvidenceClient:
    API = "https://api.github.com"
    def __init__(self, session: requests.Session | None = None, timeout: float = 8.0) -> None:
        self.session = session or requests.Session(); self.timeout = timeout
    def repository_activity(self, repo_url: str) -> tuple[str, int, int]:
        parsed = urlparse(repo_url); parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2 or parsed.netloc.lower() not in {"github.com", "www.github.com"}: return repo_url, 0, 0
        owner, repo = parts[0], parts[1].removesuffix(".git"); api_url = f"{self.API}/repos/{owner}/{repo}"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "solana-utility-scanner/1.0"}
        try:
            repo_response = self.session.get(api_url, headers=headers, timeout=self.timeout)
            if repo_response.status_code != 200: return f"https://github.com/{owner}/{repo}", 0, 0
            since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            commits = self.session.get(f"{api_url}/commits", headers=headers, params={"since": since.isoformat().replace("+00:00", "Z"), "per_page": 20}, timeout=self.timeout)
            issues = self.session.get(f"{api_url}/issues", headers=headers, params={"state": "all", "since": since.isoformat().replace("+00:00", "Z"), "per_page": 20}, timeout=self.timeout)
            commit_payload = commits.json() if commits.ok else []; issue_payload = issues.json() if issues.ok else []
            return f"https://github.com/{owner}/{repo}", len(commit_payload) if isinstance(commit_payload, list) else 0, len(issue_payload) if isinstance(issue_payload, list) else 0
        except (requests.RequestException, ValueError):
            return f"https://github.com/{owner}/{repo}", 0, 0

def _extract_urls(profile: Mapping[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ("url", "website"):
        value = profile.get(key)
        if isinstance(value, str): candidates.append(value)
    links = profile.get("links")
    if isinstance(links, Sequence) and not isinstance(links, (str, bytes)):
        for item in links:
            if isinstance(item, Mapping) and isinstance(item.get("url"), str):
                link_type = str(item.get("type") or item.get("label") or "").lower()
                if any(term in link_type for term in ("website", "docs", "documentation", "github", "whitepaper")): candidates.append(item["url"])
    info = profile.get("info")
    if isinstance(info, Mapping):
        websites = info.get("websites")
        if isinstance(websites, Sequence) and not isinstance(websites, (str, bytes)):
            for item in websites:
                if isinstance(item, Mapping) and isinstance(item.get("url"), str): candidates.append(item["url"])
    result: list[str] = []; seen: set[str] = set()
    for value in candidates:
        value = value.strip()
        if not value.startswith(("http://", "https://")): continue
        parsed = urlparse(value)
        if parsed.netloc and value not in seen: seen.add(value); result.append(value)
    return result[:6]

def _count_terms(text: str, terms: Sequence[str]) -> int:
    lowered = text.lower(); return sum(1 for term in terms if term in lowered)

def _has_token_function(text: str, symbol: str) -> bool:
    """Require explicit language connecting the token to a functional action."""
    escaped = re.escape(symbol.lower()); lowered = text.lower()
    # Do not use str.format here: the regex quantifier {0,100} is a valid
    # regex brace expression and would be interpreted as a format field.
    return any(re.search(pattern.replace("{symbol}", escaped), lowered) for pattern in TOKEN_FUNCTION_PATTERNS)

def _has_strong_product_evidence(text: str) -> bool:
    return _count_terms(text.lower(), PRODUCT_STRONG_TERMS) >= 2

def _has_speculative_meme_signal(text: str) -> bool:
    return _count_terms(text, SPECULATIVE_MEME_TERMS) >= 1

def _risk_from_security(candidate: CollectedToken) -> RiskAssessment:
    security = candidate.security; token = candidate.token; reasons: list[str] = []
    holder_risk = 0
    if token.top_holder_concentration_pct is None: holder_risk = 70; reasons.append("Top-holder concentration could not be independently verified")
    elif token.top_holder_concentration_pct > 35: holder_risk = 90; reasons.append(f"Top-holder concentration is {token.top_holder_concentration_pct:.1f}%")
    elif token.top_holder_concentration_pct > 25: holder_risk = 60; reasons.append(f"Top-holder concentration is elevated at {token.top_holder_concentration_pct:.1f}%")
    elif token.top_holder_concentration_pct > 15: holder_risk = 30
    ratio = token.liquidity_usd / max(token.market_cap_usd, 1.0); liquidity_risk = 0
    if ratio < 0.05: liquidity_risk = 85; reasons.append("Liquidity is very thin relative to market cap")
    elif ratio < 0.10: liquidity_risk = 60; reasons.append("Liquidity is thin relative to market cap")
    elif ratio < 0.20: liquidity_risk = 35
    contract_risk = 0
    if token.mint_authority_active is None or token.freeze_authority_active is None: contract_risk += 30; reasons.append("Token authority state is incomplete")
    else:
        if token.mint_authority_active: contract_risk += 35; reasons.append("Mint authority is active")
        if token.freeze_authority_active: contract_risk += 45; reasons.append("Freeze authority is active")
    rug_risk = 0; creator_risk = 0
    if security is None: rug_risk = 80; creator_risk = 70; reasons.append("Independent security report is unavailable")
    else:
        raw = security.raw; risk_items = raw.get("risks") if isinstance(raw, Mapping) else None
        if isinstance(risk_items, list):
            severities: list[int] = []
            for item in risk_items:
                if not isinstance(item, Mapping): continue
                text = " ".join(str(item.get(k, "")) for k in ("name", "description", "value", "level")).lower()
                for term, weight in RISK_TERMS.items():
                    if term in text: severities.append(weight); break
            rug_risk = min(100, max(severities, default=0))
            if rug_risk: reasons.append("Independent security data contains elevated risk findings")
    hard_fail = holder_risk >= 90 or liquidity_risk >= 85 or rug_risk >= 80 or contract_risk >= 80
    return RiskAssessment(rug_pull_risk=rug_risk, holder_concentration_risk=holder_risk, contract_risk=min(contract_risk, 100), liquidity_risk=liquidity_risk, creator_wallet_risk=creator_risk, hard_filter_failed=hard_fail, reasons=tuple(dict.fromkeys(reasons)))

class LiveEvidenceProvider:
    def __init__(self, web: WebEvidenceClient | None = None, github: GitHubEvidenceClient | None = None, *, max_documents: int = 4) -> None:
        self.web = web or WebEvidenceClient(); self.github = github or GitHubEvidenceClient(); self.max_documents = max(1, max_documents)
    def enrich(self, candidate: CollectedToken):
        from .live_pipeline import CandidateEvidence
        from .analyst import EvidenceAnalyst
        token = candidate.token; urls = _extract_urls(candidate.profile)
        documents = [doc for url in urls[: self.max_documents] if (doc := self.web.fetch(url)) is not None]
        usable = [doc for doc in documents if doc.usable]
        if not usable: raise EvidenceError("No usable first-party project evidence could be fetched")
        combined = " ".join(d.text for d in usable)
        exact_mint_mentions = combined.lower().count(token.address.lower())
        utility_hits = _count_terms(combined, UTILITY_TERMS); product_hits = _count_terms(combined, PRODUCT_TERMS)
        strong_product_hits = _count_terms(combined, PRODUCT_STRONG_TERMS); catalyst_hits = _count_terms(combined, CATALYST_TERMS)
        token_function_verified = _has_token_function(combined, token.symbol); speculative_meme = _has_speculative_meme_signal(combined); strong_product = _has_strong_product_evidence(combined)
        github_repos: list[str] = []; github_commits = 0; github_issues = 0
        for url in urls:
            if "github.com/" in url.lower():
                repo, commits, issues = self.github.repository_activity(url); github_repos.append(repo); github_commits += commits; github_issues += issues
        has_real_use_case = utility_hits >= 2 and product_hits >= 1 and strong_product
        product_exists = strong_product
        token_is_used = token_function_verified or (exact_mint_mentions >= 1 and _count_terms(combined, ("token", "mint", "contract")) >= 1 and utility_hits >= 3)
        active_development = github_commits > 0 or github_issues > 0 or catalyst_hits >= 2
        if speculative_meme and not (has_real_use_case and product_exists and token_is_used and active_development):
            raise EvidenceError("Project appears primarily meme/speculative and lacks independently verified token utility")
        if not has_real_use_case or not product_exists or not token_is_used:
            raise EvidenceError("Project utility could not be verified from source-backed evidence")
        risk = _risk_from_security(candidate)
        evidence_confidence = round(sum((bool(usable), exact_mint_mentions > 0, token_function_verified, has_real_use_case, strong_product, active_development, candidate.security is not None, token.top_holder_concentration_pct is not None, token.holders is not None)) / 9 * 100, 2)
        catalyst_score = min(10.0, catalyst_hits * 1.5 + min(github_commits, 3) + min(github_issues, 2) * 0.5)
        utility = UtilityEvidence(has_real_use_case=has_real_use_case, product_exists=product_exists, token_is_used_by_product=token_is_used, active_development=active_development, evidence_urls=tuple(d.url for d in usable), notes=f"Verified from {len(usable)} source documents; {exact_mint_mentions} exact mint mentions; {utility_hits} utility terms; {strong_product_hits} strong product signals; explicit token function={token_function_verified}; {len(github_repos)} linked GitHub repositories.")
        finding = EvidenceAnalyst().analyze(candidate, utility, risk, catalyst_signals=(f"{catalyst_hits} catalyst/development signals found in source material",) if catalyst_hits else ())
        invalidations = ("Liquidity falls materially below the current screening level.", "Top-holder concentration rises above the hard risk threshold.", "Security evidence identifies a material rug, authority, or wallet risk.", "Momentum or volume deteriorates enough to invalidate the current setup.")
        return CandidateEvidence(utility=utility, risk=risk, why_now=finding.thesis, catalyst_score=catalyst_score, confidence=min(evidence_confidence, finding.confidence), invalidation_conditions=invalidations)
