"""Continuous production runtime for the live scanner.

The runtime intentionally contains no trading logic. It repeatedly executes
one complete scanner cycle and waits between cycles. A failure in one cycle is
logged and does not terminate the process, while the scanner itself remains
fail-closed for individual candidates.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from collections.abc import Callable

from .live_pipeline import LiveScannerRunner

logger = logging.getLogger("solana-utility-scanner.runtime")


def run_forever(
    runner: LiveScannerRunner | None = None,
    *,
    interval_seconds: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Run scanner cycles continuously until the process receives SIGTERM/SIGINT."""
    runner = runner or LiveScannerRunner()
    interval = interval_seconds
    if interval is None:
        interval = float(os.getenv("SCAN_INTERVAL_SECONDS", "300"))
    if interval <= 0:
        raise ValueError("SCAN_INTERVAL_SECONDS must be greater than zero")

    logger.info("Continuous scanner started; interval=%ss", interval)
    while True:
        started = time.monotonic()
        try:
            results = runner.run_once()
            logger.info(
                "Scan cycle complete: candidates=%d alerts=%d",
                len(results),
                sum(result.should_notify for result in results),
            )
        except Exception:
            logger.exception("Scan cycle failed; continuing after interval")

        elapsed = time.monotonic() - started
        sleep(max(0.0, interval - elapsed))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Solana utility scanner continuously")
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Seconds between scan cycles; defaults to SCAN_INTERVAL_SECONDS or 300",
    )
    args = parser.parse_args()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_forever(interval_seconds=args.interval)


if __name__ == "__main__":
    main()
