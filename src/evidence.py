"""Real, source-backed evidence collection for live Solana candidates."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from typing import Any, Mapping, Sequence
from urllib.parse import urljoin, urlparse
import requests
from .collector import CollectedToken
from .models import RiskAssessment, UtilityEvidence

UTILITY_TERMS=("utility","used to","use the token","token is used","powered by","staking","governance","access","payment","fee","discount","rewards","membership","protocol","platform","marketplace","infrastructure","api","terminal","application")
PRODUCT_TERMS=("app","application","platform","product","protocol","dashboard","marketplace","mainnet","testnet","demo","docs","documentation")
PRODUCT_STRONG_TERMS=("live product","live platform","live protocol","live application","public beta","public testnet","mainnet","testnet","dashboard","documentation","docs","api","sdk","app","application","marketplace","protocol")
TOKEN_FUNCTION_ACTIONS=r"(?:used|use|required|needed|pay|payment|access|stake|staking|govern|governance|redeem|redeemable|fee|fees|reward|rewards)"
SPECULATIVE_MEME_TERMS=("meme coin","memecoin","meme token","for the memes","just for fun","community meme","viral meme","internet meme","culture coin","culture token","purely speculative","speculation only","no utility")
CATALYST_TERMS=("launch","launched","release","released","integration","integrated","partnership","partner","listing","mainnet","testnet","upgrade","roadmap","update","version","v2","v3")
EVIDENCE_LINK_TERMS=("docs","documentation","github","whitepaper","litepaper","paper","app","application","platform","protocol","product","api","sdk","roadmap")
RISK_TERMS={"mint":25,"freeze":25,"authority":10,"blacklist":20,"honeypot":60,"rug":60,"scam":80,"bundled":20,"sniper":15,"concentration":20}

class EvidenceError(RuntimeError): pass

class _TextExtractor(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]
    def handle_starttag(self,tag,attrs): pass
    def handle_endtag(self,tag): pass
    def handle_data(self,data):
        text=" ".join(data.split())
        if text:self.parts.append(text)

@dataclass(frozen=True)
class EvidenceDocument:
    url:str; status_code:int; text:str; fetched_at:datetime; content_type:str=""; links:tuple[str,...]=()
    @property
    def usable(self): return self.status_code==200 and len(self.text)>=120

class WebEvidenceClient:
    def __init__(self,session=None,timeout:float=8.0): self.session=session or requests.Session(); self.timeout=timeout
    def fetch(self,url):
        parsed=urlparse(url)
        if parsed.scheme not in {"http","https"} or not parsed.netloc:return None
        try:
            r=self.session.get(url,headers={"User-Agent":"solana-utility-scanner/1.0","Accept":"text/html,application/xhtml+xml"},timeout=self.timeout,allow_redirects=True)
            ct=r.headers.get("content-type","")
            raw=r.text[:500000] if r.ok else ""
            links=[]
            if "text/html" in ct or "application/xhtml+xml" in ct:
                p=_TextExtractor(); p.feed(raw); text=" ".join(p.parts)
                for href,label in re.findall(r'<a[^>]+href=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>',raw,re.I|re.S):
                    clean=re.sub(r"<[^>]+>"," ",label); clean=" ".join(clean.split()).lower()
                    absolute=urljoin(r.url,href)
                    if urlparse(absolute).scheme in {"http","https"} and (any(term in clean for term in EVIDENCE_LINK_TERMS) or any(term in absolute.lower() for term in EVIDENCE_LINK_TERMS)):
                        links.append(absolute)
            else: text=raw[:2000]
            return EvidenceDocument(r.url,r.status_code,text[:100000],datetime.now(timezone.utc),ct,tuple(dict.fromkeys(links))[:12])
        except requests.RequestException:return None

class GitHubEvidenceClient:
    API="https://api.github.com"
    def __init__(self,session=None,timeout:float=8.0): self.session=session or requests.Session(); self.timeout=timeout
    def repository_activity(self,repo_url):
        parsed=urlparse(repo_url); parts=[p for p in parsed.path.split("/") if p]
        if len(parts)<2 or parsed.netloc.lower() not in {"github.com","www.github.com"}: return repo_url,0,0
        owner,repo=parts[0],parts[1].removesuffix(".git"); api=f"{self.API}/repos/{owner}/{repo}"
        h={"Accept":"application/vnd.github+json","User-Agent":"solana-utility-scanner/1.0"}
        try:
            rr=self.session.get(api,headers=h,timeout=self.timeout)
            if rr.status_code!=200:return f"https://github.com/{owner}/{repo}",0,0
            since=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat().replace("+00:00","Z")
            c=self.session.get(f"{api}/commits",headers=h,params={"since":since,"per_page":20},timeout=self.timeout)
            i=self.session.get(f"{api}/issues",headers=h,params={"state":"all","since":since,"per_page":20},timeout=self.timeout)
            cp=c.json() if c.ok else []; ip=i.json() if i.ok else []
            return f"https://github.com/{owner}/{repo}",len(cp) if isinstance(cp,list) else 0,len(ip) if isinstance(ip,list) else 0
        except (requests.RequestException,ValueError): return f"https://github.com/{owner}/{repo}",0,0

def _extract_urls(profile:Mapping[str,Any]):
    candidates=[]
    for key in ("url","website"):
        v=profile.get(key)
        if isinstance(v,str):candidates.append(v)
    links=profile.get("links")
    if isinstance(links,Sequence) and not isinstance(links,(str,bytes)):
        for item in links:
            if isinstance(item,Mapping) and isinstance(item.get("url"),str):
                typ=str(item.get("type") or item.get("label") or "").lower()
                if any(x in typ for x in ("website","docs","documentation","github","whitepaper")):candidates.append(item["url"])
    info=profile.get("info")
    if isinstance(info,Mapping):
        ws=info.get("websites")
        if isinstance(ws,Sequence) and not isinstance(ws,(str,bytes)):
            for item in ws:
                if isinstance(item,Mapping) and isinstance(item.get("url"),str):candidates.append(item["url"])
    out=[]; seen=set()
    for v in candidates:
        v=v.strip()
        if v.startswith(("http://","https://")) and urlparse(v).netloc and v not in seen:seen.add(v);out.append(v)
    return out[:8]

def _count_terms(text,terms): return sum(1 for t in terms if t in text.lower())

def _has_token_function(text,symbol):
    s=re.escape(symbol.lower())
    sentences=re.split(r"(?<=[.!?])\s+|[\n\r]+",text.lower())
    token=rf"\b{s}\b"; action=rf"\b{TOKEN_FUNCTION_ACTIONS}\b"
    return any((re.search(token,sent) and re.search(action,sent)) for sent in sentences)

def _has_strong_product_evidence(text): return _count_terms(text,PRODUCT_STRONG_TERMS)>=2
def _has_speculative_meme_signal(text): return _count_terms(text,SPECULATIVE_MEME_TERMS)>=1

def _risk_from_security(candidate):
    security=candidate.security; token=candidate.token; reasons=[]
    hc=token.top_holder_concentration_pct
    holder=70 if hc is None else 90 if hc>35 else 60 if hc>25 else 30 if hc>15 else 0
    if hc is None:reasons.append("Top-holder concentration could not be independently verified")
    elif hc>35:reasons.append(f"Top-holder concentration is {hc:.1f}%")
    elif hc>25:reasons.append(f"Top-holder concentration is elevated at {hc:.1f}%")
    ratio=token.liquidity_usd/max(token.market_cap_usd,1.0); liq=85 if ratio<.05 else 60 if ratio<.10 else 35 if ratio<.20 else 0
    if liq>=60:reasons.append("Liquidity is thin relative to market cap")
    contract=0
    if token.mint_authority_active is None or token.freeze_authority_active is None:contract=30;reasons.append("Token authority state is incomplete")
    else:
        if token.mint_authority_active:contract+=35;reasons.append("Mint authority is active")
        if token.freeze_authority_active:contract+=45;reasons.append("Freeze authority is active")
    rug=0;creator=0
    if security is None:rug=80;creator=70;reasons.append("Independent security report is unavailable")
    else:
        raw=security.raw; items=raw.get("risks") if isinstance(raw,Mapping) else None
        if isinstance(items,list):
            vals=[]
            for item in items:
                if isinstance(item,Mapping):
                    txt=" ".join(str(item.get(k,"")) for k in ("name","description","value","level")).lower()
                    for term,w in RISK_TERMS.items():
                        if term in txt:vals.append(w);break
            rug=min(100,max(vals,default=0))
            if rug:reasons.append("Independent security data contains elevated risk findings")
    return RiskAssessment(rug_pull_risk=rug,holder_concentration_risk=holder,contract_risk=min(contract,100),liquidity_risk=liq,creator_wallet_risk=creator,hard_filter_failed=holder>=90 or liq>=85 or rug>=80 or contract>=80,reasons=tuple(dict.fromkeys(reasons)))

class LiveEvidenceProvider:
    def __init__(self,web=None,github=None,*,max_documents=8):self.web=web or WebEvidenceClient();self.github=github or GitHubEvidenceClient();self.max_documents=max(1,max_documents)
    def enrich(self,candidate):
        from .live_pipeline import CandidateEvidence
        from .analyst import EvidenceAnalyst
        token=candidate.token;seed_urls=_extract_urls(candidate.profile)
        queue=list(seed_urls);seen=set();documents=[]
        while queue and len(documents)<self.max_documents:
            url=queue.pop(0)
            if url in seen:continue
            seen.add(url)
            doc=self.web.fetch(url)
            if doc is None:continue
            documents.append(doc)
            for linked in doc.links:
                if linked not in seen and linked not in queue and len(queue)<20:queue.append(linked)
        usable=[d for d in documents if d.usable]
        if not usable:raise EvidenceError("No usable first-party project evidence could be fetched")
        combined=" ".join(d.text for d in usable); exact=combined.lower().count(token.address.lower())
        utility_hits=_count_terms(combined,UTILITY_TERMS);product_hits=_count_terms(combined,PRODUCT_TERMS);strong_hits=_count_terms(combined,PRODUCT_STRONG_TERMS);catalyst_hits=_count_terms(combined,CATALYST_TERMS)
        token_function=_has_token_function(combined,token.symbol);meme=_has_speculative_meme_signal(combined);strong_product=_has_strong_product_evidence(combined)
        repos=[];commits=issues=0
        github_urls=list(seed_urls)
        for doc in usable:github_urls.extend(doc.links)
        for url in dict.fromkeys(github_urls):
            if "github.com/" in url.lower():
                repo,c,i=self.github.repository_activity(url);repos.append(repo);commits+=c;issues+=i
        has_real=utility_hits>=2 and product_hits>=1 and strong_product; product_exists=strong_product
        token_used=token_function or (exact>=1 and _count_terms(combined,("token","mint","contract"))>=1 and utility_hits>=3)
        active=commits>0 or issues>0 or catalyst_hits>=2
        if meme and not (has_real and product_exists and token_used and active):raise EvidenceError("Project appears primarily meme/speculative and lacks independently verified token utility")
        if not has_real or not product_exists or not token_used:raise EvidenceError("Project utility could not be verified from source-backed evidence")
        risk=_risk_from_security(candidate)
        confidence=round(sum((bool(usable),exact>0,token_function,has_real,strong_product,active,candidate.security is not None,token.top_holder_concentration_pct is not None,token.holders is not None))/9*100,2)
        catalyst=min(10.0,catalyst_hits*1.5+min(commits,3)+min(issues,2)*.5)
        utility=UtilityEvidence(has_real_use_case=has_real,product_exists=product_exists,token_is_used_by_product=token_used,active_development=active,evidence_urls=tuple(d.url for d in usable),notes=f"Verified from {len(usable)} source documents; {exact} exact mint mentions; {utility_hits} utility terms; {strong_hits} strong product signals; explicit token function={token_function}; {len(repos)} linked GitHub repositories.")
        finding=EvidenceAnalyst().analyze(candidate,utility,risk,catalyst_signals=(f"{catalyst_hits} catalyst/development signals found in source material",) if catalyst_hits else ())
        invalid=("Liquidity falls materially below the current screening level.","Top-holder concentration rises above the hard risk threshold.","Security evidence identifies a material rug, authority, or wallet risk.","Momentum or volume deteriorates enough to invalidate the current setup.")
        return CandidateEvidence(utility=utility,risk=risk,why_now=finding.thesis,catalyst_score=catalyst,confidence=min(confidence,finding.confidence),invalidation_conditions=invalid)
