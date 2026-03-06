from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Optional


class MongoRunSummaryStore:
    def __init__(
        self,
        *,
        url: str,
        db: str = "riskmonitor",
        collection: str = "run_summaries",
    ) -> None:
        try:
            from pymongo import MongoClient  # type: ignore
        except Exception as e:  # pylint: disable=broad-except
            raise RuntimeError("pymongo_dependency_missing") from e

        self._client = MongoClient(url, connectTimeoutMS=2000, serverSelectionTimeoutMS=2000)
        self._coll = self._client[db][collection]

    async def upsert(self, *, run_id: str, summary: dict[str, Any]) -> None:
        rid = str(run_id or "").strip()
        if not rid:
            return
        doc = dict(summary) if isinstance(summary, dict) else {}
        doc.setdefault("schema_version", "run_summary.v1")
        doc["run_id"] = rid
        doc.setdefault("ts_ms", int(time.time() * 1000))

        def _write() -> None:
            self._coll.replace_one({"_id": rid}, {"_id": rid, **doc}, upsert=True)

        await asyncio.to_thread(_write)

    async def get(self, *, run_id: str) -> Optional[dict[str, Any]]:
        rid = str(run_id or "").strip()
        if not rid:
            return None

        def _read() -> Optional[dict[str, Any]]:
            out = self._coll.find_one({"_id": rid})
            return dict(out) if isinstance(out, dict) else None

        return await asyncio.to_thread(_read)


_IN_MEMORY_RUN_SUMMARIES: dict[str, dict[str, Any]] = {}


class InMemoryRunSummaryStore:
    def __init__(self) -> None:
        self._items = _IN_MEMORY_RUN_SUMMARIES

    async def upsert(self, *, run_id: str, summary: dict[str, Any]) -> None:
        rid = str(run_id or "").strip()
        if not rid:
            return
        self._items[rid] = dict(summary) if isinstance(summary, dict) else {}

    async def get(self, *, run_id: str) -> Optional[dict[str, Any]]:
        rid = str(run_id or "").strip()
        if not rid:
            return None
        it = self._items.get(rid)
        return dict(it) if isinstance(it, dict) else None


def build_run_summary_store():
    url = (os.getenv("MONGO_URL") or "").strip()
    db = (os.getenv("MONGO_DB") or "riskmonitor").strip() or "riskmonitor"
    coll = (os.getenv("MONGO_RUN_SUMMARY_COLLECTION") or "run_summaries").strip() or "run_summaries"
    if not url:
        return InMemoryRunSummaryStore()
    try:
        return MongoRunSummaryStore(url=url, db=db, collection=coll)
    except Exception:
        return InMemoryRunSummaryStore()
