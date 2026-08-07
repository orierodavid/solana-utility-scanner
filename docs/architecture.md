# Solana Utility Scanner — System Architecture

## 1. Purpose

The Solana Utility Scanner is an automated market-intelligence and trade-screening engine focused exclusively on Solana utility tokens in the early-stage market-cap range.

The system is designed to identify a small number of high-quality short-term trading candidates rather than maximize the number of alerts.

## 2. Trading Objective

The primary discovery range is:

- **$50,000–$100,000 market cap:** Primary target zone
- **$100,000–$150,000 market cap:** Secondary target zone
- **Below $50,000:** Reject by default
- **Above $150,000:** Reject by default

Market cap is a **discovery filter**, not a buy signal. A token must pass the broader quality, momentum, utility, and risk analysis before it can become a trade candidate.

The strategic objective is to identify tokens with credible evidence of potential expansion toward approximately **$1M+ market cap**, without treating that outcome as guaranteed or predictable.

## 3. Decision Pipeline

```text
Market Discovery
       ↓
Live Data Collection
       ↓
Hard Risk & Eligibility Filters
       ↓
Real Evidence Verification
       ↓
Utility / Development / Risk Analysis
       ↓
Market Structure Analysis
       ↓
Momentum Analysis
       ↓
Catalyst / Timing Analysis
       ↓
Alpha / Opportunity Scoring
       ↓
AI Analysis (evidence-only, optional)
       ↓
Trade Decision
       ↓
Notification
```

Real evidence verification is mandatory for actionable live alerts. AI cannot create evidence that the collector or evidence providers did not establish.

## 4. Core Modules

### Collector

Collects current and historical market data from approved Solana data providers.

Expected data includes:

- Exact token mint/contract address
- Market capitalization
- Price
- Liquidity
- Trading volume
- Buy/sell activity
- Transaction counts
- Holder count and holder growth
- Token age
- Pool/pair information
- Creator/deployer information where available
- Wallet activity where available
- Project metadata and social links

### Validator

Applies mandatory pass/fail rules before a token reaches the scoring engine.

It checks for:

- Solana-only eligibility
- Utility requirement
- Minimum market-cap range
- Minimum viable liquidity
- Contract/security red flags
- Suspicious creator or wallet behavior
- Dangerous holder concentration
- Obvious rug-pull indicators
- Insufficient or unreliable data

A token that fails a mandatory rule is rejected regardless of its numerical score.

### Real Evidence Engine

The live scanner uses source-backed evidence rather than fabricated or assumed project information.

The current provider verifies:

- Reachable first-party project/documentation sources
- Product/use-case signals
- Explicit token utility signals
- Exact mint mentions when available
- Linked GitHub activity when available
- Catalyst/development language from source material
- Independent security and holder-risk data
- Liquidity risk relative to market cap
- Contract-authority risk

Evidence confidence is calculated from observed evidence. Missing evidence does not become a bullish assumption. Candidates without usable utility proof are rejected before alerting.

### Analyst

The analyst receives the verified evidence and produces a conservative thesis containing:

1. What the project does
2. Why the token qualifies as a utility token
3. Why the setup is interesting now
4. Evidence supporting the current setup
5. Major risks
6. Invalidation conditions
7. Confidence in the evidence set

The AI-facing analyst must preserve the exact contract address and must never invent missing data, URLs, catalysts, wallet activity, or risk findings.

### Scorer

Calculates the token's quantitative opportunity score from 0–100.

The score considers multiple independent dimensions rather than market cap alone:

- Utility / product quality
- Market structure
- Liquidity quality
- Momentum
- Volume acceleration
- Holder growth
- Buy/sell pressure
- Development activity
- Catalysts / timing
- Community quality
- Risk

### Decision Engine

Converts validated evidence and scores into one of three primary decisions:

- **BUY CANDIDATE** — meets the required threshold and passes all mandatory filters.
- **WAIT** — promising setup but confirmation is still required.
- **NO TRADE** — insufficient opportunity, failed filter, or unacceptable risk.

The minimum actionable score is **85/100**, but a score of 85 or higher cannot override a mandatory risk failure.

### Notifier

Sends qualified alerts to the configured notification channel.

Every actionable alert preserves the exact Solana mint address collected at the source boundary. The notification layer does not reconstruct an address from a token symbol or name.

### Scheduler

Runs scans at the configured interval and prevents duplicate alerts where possible.

### Main

Coordinates the complete pipeline and provides the application entry point.

## 5. Scoring Philosophy

The system must not equate low market cap with high opportunity.

A $70,000 token is interesting because it is inside the discovery range. It becomes a trade candidate only when the evidence supports the setup.

### Utility

- Real-world or ecosystem use case
- Working product or credible development
- Actual relationship between token and product utility
- Evidence of use or adoption

### Market Structure

- Market cap
- Liquidity
- Liquidity relative to market cap
- Holder distribution
- Trading stability

### Momentum

- Volume acceleration
- Price structure
- Buy/sell pressure
- Holder growth
- Transaction acceleration where available

### Development

- Product releases
- GitHub activity where applicable
- Documentation
- Development updates
- Evidence of active builders

### Catalysts / Timing

- Product launches
- Partnerships
- Integrations
- Listings
- Major releases
- Ecosystem developments
- Observed acceleration in market participation

Missing catalyst evidence contributes no bullish points.

### Wallet Intelligence

Where reliable data is available:

- Accumulation by established wallets
- Early-wallet selling
- New-wallet participation
- Concentration of purchases
- Suspicious wallet relationships

### Risk

- Creator/deployer behavior
- Holder concentration
- Contract authorities
- Liquidity risks
- Unlocks or supply events
- Suspicious transaction patterns
- Rug-pull indicators

## 6. Alert Philosophy

The system should target approximately **1–9 genuinely qualified opportunities per week**, but this is a quality target rather than a quota.

The scanner must never loosen its rules simply to produce more alerts.

Possible outcomes include:

- 0 alerts when no setup qualifies
- 1–3 exceptional opportunities
- 4–6 strong opportunities
- 7–9 opportunities during unusually active conditions

## 7. Alert Structure

A qualified alert should contain, at minimum:

```text
SOLANA UTILITY TRADE ALERT

Token:
Contract:
Market Cap:
Liquidity:
24h Volume:
Token Age:

Opportunity Score:
Risk Level:
Confidence:

Momentum:
Holder Growth:
Buy/Sell Pressure:
Catalyst:

Decision:

Why Now:

Key Risks:

Invalidation Conditions:
```

The alert clearly distinguishes measured data from analyst interpretation.

## 8. Safety and Integrity Rules

The engine must:

- Never fabricate missing data.
- Never claim certainty about future price or market cap.
- Treat thin liquidity as a major risk.
- Treat suspicious wallet concentration as a major risk.
- Reject obvious scams and rug-pull indicators.
- Preserve evidence behind each recommendation.
- Preserve the exact source mint through every pipeline stage.
- Fail closed when required evidence cannot be verified.
- Never lower thresholds simply to reach the weekly alert target.

## 9. Future Learning Layer

Later versions can store historical alerts and outcomes to evaluate:

- Which signals were predictive
- Which signals generated false positives
- Time from alert to target levels
- Maximum drawdown after alerts
- Which catalysts produced the strongest moves
- Which risk indicators were most useful

The system should improve through measured historical performance rather than allowing the AI to change trading rules without evidence.
