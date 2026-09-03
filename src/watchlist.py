"""Persistent watchlist for candidates that are not yet alertable."""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from typing import Any

class WatchlistStore:
    def __init__(self,path: str|Path="data/watchlist.json"):
        self.path=Path(path); self._lock=Lock()
    def _load(self)->dict[str,dict[str,Any]]:
        if not self.path.exists(): return {}
        try:
            data=json.loads(self.path.read_text(encoding="utf-8")); return data if isinstance(data,dict) else {}
        except (OSError,ValueError): return {}
    def entries(self)->list[dict[str,Any]]:
        """Return monitored candidates for re-evaluation on every scan cycle."""
        with self._lock:
            data=self._load()
        return [dict(value) for value in data.values() if isinstance(value,dict) and value.get("contract_address")]
    def upsert(self,contract_address:str,**fields:Any)->None:
        with self._lock:
            data=self._load(); old=data.get(contract_address,{})
            old.update(fields); old["contract_address"]=contract_address; old["last_seen_at"]=datetime.now(timezone.utc).isoformat(); old["status"]="MONITORED"
            data[contract_address]=old
            self.path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.path.with_suffix(".tmp"); tmp.write_text(json.dumps(data,indent=2,sort_keys=True),encoding="utf-8"); tmp.replace(self.path)
    def remove(self,contract_address:str)->None:
        with self._lock:
            data=self._load(); data.pop(contract_address,None)
            self.path.parent.mkdir(parents=True,exist_ok=True); self.path.write_text(json.dumps(data,indent=2,sort_keys=True),encoding="utf-8")
