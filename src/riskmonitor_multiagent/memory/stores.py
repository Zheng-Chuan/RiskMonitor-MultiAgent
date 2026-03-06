from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import JSON, Column, MetaData, String, Table, Text, create_engine, select
from sqlalchemy.engine import Engine

from riskmonitor_multiagent.contracts.memory_entry import MemoryEntry, normalize_memory_entry

_SQL_ENGINES: list[Engine] = []


def dispose_all_sql_memory_engines() -> None:
    for e in list(_SQL_ENGINES):
        try:
            e.dispose()
        except Exception:
            pass
    _SQL_ENGINES.clear()


@dataclass(frozen=True)
class MemoryQuery:
    agent_id: str
    scope: str
    session_id: str | None = None
    run_id: str | None = None
    kinds: list[str] | None = None
    limit: int = 50


class InMemoryStore:
    def __init__(self) -> None:
        self._items: list[dict[str, Any]] = []

    async def append(self, entry: dict[str, Any]) -> dict[str, Any]:
        nd = normalize_memory_entry(entry)
        self._items.append(nd)
        return nd

    async def list_recent(self, query: MemoryQuery) -> list[dict[str, Any]]:
        limit = max(1, int(query.limit))
        kinds = set(query.kinds) if isinstance(query.kinds, list) else None
        out: list[dict[str, Any]] = []
        for it in reversed(self._items):
            if not isinstance(it, dict):
                continue
            if it.get("scope") != query.scope:
                continue
            if query.scope != "shared" and it.get("agent_id") != query.agent_id:
                continue
            if query.session_id is not None and it.get("session_id") != query.session_id:
                continue
            if query.run_id is not None and it.get("run_id") != query.run_id:
                continue
            if kinds is not None and it.get("kind") not in kinds:
                continue
            out.append(it)
            if len(out) >= limit:
                break
        return list(reversed(out))


class SqlMemoryStore:
    def __init__(self, *, url: str) -> None:
        self._engine = create_engine(url)
        _SQL_ENGINES.append(self._engine)
        self._meta = MetaData()
        self._table = Table(
            "memory_entries",
            self._meta,
            Column("entry_id", String(64), primary_key=True),
            Column("ts_ms", String(32), nullable=False),
            Column("agent_id", String(64), nullable=False),
            Column("scope", String(64), nullable=False),
            Column("kind", String(64), nullable=False),
            Column("session_id", String(128), nullable=True),
            Column("run_id", String(128), nullable=True),
            Column("schema_version", String(64), nullable=False),
            Column("tags_json", Text, nullable=True),
            Column("content_json", JSON, nullable=False),
        )
        self._meta.create_all(self._engine)

    async def append(self, entry: dict[str, Any]) -> dict[str, Any]:
        nd = normalize_memory_entry(entry)
        tags = nd.get("tags") if isinstance(nd.get("tags"), list) else None
        tags_json = json.dumps(tags, ensure_ascii=False) if tags is not None else None
        row = {
            "entry_id": str(nd.get("entry_id")),
            "ts_ms": str(int(nd.get("ts_ms") or 0)),
            "agent_id": str(nd.get("agent_id")),
            "scope": str(nd.get("scope")),
            "kind": str(nd.get("kind")),
            "session_id": nd.get("session_id"),
            "run_id": nd.get("run_id"),
            "schema_version": str(nd.get("schema_version")),
            "tags_json": tags_json,
            "content_json": nd.get("content") if isinstance(nd.get("content"), dict) else {},
        }
        def _write() -> None:
            with self._engine.begin() as conn:
                conn.execute(self._table.delete().where(self._table.c.entry_id == row["entry_id"]))
                conn.execute(self._table.insert(), row)
        await asyncio.to_thread(_write)
        return nd

    async def list_recent(self, query: MemoryQuery) -> list[dict[str, Any]]:
        limit = max(1, int(query.limit))
        kinds = set(query.kinds) if isinstance(query.kinds, list) else None

        def _read() -> list[dict[str, Any]]:
            stmt = select(self._table).where(self._table.c.scope == query.scope)
            if query.scope != "shared":
                stmt = stmt.where(self._table.c.agent_id == query.agent_id)
            if query.session_id is not None:
                stmt = stmt.where(self._table.c.session_id == query.session_id)
            if query.run_id is not None:
                stmt = stmt.where(self._table.c.run_id == query.run_id)
            if kinds is not None and len(kinds) > 0:
                stmt = stmt.where(self._table.c.kind.in_(list(kinds)))
            stmt = stmt.order_by(self._table.c.ts_ms.desc()).limit(limit)
            with self._engine.begin() as conn:
                rows = conn.execute(stmt).mappings().all()
            out: list[dict[str, Any]] = []
            for r in reversed(rows):
                tags_json = r.get("tags_json")
                tags = None
                if isinstance(tags_json, str) and tags_json.strip():
                    try:
                        tj = json.loads(tags_json)
                        tags = tj if isinstance(tj, list) else None
                    except Exception:
                        tags = None
                out.append(
                    normalize_memory_entry(
                        {
                            "schema_version": r.get("schema_version"),
                            "entry_id": r.get("entry_id"),
                            "ts_ms": int(r.get("ts_ms") or 0),
                            "agent_id": r.get("agent_id"),
                            "scope": r.get("scope"),
                            "kind": r.get("kind"),
                            "content": r.get("content_json") if isinstance(r.get("content_json"), dict) else {},
                            "tags": tags,
                            "session_id": r.get("session_id"),
                            "run_id": r.get("run_id"),
                        }
                    )
                )
            return out

        return await asyncio.to_thread(_read)


