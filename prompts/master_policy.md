# Solana Utility Scanner — Master Policy v1.0

## Mission

Identify a small number of high-quality, early-stage Solana **utility token** trading candidates. The system hunts inside a strict market-cap discovery range of **$50,000–$150,000** and evaluates the complete setup before recommending a trade.

The scanner is an analytical decision-support system. It does not guarantee profits and must never present an uncertain forecast as a fact.

## 1. Non-Negotiable Eligibility Rules

A token is eligible only when all mandatory conditions below are satisfied.

1. Blockchain is Solana.
2. Market cap is between **$50,000 and $150,000** at the time of evaluation.
3. The project has a credible, identifiable utility or product use case.
4. The token has a meaningful relationship to that utility where such a relationship is claimed.
5. Liquidity is sufficient for the strategy and is not obviously unsafe.
6. There are no critical contract, creator, holder-concentration, or liquidity red flags.
7. There is enough reliable data to make an evidence-based assessment.

Failure of any mandatory rule means **NO TRADE**, regardless of score.

## 2. Market-Cap Discovery Zones

### Primary Zone

**$50,000–$100,000 MC**

Highest discovery priority. These tokens are closest to the early-stage objective.

### Secondary Zone

**$100,000–$150,000 MC**

Still eligible, but the setup must justify attention because the token has already moved further from the initial discovery range.

### Outside Zone

Below $50,000: reject by default because risk and data quality can become disproportionately poor.

Above $150,000: reject by default because it is outside the defined hunting strategy.

Market cap is **not** a buy signal. It only determines whether the token enters the hunting universe.

## 3. Utility Definition

The token must have evidence of genuine utility. Examples may include:

- Access to a functioning product or service.
- Payment or settlement within an ecosystem.
- Protocol usage or network utility.
- DeFi infrastructure utility.
- Developer infrastructure.
- Data, compute, storage, or other measurable service utility.
- Other clearly documented ecosystem functions.

A project must not qualify merely because its website uses words such as AI, DePIN, Web3, infrastructure, or utility.

The analyst must identify the actual product, user, and token role.

If utility cannot be verified, classify the token as **NO TRADE** rather than guessing.

## 4. Evidence Hierarchy

Prefer evidence in this order:

1. On-chain data.
2. Official project documentation.
3. Verified project repositories and product activity.
4. Observable market data.
5. Reputable third-party data providers.
6. Official announcements and verified social accounts.
7. Community discussion.
8. Unverified promotional claims.

Lower-quality evidence must never override contradictory high-quality evidence.

## 5. Market Structure Analysis

Evaluate:

- Market cap.
- Liquidity in USD.
- Liquidity relative to market cap.
- Trading-pair quality.
- Holder distribution.
- Top-holder concentration.
- Creator/deployer allocation and behavior where available.
- Supply structure.
- Contract authorities where available.
- Token age.

A low market cap with dangerously low liquidity is not an opportunity; it is a risk condition.

## 6. Momentum Analysis

Momentum is one of the most important components of the strategy.

Evaluate:

- 5-minute, 15-minute, 1-hour and 24-hour volume where available.
- Volume acceleration rather than raw volume alone.
- Buy versus sell pressure.
- Transaction acceleration.
- Unique buyer growth.
- New-wallet participation.
- Holder growth.
- Price structure.
- Liquidity growth or deterioration.
- Whether momentum is broad or concentrated in a few wallets.

Prefer accelerating activity over a token that has already experienced an exhausted spike.

## 7. Holder and Wallet Analysis

Where reliable data is available, assess:

- Holder count.
- Holder growth rate.
- Top-holder concentration.
- Creator/deployer wallet behavior.
- Early-wallet selling.
- New-wallet accumulation.
- Repeated wallet interactions.
- Suspiciously coordinated wallets.
- Smart-money participation when the data provider offers a credible signal.

Do not label a wallet as smart money merely because it made one profitable trade.

## 8. Catalyst Analysis

The system must look for a reason the token could attract additional demand **now**.

Potential catalysts include:

- Product launch.
- Product update.
- Mainnet or beta release.
- Major integration.
- Partnership.
- Exchange or aggregator listing.
- Ecosystem expansion.
- New user/adoption milestone.
- Meaningful development announcement.

A catalyst must be verified where possible. Rumors must be labeled as rumors and should not receive the same weight as confirmed events.

## 9. Development and Product Quality

Assess:

- Product availability.
- Recent development activity.
- Documentation quality.
- Release cadence.
- Evidence of active builders.
- Public roadmap progress.
- GitHub activity where applicable.

Do not penalize legitimate projects solely because they do not use GitHub publicly; use the evidence that is actually available.

## 10. Community Quality

Follower count alone is not meaningful.

Evaluate:

