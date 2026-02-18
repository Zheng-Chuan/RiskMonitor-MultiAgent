from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def new_run_id(*, event_id: str) -> str:
    now_ms = int(time.time() * 1000)
    safe_event_id = event_id.replace("/", "_").replace(":", "_")
    return f"run_{safe_event_id}_{now_ms}"


@dataclass(frozen=True)
class ContextRecord:
    run_id: str
    event_id: str
    created_at_ms: int
    data: dict[str, Any]


class ContextStore:
    def upsert(self, *, run_id: str, event_id: str, patch: dict[str, Any]) -> None:
        raise NotImplementedError

    def get(self, *, run_id: str) -> Optional[ContextRecord]:
        raise NotImplementedError

    def get_final_by_event_id(self, *, event_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    def get_event_snapshot_by_event_id(self, *, event_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError


class FileContextStore(ContextStore):
    def __init__(self, *, base_dir: Optional[str] = None) -> None:
        self._base_dir = Path(base_dir or os.getenv("CONTEXT_STORE_DIR", "data/context_store"))
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        return self._base_dir / f"{run_id}.json"

    def upsert(self, *, run_id: str, event_id: str, patch: dict[str, Any]) -> None:
        if not isinstance(patch, dict):
            return
        path = self._path(run_id)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        else:
            data = {}
        data.setdefault("run_id", run_id)
        data.setdefault("event_id", event_id)
        data.setdefault("created_at_ms", int(time.time() * 1000))
        for k, v in patch.items():
            data[k] = v
        path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    def get(self, *, run_id: str) -> Optional[ContextRecord]:
        path = self._path(run_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        event_id = data.get("event_id")
        created_at_ms = data.get("created_at_ms")
        if not isinstance(event_id, str) or not isinstance(created_at_ms, int):
            return None
        return ContextRecord(
            run_id=run_id,
            event_id=event_id,
            created_at_ms=created_at_ms,
            data=data,
        )

    def get_final_by_event_id(self, *, event_id: str) -> Optional[dict[str, Any]]:
        if not isinstance(event_id, str) or not event_id:
            return None
        for path in sorted(self._base_dir.glob("run_*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            if data.get("event_id") != event_id:
                continue
            final = data.get("final_output")
            if isinstance(final, dict):
                return final
            continue
        return None

    def get_event_snapshot_by_event_id(self, *, event_id: str) -> Optional[dict[str, Any]]:
        if not isinstance(event_id, str) or not event_id:
            return None
        for path in sorted(self._base_dir.glob("run_*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            if data.get("event_id") != event_id:
                continue
            snapshot = data.get("event_snapshot")
            if isinstance(snapshot, dict):
                return snapshot
        return None
