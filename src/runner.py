"""Continuous and single-cycle runtime for the live scanner."""

from __future__ import annotations

import argparse
import logging
import os
import time
from collections.abc import Callable
from datetime import datetime, timezone

from .live_pipeline import LiveScannerRunner
from .monitoring import build_scan_health, validate_health, write_health_record

logger = logging.getLogger("solana-utility-scanner.runtime")


def run_once(runner: LiveScannerRunner | None = None) -> list:
    """Execute exactly one complete live scanner cycle and validate its health."""
    runner = runner or LiveScannerRunner()
    started = datetime.now(timezone.utc)
    results = runner.run_once()
    finished = datetime.now(timezone.utc)
    health = build_scan_health(started, finished, results)
    health_path = os.getenv("HEALTH_STORE_PATH", "data/scan_health.jsonl")
    write_health_record(health_path, health)
    logger.info("Scan health: %s", health.to_dict())
    validate_health(health)
    logger.info(
        "Scan cycle complete: candidates=%d alerts=%d",
        len(results),
        sum(result.should_notify for result in results),
    )
    return results


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
            run_once(runner)
        except Exception:
            logger.exception("Scan cycle failed; continuing after interval")

        elapsed = time.monotonic() - started
        sleep(max(0.0, interval - elapsed))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Solana utility scanner")
    parser.add_argument("--interval", type=float, default=None)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    if args.once:
        run_once()
    else:
        run_forever(interval_seconds=args.interval)


if __name__ == "__main__":
    main()
