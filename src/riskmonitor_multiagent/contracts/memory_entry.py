from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any


MEMORY_ENTRY_SCHEMA_VERSION = "memory_entry.v1"


def _is_non_empty_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def validate_memory_entry(entry: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(entry, dict):
        return False, ["entry must be dict"]

    schema_version = entry.get("schema_version")
    if schema_version is None:
        pass
    elif not _is_non_empty_str(schema_version):
        errors.append("bad_schema_version")
    elif schema_version != MEMORY_ENTRY_SCHEMA_VERSION:
        errors.append("unsupported_schema_version")

    if not _is_non_empty_str(entry.get("entry_id")):
        errors.append("bad_entry_id")
    if not isinstance(entry.get("ts_ms"), int):
        errors.append("bad_ts_ms")
    if not _is_non_empty_str(entry.get("agent_id")):
        errors.append("bad_agent_id")
    if not _is_non_empty_str(entry.get("scope")):
        errors.append("bad_scope")
    if not _is_non_empty_str(entry.get("kind")):
        errors.append("bad_kind")
    if not isinstance(entry.get("content"), dict):
        errors.append("bad_content")

    tags = entry.get("tags")
    if tags is not None:
        if not isinstance(tags, list) or any(not _is_non_empty_str(x) for x in tags):
            errors.append("bad_tags")

    for opt in ("session_id", "run_id"):
        v = entry.get(opt)
        if v is not None and not _is_non_empty_str(v):
            errors.append(f"bad_{opt}")

    return len(errors) == 0, errors


def normalize_memory_entry(entry: dict[str, Any]) -> dict[str, Any]:
    out = dict(entry) if isinstance(entry, dict) else {}
    out.setdefault("schema_version", MEMORY_ENTRY_SCHEMA_VERSION)
    out.setdefault("entry_id", f"mem_{uuid.uuid4().hex}")
    out.setdefault("ts_ms", int(time.time() * 1000))
    out.setdefault("agent_id", "shared")
    out.setdefault("scope", "shared")
    out.setdefault("kind", "unknown")
    out.setdefault("content", {})
    if not isinstance(out.get("content"), dict):
        out["content"] = {}
    tags = out.get("tags")
    if tags is not None and not isinstance(tags, list):
        out["tags"] = None
    return out


@dataclass(frozen=True)
class MemoryEntry:
    schema_version: str
    entry_id: str
    ts_ms: int
    agent_id: str
    scope: str
    kind: str
    content: dict[str, Any]
    tags: list[str] | None = None
    session_id: str | None = None
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entry_id": self.entry_id,
            "ts_ms": int(self.ts_ms),
            "agent_id": self.agent_id,
            "scope": self.scope,
            "kind": self.kind,
            "content": dict(self.content),
            "tags": list(self.tags) if isinstance(self.tags, list) else None,
            "session_id": self.session_id,
            "run_id": self.run_id,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "MemoryEntry":
        nd = normalize_memory_entry(d)
        return MemoryEntry(
            schema_version=str(nd.get("schema_version")),
            entry_id=str(nd.get("entry_id")),
            ts_ms=int(nd.get("ts_ms")),
            agent_id=str(nd.get("agent_id")),
            scope=str(nd.get("scope")),
            kind=str(nd.get("kind")),
            content=nd.get("content") if isinstance(nd.get("content"), dict) else {},
            tags=nd.get("tags") if isinstance(nd.get("tags"), list) else None,
            session_id=nd.get("session_id") if isinstance(nd.get("session_id"), str) else None,
            run_id=nd.get("run_id") if isinstance(nd.get("run_id"), str) else None,
        )