class RedisMemoryStore:
    def __init__(self, *, url: str, max_len: int = 2000, ttl_s: int | None = 86400) -> None:
        try:
            import redis.asyncio as redis  # type: ignore
        except Exception as e:  # pylint: disable=broad-except
            raise RuntimeError("redis_dependency_missing") from e
        self._redis = redis.from_url(url)
        self._max_len = int(max_len)
        self._ttl_s = int(ttl_s) if ttl_s is not None else None

    def _key(self, *, agent_id: str, scope: str, session_id: str | None) -> str:
        sid = session_id or "default"
        if scope == "shared":
            return f"rm:mem:shared:{sid}"
        return f"rm:mem:private:{agent_id}:{sid}"

    async def append(self, entry: dict[str, Any]) -> dict[str, Any]:
        nd = normalize_memory_entry(entry)
        key = self._key(agent_id=str(nd.get("agent_id")), scope=str(nd.get("scope")), session_id=nd.get("session_id"))
        data = json.dumps(nd, ensure_ascii=False, sort_keys=True)
        pipe = self._redis.pipeline()
        pipe.rpush(key, data)
        pipe.ltrim(key, max(0, self._max_len * -1), -1)
        if self._ttl_s is not None:
            pipe.expire(key, int(self._ttl_s))
        await pipe.execute()
        return nd

    async def list_recent(self, query: MemoryQuery) -> list[dict[str, Any]]:
        key = self._key(agent_id=query.agent_id, scope=query.scope, session_id=query.session_id)
        limit = max(1, int(query.limit))
        raw = await self._redis.lrange(key, max(0, -limit), -1)
        out: list[dict[str, Any]] = []
        for b in raw:
            try:
                s = b.decode("utf-8") if isinstance(b, (bytes, bytearray)) else str(b)
                d = json.loads(s)
                if not isinstance(d, dict):
                    continue
                if query.run_id is not None and d.get("run_id") != query.run_id:
                    continue
                if isinstance(query.kinds, list) and d.get("kind") not in set(query.kinds):
                    continue
                if query.scope != "shared" and d.get("agent_id") != query.agent_id:
                    continue
                out.append(normalize_memory_entry(d))
            except Exception:
                continue
        return out


def default_sqlite_memory_url() -> str:
    base = Path(__file__).resolve().parents[3]
    path = os.getenv("MEMORY_SQLITE_PATH")
    if path is None or not str(path).strip():
        path = str(base / "data" / "memory.sqlite")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{p}"
