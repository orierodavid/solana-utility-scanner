# Trade Scoring Model

## Purpose

The scoring engine ranks live Solana utility-token opportunities on a transparent 100-point scale. It is a decision-support component, not an execution engine, and it never places trades.

## Hard gates

A token cannot become `BUY_CANDIDATE` when:

- market cap is outside **$50,000–$150,000**;
- the risk assessment has failed a hard filter; or
- verified utility evidence is missing.

Market cap is therefore an **opportunity universe**, not the buy signal.

## Score weights

| Factor | Maximum |
|---|---:|
| Utility | 20 |
| Market structure | 15 |
| Momentum | 20 |
| Development | 15 |
| Catalysts | 10 |
| Community | 10 |
| Risk | 10 |
| **Total** | **100** |

## Decisions

- **85–100:** `BUY_CANDIDATE`, provided confidence is also at least 85 and all hard gates pass.
- **75–84.99:** `WAIT` when hard gates pass.
- **Below 75:** `NO_TRADE`.
- Any hard-gate failure forces `NO_TRADE`, regardless of score.

## Evidence discipline

Missing values receive no points. The engine does not assume that an unavailable metric is bullish. `catalyst_score` is supplied explicitly and is bounded to 0–10; the engine does not invent catalyst evidence.

## Confidence

Confidence measures **evidence completeness**, not the probability of profit. It is calculated from the availability of market, security, utility, and development evidence. A 90 confidence score does not mean a 90% chance of a successful trade.

## Contract-address integrity

The exact verified Solana mint address remains attached to the token market data and must be used unchanged by downstream alerting. Symbols and names are never used to reconstruct a contract address.
