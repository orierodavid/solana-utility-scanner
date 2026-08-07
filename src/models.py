"""Core data models for the Solana utility-token scanner."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_SOLANA_BASE58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]+$")


class Decision(str, Enum):
    BUY_CANDIDATE = "BUY_CANDIDATE"
    WAIT = "WAIT"
    NO_TRADE = "NO_TRADE"


class MarketCapZone(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    OUTSIDE = "OUTSIDE"


class TokenMarketData(BaseModel):
    """Observed/collected data for one Solana token.

    ``address`` is the exact Solana token mint address supplied by the data
    collector. It must never be inferred from a token symbol or name.
    """

    model_config = ConfigDict(extra="forbid")

    address: str = Field(min_length=32, max_length=44)
    symbol: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=120)
    chain: str = "solana"
    market_cap_usd: float = Field(ge=0)
    liquidity_usd: float = Field(ge=0)
    volume_24h_usd: float = Field(ge=0)
    price_usd: float = Field(ge=0)
    holders: Optional[int] = Field(default=None, ge=0)
    holder_growth_24h_pct: Optional[float] = None
    buy_count_24h: Optional[int] = Field(default=None, ge=0)
    sell_count_24h: Optional[int] = Field(default=None, ge=0)
    volume_change_24h_pct: Optional[float] = None
    price_change_24h_pct: Optional[float] = None
    token_age_hours: Optional[float] = Field(default=None, ge=0)
    top_holder_concentration_pct: Optional[float] = Field(default=None, ge=0, le=100)
    creator_holding_pct: Optional[float] = Field(default=None, ge=0, le=100)
    mint_authority_active: Optional[bool] = None
    freeze_authority_active: Optional[bool] = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("address")
    @classmethod
    def validate_solana_mint_address(cls, value: str) -> str:
        # Solana addresses are Base58 strings and are normally 32 bytes,
        # represented as 32–44 Base58 characters. We intentionally do not
        # accept whitespace, symbols, URLs, or token tickers.
        if not _SOLANA_BASE58.fullmatch(value):
            raise ValueError("address must be a valid-looking Solana Base58 mint address")
        return value

    @field_validator("chain")
    @classmethod
    def solana_only(cls, value: str) -> str:
        if value.lower() != "solana":
            raise ValueError("Only Solana tokens are supported")
        return "solana"

    @model_validator(mode="after")
    def validate_market_data(self) -> "TokenMarketData":
        if self.market_cap_usd > 0 and self.liquidity_usd > self.market_cap_usd * 10:
            raise ValueError("Liquidity is implausibly high relative to market cap")
        return self

    @property
    def market_cap_zone(self) -> MarketCapZone:
        if 50_000 <= self.market_cap_usd <= 100_000:
            return MarketCapZone.PRIMARY
        if 100_000 < self.market_cap_usd <= 150_000:
            return MarketCapZone.SECONDARY
        return MarketCapZone.OUTSIDE


class UtilityEvidence(BaseModel):
    """Evidence used to establish genuine token utility."""

    model_config = ConfigDict(extra="forbid")

    has_real_use_case: bool
    product_exists: bool
    token_is_used_by_product: bool
    active_development: bool
    evidence_urls: list[str] = Field(default_factory=list)
    notes: str = ""

    @property
    def verified(self) -> bool:
        return self.has_real_use_case and self.product_exists and self.token_is_used_by_product


class RiskAssessment(BaseModel):
    """Risk findings independent of the opportunity score."""

    model_config = ConfigDict(extra="forbid")

    rug_pull_risk: int = Field(ge=0, le=100)
    holder_concentration_risk: int = Field(ge=0, le=100)
    contract_risk: int = Field(ge=0, le=100)
    liquidity_risk: int = Field(ge=0, le=100)
    creator_wallet_risk: int = Field(ge=0, le=100)
    hard_filter_failed: bool = False
    reasons: list[str] = Field(default_factory=list)

    @property
    def overall_risk(self) -> int:
        return round((self.rug_pull_risk + self.holder_concentration_risk + self.contract_risk + self.liquidity_risk + self.creator_wallet_risk) / 5)


class ScoreBreakdown(BaseModel):
    """Transparent 100-point opportunity score."""

    model_config = ConfigDict(extra="forbid")

    utility: float = Field(ge=0, le=20)
    market_structure: float = Field(ge=0, le=15)
    momentum: float = Field(ge=0, le=20)
    development: float = Field(ge=0, le=15)
    catalysts: float = Field(ge=0, le=10)
    community: float = Field(ge=0, le=10)
    risk: float = Field(ge=0, le=10)

    @property
    def total(self) -> float:
        return round(self.utility + self.market_structure + self.momentum + self.development + self.catalysts + self.community + self.risk, 2)


class TokenAnalysis(BaseModel):
    """Final structured analysis consumed by the decision engine."""

    model_config = ConfigDict(extra="forbid")

    token: TokenMarketData
    utility: UtilityEvidence
    risk: RiskAssessment
    score: ScoreBreakdown
    confidence: float = Field(ge=0, le=100)
    why_now: str = Field(min_length=1)
    invalidation_conditions: list[str] = Field(default_factory=list)
    decision: Decision = Decision.NO_TRADE

    @property
    def contract_address(self) -> str:
        """Exact verified mint address to be included in every alert."""
        return self.token.address

    @model_validator(mode="after")
    def enforce_decision_rules(self) -> "TokenAnalysis":
        if self.token.market_cap_zone is MarketCapZone.OUTSIDE or self.risk.hard_filter_failed or not self.utility.verified:
            self.decision = Decision.NO_TRADE
        elif self.score.total >= 85 and self.confidence >= 85:
            self.decision = Decision.BUY_CANDIDATE
        elif self.score.total >= 75:
            self.decision = Decision.WAIT
        else:
            self.decision = Decision.NO_TRADE
        return self
