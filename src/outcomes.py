"""Historical recording for scanner decisions and alert deduplication.

This module deliberately records observations; it does not change scoring,
decision thresholds, or trading rules. Outcome data is keyed by the exact
Solana mint address and preserves the alert-time evidence needed for later
performance analysis.
"""

from __future__ import annotations

from asdict import asdict
