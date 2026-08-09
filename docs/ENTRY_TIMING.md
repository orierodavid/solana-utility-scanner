# Entry Timing Strategy

The scanner is intentionally optimized for catching the beginning of a utility-token move rather than validating a move after it has already happened.

| Market cap | State | Meaning |
|---|---|---|
| $40K-$75K | EARLY_BUY | Preferred actionable entry zone when utility, security, score and confidence gates pass. |
| $75K-$120K | CONFIRMATION | Move is developing; early-entry window has passed. |
| $120K-$150K | MISSED_ENTRY | Monitoring only. A high score must not turn this into a fresh buy signal. |
| >$150K | OUTSIDE | Outside the strategy's discovery range. |

The $40K threshold is a discovery floor, not a standalone buy condition. Security, utility, liquidity, momentum and confidence gates still apply.
