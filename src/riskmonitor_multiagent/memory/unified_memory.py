from __future__ import annotations

import os
from typing import Any

from riskmonitor_multiagent.contracts.memory_entry import normalize_memory_entry
from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore
from riskmonitor_multiagent.memory.mongo_run_summary_store import build_run_summary_store


class UnifiedMemory:
    def __init__(self) -> None:
        self._working = self._build_working_store()
        self._run_summaries = build_run_summary_store()
        enable_semantic = os.getenv("MEMORY_ENABLE_SEMANTIC_APPEND", "0").strip() in {"1", "true", "True"}
        self._semantic = ChromaVectorStore(collection=os.getenv("CHROMA_MEMORY_COLLECTION")) if enable_semantic else None

    def _build_working_store(self):
        from riskmonitor_multiagent.memory.stores import RedisMemoryStore, SqlMemoryStore, default_sqlite_memory_url

        url = (os.getenv("REDIS_URL") or "").strip()
        if not url:
            sqlite_url = default_sqlite_memory_url()
            return SqlMemoryStore(url=sqlite_url)
        max_len = int(os.getenv("WORKING_MEMORY_MAX_LEN", "2000"))
        ttl_s = os.getenv("WORKING_MEMORY_TTL_S")
        ttl = int(ttl_s) if ttl_s is not None and ttl_s.strip().isdigit() else 86400
        try:
            return RedisMemoryStore(url=url, max_len=max_len, ttl_s=ttl)
        except Exception:
            sqlite_url = default_sqlite_memory_url()
            return SqlMemoryStore(url=sqlite_url)

    async def append(self, entry: dict[str, Any]) -> dict[str, Any]:
        nd = normalize_memory_entry(entry)
        await self._working.append(nd)
        await self._maybe_upsert_semantic(nd)
        return nd

    async def list_recent(self, *, agent_id: str, scope: str, session_id: str | None = None, run_id: str | None = None, kinds: list[str] | None = None, limit: int = 50) -> list[dict[str, Any]]:
        from riskmonitor_multiagent.memory.stores import MemoryQuery

        q = MemoryQuery(agent_id=agent_id, scope=scope, session_id=session_id, run_id=run_id, kinds=kinds, limit=limit)
        return await self._working.list_recent(q)

    async def upsert_run_summary(self, *, run_id: str, summary: dict[str, Any]) -> None:
        await self._run_summaries.upsert(run_id=run_id, summary=summary)

    async def get_run_summary(self, *, run_id: str) -> dict[str, Any] | None:
        return await self._run_summaries.get(run_id=run_id)

    async def _maybe_upsert_semantic(self, entry: dict[str, Any]) -> None:
        if self._semantic is None:
            return
        kind = entry.get("kind")
        if kind not in {"plan", "final"}:
            return
        content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
        text = content.get("text")
        if not isinstance(text, str) or not text.strip():
            return
        alert_id = str(entry.get("entry_id") or "")
        if not alert_id:
            return
        self._semantic.upsert_alert(
            alert_id=alert_id,
            document=text,
            metadata={
                "type": "memory_entry",
                "kind": kind,
                "agent_id": entry.get("agent_id"),
                "scope": entry.get("scope"),
                "session_id": entry.get("session_id"),
                "run_id": entry.get("run_id"),
            },
        )
