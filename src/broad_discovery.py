"""Broad two-lane discovery for very early Solana opportunities."""
from __future__ import annotations
from datetime import datetime,timezone
import json
from pathlib import Path
from .collector import CollectedToken,CollectorConfig,CollectorError,LiveSolanaCollector,_best_pair,_token_from_pair

class BroadLiveSolanaCollector(LiveSolanaCollector):
    """Discover the <$50K core plus exceptional early candidates above it.

    Discovery is deliberately wider than the alert gate. Utility is the
    primary thesis downstream; non-utility candidates can enter the secondary
    high-potential lane when market, momentum and risk evidence is strong.
    Monitored watchlist mints are re-added to the batch so they are rechecked
    even when they disappear from the newest discovery feeds.
    """
    def __init__(self,config=None,dex=None,rugcheck=None,watchlist_path=None):
        if config is None: config=CollectorConfig(min_market_cap_usd=1_000,max_market_cap_usd=150_000,min_liquidity_usd=2_500)
        super().__init__(config=config,dex=dex,rugcheck=rugcheck)
        self.watchlist_path=Path(watchlist_path or "data/watchlist.json")
    def _watchlist_entries(self):
        try:
            data=json.loads(self.watchlist_path.read_text(encoding="utf-8"))
            return list(data.values()) if isinstance(data,dict) else []
        except (OSError,ValueError): return []
    def collect(self)->list[CollectedToken]:
        limit=100;feeds=[]
        for path in ("/token-profiles/latest/v1","/token-boosts/latest/v1","/token-boosts/top/v1"):
            try:
                payload=self.dex._get_json(path)
                if isinstance(payload,list): feeds.extend(x for x in payload if isinstance(x,dict) and x.get("chainId")=="solana" and x.get("tokenAddress"))
            except CollectorError: continue
        profiles=[];seen=set()
        for p in feeds:
            mint=str(p["tokenAddress"])
            if mint not in seen: seen.add(mint);profiles.append(p)
            if len(profiles)>=limit: break
        # Re-evaluate monitored candidates even when they are absent from the
        # latest profiles/boost feeds. This is the continuous watch mechanism.
        for entry in self._watchlist_entries():
            mint=str(entry.get("contract_address") or "")
            if mint and mint not in seen and len(profiles)<limit+25:
                profile=entry.get("profile") if isinstance(entry.get("profile"),dict) else {"tokenAddress":mint,"chainId":"solana"}
                profile=dict(profile);profile.setdefault("tokenAddress",mint);profile.setdefault("chainId","solana");seen.add(mint);profiles.append(profile)
        mints=[str(p["tokenAddress"]) for p in profiles];pairs=[]
        for i in range(0,len(mints),30): pairs.extend(self.dex.token_pairs(mints[i:i+30]))
        now=datetime.now(timezone.utc);by_mint={str(p["tokenAddress"]):p for p in profiles};out=[]
        for mint in mints:
            pair=_best_pair(pairs,mint)
            if pair is None: continue
            token=_token_from_pair(pair,mint,now)
            if not self.config.min_market_cap_usd<=token.market_cap_usd<=self.config.max_market_cap_usd or token.liquidity_usd<self.config.min_liquidity_usd: continue
            sec=None
            try: sec=self.rugcheck.token_report(mint)
            except CollectorError: sec=None
            if sec: token=token.model_copy(update={"holders":sec.holders,"top_holder_concentration_pct":sec.top_holder_concentration_pct,"mint_authority_active":sec.mint_authority_active,"freeze_authority_active":sec.freeze_authority_active})
            out.append(CollectedToken(token,sec,by_mint.get(mint,{})))
        return out
