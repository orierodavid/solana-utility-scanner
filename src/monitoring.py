"""Production scan health telemetry and alert-delivery diagnostics."""
from __future__ import annotations
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
import json
from pathlib import Path
from typing import Any
@dataclass(frozen=True)
class ScanHealth:
    started_at:datetime; finished_at:datetime; candidates:int; evaluated:int; alerts_qualified:int; alerts_sent:int; candidates_failed:int; delivery_failures:int; re_evaluated:int; duration_seconds:float
    @property
    def healthy(self)->bool:return self.duration_seconds<240
    @property
    def degraded(self)->bool:return self.candidates_failed>0 or self.delivery_failures>0
    def to_dict(self)->dict[str,Any]:
        payload=asdict(self);payload["started_at"]=self.started_at.isoformat();payload["finished_at"]=self.finished_at.isoformat();payload["healthy"]=self.healthy;payload["degraded"]=self.degraded;return payload
def build_scan_health(started_at:datetime,finished_at:datetime,results:list[Any])->ScanHealth:
    duration=max(0.0,(finished_at-started_at).total_seconds())
    # delivery_error was added for the live Telegram diagnostics path. Keep
    # monitoring backward-compatible with older/fake result objects that do
    # not expose that optional field.
    delivery_errors=[getattr(r,"delivery_error",None) for r in results]
    return ScanHealth(started_at.astimezone(timezone.utc),finished_at.astimezone(timezone.utc),len(results),sum(r.pipeline is not None for r in results),sum(r.should_notify for r in results),sum(r.notified for r in results),sum(r.error is not None and delivery_error is None for r,delivery_error in zip(results,delivery_errors)),sum(delivery_error is not None for delivery_error in delivery_errors),sum(getattr(r,"re_evaluated",False) for r in results),duration)
def write_health_record(path:str|Path,health:ScanHealth)->None:
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("a",encoding="utf-8") as handle:handle.write(json.dumps(health.to_dict(),sort_keys=True)+"\n")
def validate_health(health:ScanHealth)->None:
    if health.duration_seconds>=240:raise RuntimeError("scan exceeded the four-minute production budget")