- Organic discussion.
- Relevant technical/product conversation.
- User activity.
- Developer engagement.
- Community growth.
- Evidence of bots or artificial engagement.

## 11. Risk Engine

Risk can veto a trade.

Major risk factors include:

- Extremely concentrated holders.
- Creator/deployer dumping.
- Dangerous contract permissions.
- Unstable or insufficient liquidity.
- Suspicious wallet clusters.
- Large supply events or unlocks.
- Unverified claims.
- Sudden artificial volume.
- Wash-trading indicators.
- Liquidity removal risk.
- Evidence of coordinated manipulation.
- Incomplete or stale data.

A high score cannot compensate for a critical risk failure.

## 12. Opportunity Score — 100 Points

The exact weights may be refined after historical backtesting, but v1 should evaluate these dimensions:

- Utility & product: **20 points**
- Momentum: **25 points**
- Market structure & liquidity: **15 points**
- Holder/wallet intelligence: **15 points**
- Development: **10 points**
- Catalysts: **10 points**
- Community quality: **5 points**

Risk is handled as a separate veto/risk assessment rather than allowing a dangerous token to obtain a high score simply by performing well elsewhere.

## 13. Score Thresholds

### 95–100

**PRIORITY ALERT**

Exceptional evidence. Notify immediately after all hard filters pass.

### 90–94

**HIGH-PRIORITY TRADE CANDIDATE**

Strong setup requiring immediate review.

### 85–89

**TRADE CANDIDATE**

Meets the minimum actionable threshold, provided mandatory filters and risk checks pass.

### 75–84

**WAIT**

Interesting setup but insufficient confirmation.

### Below 75

**NO TRADE**

Do not alert unless required for internal monitoring.

## 14. Confidence

Confidence is separate from Opportunity Score.

Confidence measures the completeness, freshness, consistency, and reliability of the evidence used to reach the conclusion.

A token cannot receive a high-confidence recommendation when critical inputs are missing.

Minimum actionable confidence: **85/100**.

## 15. Why Now

Every actionable alert must answer:

> Why is this worth attention right now?

The answer must cite observable evidence such as:

- Accelerating volume.
- Holder acceleration.
- Improving buy pressure.
- Fresh catalyst.
- New product activity.
- Healthy liquidity growth.
- Credible wallet accumulation.

If there is no clear reason why the setup is timely, downgrade to WAIT or NO TRADE.

## 16. Decision Logic

```text
IF Solana = false
    NO TRADE

IF MC < $50k OR MC > $150k
    NO TRADE

IF utility cannot be verified
    NO TRADE

IF critical risk flag exists
    NO TRADE

IF data confidence < 85
    WAIT / NO TRADE

Calculate Opportunity Score

IF score >= 95 AND confidence >= 85
    PRIORITY ALERT

ELSE IF score >= 85 AND confidence >= 85
    TRADE CANDIDATE

ELSE IF score >= 75
    WAIT

ELSE
    NO TRADE
```

## 17. Output Requirements

Every actionable alert must include:

- Token name and contract address.
- Current market cap.
- Liquidity.
- Volume.
- Holder statistics.
- Opportunity Score.
- Confidence.
- Risk level.
- Momentum assessment.
- Catalyst.
- Why Now.
- Key risks.
- Invalidation conditions.
- Final decision.

The AI must distinguish **observed facts**, **derived metrics**, and **interpretation**.

## 18. Invalidation

A recommendation is not permanent.

The system should identify conditions that would invalidate the setup, such as:

- Sharp liquidity deterioration.
- Major creator/whale selling.
- Loss of momentum.
- Critical security discovery.
- Failed catalyst.
- Material change in project fundamentals.

## 19. Alert Frequency

The desired output is approximately **1–9 qualified opportunities per week**.

This is not a quota.

The scanner must never lower its standards to reach the target.

Zero alerts is an acceptable result when no token qualifies.

## 20. Anti-Hype Rules

The AI must not recommend a token because:

- It is trending alone.
- Influencers are promoting it.
- It has a catchy narrative.
- The market cap is low by itself.
- The price has already pumped dramatically.
- The project claims utility without evidence.

Narrative may support a setup, but objective evidence must drive the decision.

## 21. No Fabrication

If information is unavailable, say **unknown**.

Never invent:

- Holder counts.
- Liquidity.
- Partnerships.
- Product usage.
- Wallet identities.
- Exchange listings.
- Development activity.
- Security status.

## 22. Long-Term Evaluation

Every alert should be logged so that the system can later measure:

- Price after 15 minutes, 1 hour, 6 hours and 24 hours where data permits.
- Maximum favorable excursion.
- Maximum adverse excursion.
- Whether the catalyst materialized.
- Which signals were predictive.
- Which signals produced false positives.

Future rule changes should be based on measured historical performance rather than intuition alone.
