"""
Skill 契约定义.

定义 Skill 数据结构、校验和归一化逻辑.
参考 contracts/memory_entry.py 的模式.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any


SKILL_SCHEMA_VERSION = "skill.v1"
SKILL_STATUS_VALUES = {"active", "deprecated", "archived"}
WRITE_ORIGIN_VALUES = {"auto", "manual", "revision"}


def _is_non_empty_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def new_skill_id() -> str:
    """生成新的 Skill ID: skill_ + uuid4 hex[:12]."""
    return f"skill_{uuid.uuid4().hex[:12]}"


def normalize_skill(d: dict[str, Any]) -> dict[str, Any]:
    """填充默认值并做类型转换.

    不做合法性校验, 仅保证结构完整.
    """
    out = dict(d) if isinstance(d, dict) else {}
    now_ms = int(time.time() * 1000)

    out.setdefault("schema_version", SKILL_SCHEMA_VERSION)
    out.setdefault("skill_id", new_skill_id())
    out.setdefault("name", "")
    out.setdefault("tags", [])
    out.setdefault("applicable_conditions", [])
    out.setdefault("steps", [])
    out.setdefault("failure_boundary", "")
    out.setdefault("confidence", 0.5)
    out.setdefault("write_origin", "auto")
    out.setdefault("status", "active")
    out.setdefault("created_at", now_ms)
    out.setdefault("updated_at", now_ms)
    out.setdefault("usage_count", 0)
    out.setdefault("success_rate", 0.0)
    out.setdefault("revision_history", [])
    out.setdefault("source_run_id", None)
    out.setdefault("source_agent_id", None)

    # ---- 类型转换 ----
    out["schema_version"] = str(out.get("schema_version") or SKILL_SCHEMA_VERSION)
    out["skill_id"] = str(out.get("skill_id") or new_skill_id())
    out["name"] = str(out.get("name") or "")
    out["failure_boundary"] = str(out.get("failure_boundary") or "")

    # tags -> list[str]
    tags = out.get("tags")
    if not isinstance(tags, list):
        out["tags"] = []
    else:
        out["tags"] = [str(t) for t in tags]

    # applicable_conditions -> list[str]
    conds = out.get("applicable_conditions")
    if not isinstance(conds, list):
        out["applicable_conditions"] = []
    else:
        out["applicable_conditions"] = [str(c) for c in conds]

    # steps -> list[dict]
    steps = out.get("steps")
    if not isinstance(steps, list):
        out["steps"] = []
    else:
        out["steps"] = [s if isinstance(s, dict) else {} for s in steps]

    # revision_history -> list[dict]
    rev = out.get("revision_history")
    if not isinstance(rev, list):
        out["revision_history"] = []
    else:
        out["revision_history"] = [r if isinstance(r, dict) else {} for r in rev]

    # confidence -> float [0, 1]
    try:
        out["confidence"] = float(out.get("confidence", 0.5))
    except (TypeError, ValueError):
        out["confidence"] = 0.5
    out["confidence"] = min(1.0, max(0.0, out["confidence"]))

    # success_rate -> float [0, 1]
    try:
        out["success_rate"] = float(out.get("success_rate", 0.0))
    except (TypeError, ValueError):
        out["success_rate"] = 0.0
    out["success_rate"] = min(1.0, max(0.0, out["success_rate"]))

    # created_at / updated_at -> int
    try:
        out["created_at"] = int(out.get("created_at", now_ms))
    except (TypeError, ValueError):
        out["created_at"] = now_ms
    try:
        out["updated_at"] = int(out.get("updated_at", now_ms))
    except (TypeError, ValueError):
        out["updated_at"] = now_ms

    # usage_count -> int
    try:
        out["usage_count"] = int(out.get("usage_count", 0))
    except (TypeError, ValueError):
        out["usage_count"] = 0

    out["write_origin"] = str(out.get("write_origin") or "auto")
    out["status"] = str(out.get("status") or "active")

    # source_run_id / source_agent_id -> str | None
    if not isinstance(out.get("source_run_id"), str) or not out["source_run_id"].strip():
        out["source_run_id"] = None
    if not isinstance(out.get("source_agent_id"), str) or not out["source_agent_id"].strip():
        out["source_agent_id"] = None

    return out


def validate_skill(d: dict[str, Any]) -> dict[str, Any]:
    """校验并归一化 Skill.

    非法输入抛出 ValueError.
    """
    if not isinstance(d, dict):
        raise ValueError("skill must be a dict")

    nd = normalize_skill(d)
    errors: list[str] = []

    if nd.get("schema_version") != SKILL_SCHEMA_VERSION:
        errors.append("unsupported_schema_version")
    if not _is_non_empty_str(nd.get("skill_id")):
        errors.append("bad_skill_id")
    if not _is_non_empty_str(nd.get("name")):
        errors.append("bad_name")
    if nd.get("status") not in SKILL_STATUS_VALUES:
        errors.append("unsupported_status")
    if nd.get("write_origin") not in WRITE_ORIGIN_VALUES:
        errors.append("unsupported_write_origin")

    confidence = nd.get("confidence")
    if not isinstance(confidence, (int, float)) or float(confidence) < 0.0 or float(confidence) > 1.0:
        errors.append("bad_confidence")

    steps = nd.get("steps")
    if not isinstance(steps, list):
        errors.append("bad_steps")
    else:
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or not _is_non_empty_str(step.get("description")):
                errors.append(f"bad_step_{i}")

    if not isinstance(nd.get("created_at"), int):
        errors.append("bad_created_at")
    if not isinstance(nd.get("updated_at"), int):
        errors.append("bad_updated_at")
    if not isinstance(nd.get("usage_count"), int) or int(nd.get("usage_count", 0)) < 0:
        errors.append("bad_usage_count")

    success_rate = nd.get("success_rate")
    if not isinstance(success_rate, (int, float)) or float(success_rate) < 0.0 or float(success_rate) > 1.0:
        errors.append("bad_success_rate")

    if not isinstance(nd.get("revision_history"), list):
        errors.append("bad_revision_history")

    if errors:
        raise ValueError(f"Invalid skill: {', '.join(errors)}")
    return nd


@dataclass(frozen=True)
class Skill:
    """Skill 不可变数据结构."""

    schema_version: str
    skill_id: str
    name: str
    tags: list[str]
    applicable_conditions: list[str]
    steps: list[dict[str, Any]]
    failure_boundary: str
    confidence: float
    write_origin: str
    status: str
    created_at: int
    updated_at: int
    usage_count: int
    success_rate: float
    revision_history: list[dict[str, Any]]
    source_run_id: str | None = None
    source_agent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "skill_id": self.skill_id,
            "name": self.name,
            "tags": list(self.tags),
            "applicable_conditions": list(self.applicable_conditions),
            "steps": [dict(s) for s in self.steps],
            "failure_boundary": self.failure_boundary,
            "confidence": float(self.confidence),
            "write_origin": self.write_origin,
            "status": self.status,
            "created_at": int(self.created_at),
            "updated_at": int(self.updated_at),
            "usage_count": int(self.usage_count),
            "success_rate": float(self.success_rate),
            "revision_history": [dict(r) for r in self.revision_history],
            "source_run_id": self.source_run_id,
            "source_agent_id": self.source_agent_id,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Skill":
        nd = normalize_skill(d)
        return Skill(
            schema_version=str(nd.get("schema_version")),
            skill_id=str(nd.get("skill_id")),
            name=str(nd.get("name")),
            tags=nd.get("tags") if isinstance(nd.get("tags"), list) else [],
            applicable_conditions=(
                nd.get("applicable_conditions")
                if isinstance(nd.get("applicable_conditions"), list)
                else []
            ),
            steps=nd.get("steps") if isinstance(nd.get("steps"), list) else [],
            failure_boundary=str(nd.get("failure_boundary")),
            confidence=float(nd.get("confidence")),
            write_origin=str(nd.get("write_origin")),
            status=str(nd.get("status")),
            created_at=int(nd.get("created_at")),
            updated_at=int(nd.get("updated_at")),
            usage_count=int(nd.get("usage_count")),
            success_rate=float(nd.get("success_rate")),
            revision_history=(
                nd.get("revision_history")
                if isinstance(nd.get("revision_history"), list)
                else []
            ),
            source_run_id=(
                nd.get("source_run_id") if isinstance(nd.get("source_run_id"), str) else None
            ),
            source_agent_id=(
                nd.get("source_agent_id") if isinstance(nd.get("source_agent_id"), str) else None
            ),
        )
