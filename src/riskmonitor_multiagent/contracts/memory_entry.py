from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any


MEMORY_ENTRY_SCHEMA_VERSION = "memory_entry.v1"
MEMORY_TYPE_VALUES = {"episodic", "semantic", "procedural"}


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
    elif str(entry.get("scope")) not in {"private", "shared"}:
        errors.append("unsupported_scope")
    if not _is_non_empty_str(entry.get("kind")):
        errors.append("bad_kind")
    memory_type = entry.get("memory_type")
    if memory_type is not None:
        if not _is_non_empty_str(memory_type):
            errors.append("bad_memory_type")
        elif memory_type not in MEMORY_TYPE_VALUES:
            errors.append("unsupported_memory_type")
    if not isinstance(entry.get("content"), dict):
        errors.append("bad_content")

    source = entry.get("source")
    if source is not None and not _is_non_empty_str(source):
        errors.append("bad_source")

    confidence = entry.get("confidence")
    if confidence is not None:
        if not isinstance(confidence, (int, float)):
            errors.append("bad_confidence")
        elif float(confidence) < 0.0 or float(confidence) > 1.0:
            errors.append("bad_confidence")

    created_by = entry.get("created_by")
    if created_by is not None and not _is_non_empty_str(created_by):
        errors.append("bad_created_by")

    trace_ref = entry.get("trace_ref")
    if trace_ref is not None and not isinstance(trace_ref, dict):
        errors.append("bad_trace_ref")

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
    out.setdefault("memory_type", _infer_memory_type(str(out.get("kind") or "unknown")))
    out.setdefault("content", {})
    out.setdefault("source", str(out.get("kind") or "unknown"))
    out.setdefault("confidence", 1.0)
    out.setdefault("created_by", str(out.get("agent_id") or "shared"))
    out.setdefault("trace_ref", _build_trace_ref(out))
    if not isinstance(out.get("content"), dict):
        out["content"] = {}
    if out.get("scope") not in {"private", "shared"}:
        out["scope"] = "shared"
    if out.get("memory_type") not in MEMORY_TYPE_VALUES:
        out["memory_type"] = _infer_memory_type(str(out.get("kind") or "unknown"))
    if not isinstance(out.get("source"), str) or not out["source"].strip():
        out["source"] = str(out.get("kind") or "unknown")
    try:
        out["confidence"] = float(out.get("confidence", 1.0))
    except (TypeError, ValueError):
        out["confidence"] = 1.0
    out["confidence"] = min(1.0, max(0.0, float(out["confidence"])))
    if not isinstance(out.get("created_by"), str) or not out["created_by"].strip():
        out["created_by"] = str(out.get("agent_id") or "shared")
    if not isinstance(out.get("trace_ref"), dict):
        out["trace_ref"] = _build_trace_ref(out)
    tags = out.get("tags")
    if tags is not None and not isinstance(tags, list):
        out["tags"] = None
    return out


def _infer_memory_type(kind: str) -> str:
    procedural_kinds = {"lesson", "policy", "procedure", "playbook"}
    semantic_kinds = {"semantic_case", "knowledge", "fact", "example", "few_shot"}
    if kind in procedural_kinds:
        return "procedural"
    if kind in semantic_kinds:
        return "semantic"
    return "episodic"


def _build_trace_ref(entry: dict[str, Any]) -> dict[str, Any]:
    trace_ref: dict[str, Any] = {}
    if isinstance(entry.get("run_id"), str) and entry["run_id"].strip():
        trace_ref["run_id"] = entry["run_id"]
    if isinstance(entry.get("entry_id"), str) and entry["entry_id"].strip():
        trace_ref["entry_id"] = entry["entry_id"]
    return trace_ref


@dataclass(frozen=True)
class MemoryEntry:
    schema_version: str
    entry_id: str
    ts_ms: int
    agent_id: str
    scope: str
    kind: str
    memory_type: str
    content: dict[str, Any]
    source: str
    confidence: float
    created_by: str
    trace_ref: dict[str, Any]
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
            "memory_type": self.memory_type,
            "content": dict(self.content),
            "source": self.source,
            "confidence": float(self.confidence),
            "created_by": self.created_by,
            "trace_ref": dict(self.trace_ref),
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
            memory_type=str(nd.get("memory_type")),
            content=nd.get("content") if isinstance(nd.get("content"), dict) else {},
            source=str(nd.get("source")),
            confidence=float(nd.get("confidence")),
            created_by=str(nd.get("created_by")),
            trace_ref=nd.get("trace_ref") if isinstance(nd.get("trace_ref"), dict) else {},
            tags=nd.get("tags") if isinstance(nd.get("tags"), list) else None,
            session_id=nd.get("session_id") if isinstance(nd.get("session_id"), str) else None,
            run_id=nd.get("run_id") if isinstance(nd.get("run_id"), str) else None,
        )
