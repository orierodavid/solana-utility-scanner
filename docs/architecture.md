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
Data Collection
       ↓
Hard Risk & Eligibility Filters
       ↓
Utility Verification
       ↓
Market Structure Analysis
       ↓
Momentum Analysis
       ↓
Catalyst Analysis
       ↓
Alpha / Opportunity Scoring
       ↓
AI Analysis
       ↓
Trade Decision
       ↓
Notification
```

## 4. Core Modules

### Collector

Collects current and historical market data from approved Solana data providers.

Expected data includes:

- Token identity and contract address
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

### Scorer

Calculates the token's quantitative opportunity score from 0–100.

The score considers multiple independent dimensions rather than market cap alone.

Primary dimensions include:

- Utility / product quality
- Market structure
- Liquidity quality
- Momentum
- Volume acceleration
- Holder growth
- Buy/sell pressure
- Development activity
- Catalysts
- Community quality
- Wallet / smart-money signals
- Risk

### Analyst

Uses the collected evidence and scoring output to produce a structured analysis.

The analyst must answer:

1. What does the project do?
2. Why is the token considered a utility token?
3. Why is this setup interesting now?
4. What evidence supports continued momentum?
5. What are the major risks?
6. What could invalidate the setup?
7. Is the available evidence strong enough to justify an actionable alert?

The AI must distinguish facts from assumptions and must not invent missing data.

### Decision Engine

Converts validated evidence and scores into one of three primary decisions:

- **BUY CANDIDATE** — meets the required threshold and passes all mandatory filters.
- **WAIT** — promising setup but confirmation is still required.
- **NO TRADE** — insufficient opportunity, failed filter, or unacceptable risk.

The minimum actionable score is **85/100**, but a score of 85 or higher cannot override a mandatory risk failure.

### Notifier

Sends qualified alerts to the configured notification channel.

The first notification implementation is expected to use Telegram because it is straightforward to automate. WhatsApp can be added as a subsequent integration.

### Scheduler

Runs scans at the configured interval and prevents duplicate alerts where possible.

### Main

Coordinates the complete pipeline and provides the application entry point.

## 5. Scoring Philosophy

The system must not equate low market cap with high opportunity.

A $70,000 token is interesting because it is inside the discovery range. It becomes a trade candidate only when the evidence supports the setup.

The scoring model therefore evaluates:

### Utility

- Real-world or ecosystem use case
- Working product or credible development
- Actual relationship between token and product utility
- Adoption or evidence of users

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
- Transaction acceleration
- Holder growth
- New-wallet activity
- Liquidity growth

### Development

- Product releases
- GitHub activity where applicable
- Documentation
- Development updates
- Evidence of active builders

### Catalysts

- Product launches
- Partnerships
- Integrations
- Listings
- Major releases
- Ecosystem developments

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

More than 9 alerts should trigger review of the filtering thresholds rather than automatically being treated as success.

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

The alert should clearly distinguish measured data from AI interpretation.

## 8. Safety and Integrity Rules

The system is an analytical screening tool, not a guarantee of profit.

The engine must:

- Never fabricate missing data.
- Never claim certainty about future price or market cap.
- Treat thin liquidity as a major risk.
- Treat suspicious wallet concentration as a major risk.
- Reject obvious scams and rug-pull indicators.
- Preserve evidence behind each recommendation.
- Record the inputs and decision for later evaluation.

## 9. Future Learning Layer

Later versions can store historical alerts and outcomes to evaluate:

- Which signals were predictive
- Which signals generated false positives
- Time from alert to target levels
- Maximum drawdown after alerts
- Which catalysts produced the strongest moves
- Which risk indicators were most useful

The system should improve through measured historical performance rather than allowing the AI to change trading rules without evidence.
