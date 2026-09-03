"""Continuous and single-cycle runtime for the live scanner."""
from __future__ import annotations
import argparse,logging,os,time
from collections.abc import Callable
from datetime import datetime,timezone
from .live_pipeline import LiveScannerRunner
from .monitoring import build_scan_health,validate_health,write_health_record
from .broad_discovery import BroadLiveSolanaCollector
logger=logging.getLogger("solana-utility-scanner.runtime")
def run_once(runner=None):
    runner=runner or LiveScannerRunner(collector=BroadLiveSolanaCollector()); started=datetime.now(timezone.utc); results=runner.run_once(); finished=datetime.now(timezone.utc)
    health=build_scan_health(started,finished,results); write_health_record(os.getenv("HEALTH_STORE_PATH","data/scan_health.jsonl"),health); logger.info("Scan health: %s",health.to_dict()); validate_health(health); return results
def run_forever(runner=None,*,interval_seconds=None,sleep:Callable[[float],None]=time.sleep):
    runner=runner or LiveScannerRunner(collector=BroadLiveSolanaCollector()); interval=interval_seconds if interval_seconds is not None else float(os.getenv("SCAN_INTERVAL_SECONDS","300"))
    if interval<=0: raise ValueError("SCAN_INTERVAL_SECONDS must be greater than zero")
    while True:
        started=time.monotonic()
        try: run_once(runner)
        except Exception: logger.exception("Scan cycle failed; continuing after interval")
        sleep(max(0.0,interval-(time.monotonic()-started)))
def main():
    parser=argparse.ArgumentParser(description="Run the Solana utility scanner"); parser.add_argument("--interval",type=float,default=None); parser.add_argument("--once",action="store_true"); args=parser.parse_args(); logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO")); run_once() if args.once else run_forever(interval_seconds=args.interval)
if __name__=="__main__": main()
