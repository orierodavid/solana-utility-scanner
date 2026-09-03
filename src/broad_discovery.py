"""Broader discovery layer kept separate from the trade-entry strategy."""
from __future__ import annotations
from datetime import datetime,timezone
from .collector import CollectedToken,CollectorConfig,CollectorError,LiveSolanaCollector,_best_pair,_token_from_pair
class BroadLiveSolanaCollector(LiveSolanaCollector):
    """Discover broadly; downstream decision logic still controls alerts."""
    def __init__(self,config=None,dex=None,rugcheck=None):
        if config is None: config=CollectorConfig(min_market_cap_usd=10_000,max_market_cap_usd=2_000_000,min_liquidity_usd=10_000)
        super().__init__(config=config,dex=dex,rugcheck=rugcheck)
    def collect(self)->list[CollectedToken]:
        limit=60; feeds=[]
        for path in ("/token-profiles/latest/v1","/token-boosts/latest/v1","/token-boosts/top/v1"):
            try:
                payload=self.dex._get_json(path)
                if isinstance(payload,list): feeds.extend(x for x in payload if isinstance(x,dict) and x.get("chainId")=="solana" and x.get("tokenAddress"))
            except CollectorError: continue
        profiles=[]; seen=set()
        for p in feeds:
            mint=str(p["tokenAddress"])
            if mint not in seen: seen.add(mint); profiles.append(p)
            if len(profiles)>=limit: break
        mints=[str(p["tokenAddress"]) for p in profiles]; pairs=[]
        for i in range(0,len(mints),30): pairs.extend(self.dex.token_pairs(mints[i:i+30]))
        now=datetime.now(timezone.utc); by_mint={str(p["tokenAddress"]):p for p in profiles}; out=[]
        for mint in mints:
            pair=_best_pair(pairs,mint)
            if pair is None: continue
            token=_token_from_pair(pair,mint,now)
            if not self.config.min_market_cap_usd<=token.market_cap_usd<=self.config.max_market_cap_usd or token.liquidity_usd<self.config.min_liquidity_usd: continue
            sec=None
            try: sec=self.rugcheck.token_report(mint)
            except CollectorError:
                if self.config.require_security_data: continue
            if sec: token=token.model_copy(update={"holders":sec.holders,"top_holder_concentration_pct":sec.top_holder_concentration_pct,"mint_authority_active":sec.mint_authority_active,"freeze_authority_active":sec.freeze_authority_active})
            out.append(CollectedToken(token,sec,by_mint.get(mint,{})))
        return out
