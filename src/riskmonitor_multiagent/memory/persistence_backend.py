"""MySQL 持久化后端.

Phase 6 Checkpoint 14.4.1: 记忆永久化存储层.

将 Redis 中的关键记忆数据异步落盘到 MySQL,
提供 fire-and-forget 落盘和恢复能力.

设计约束:
- 使用 data_access/mysql_engine.py 的同步 SQLAlchemy Engine,
  通过 asyncio.to_thread 包装为异步调用.
- INSERT ON DUPLICATE KEY UPDATE 实现 upsert 语义.
- JSON 字段在写入前序列化为字符串, 读取时反序列化.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from riskmonitor_multiagent.data_access.mysql_engine import get_engine

logger = logging.getLogger(__name__)

# 关键数据类型: 需要立即落盘的 kind
_CRITICAL_KINDS = {"lesson", "semantic_case"}

# 长期记忆的 memory_type
_LONG_TERM_TYPES = {"semantic", "procedural"}


def _serialize_json(value: Any) -> str | None:
    """将 Python 对象序列化为 JSON 字符串, None 返回 None."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _deserialize_json(value: Any) -> Any:
    """将 JSON 字符串反序列化为 Python 对象."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


def _build_memory_row(entry: dict[str, Any]) -> dict[str, Any]:
    """将 MemoryEntry dict 映射为 memory_store 表行."""
    kind = str(entry.get("kind") or "unknown")
    memory_type = str(entry.get("memory_type") or "episodic")
    ttl_tier = "long_term" if kind in _CRITICAL_KINDS or memory_type in _LONG_TERM_TYPES else "short_term"
    return {
        "entry_id": str(entry.get("entry_id") or ""),
        "ts_ms": int(entry.get("ts_ms") or 0),
        "agent_id": str(entry.get("agent_id") or "shared"),
        "scope": str(entry.get("scope") or "shared"),
        "kind": kind,
        "memory_type": memory_type,
        "content": _serialize_json(entry.get("content") or {}),
        "source": str(entry.get("source") or ""),
        "confidence": float(entry.get("confidence") or 0.0),
        "created_by": str(entry.get("created_by") or ""),
        "trace_ref": _serialize_json(entry.get("trace_ref")),
        "tags": _serialize_json(entry.get("tags")),
        "session_id": entry.get("session_id"),
        "run_id": entry.get("run_id"),
        "ttl_tier": ttl_tier,
    }


def _parse_memory_row(row: dict[str, Any]) -> dict[str, Any]:
    """将 memory_store 表行映射回 MemoryEntry dict."""
    return {
        "entry_id": row.get("entry_id"),
        "ts_ms": int(row.get("ts_ms") or 0),
        "agent_id": row.get("agent_id") or "shared",
        "scope": row.get("scope") or "shared",
        "kind": row.get("kind") or "unknown",
        "memory_type": row.get("memory_type") or "episodic",
        "content": _deserialize_json(row.get("content")) or {},
        "source": row.get("source") or "",
        "confidence": float(row.get("confidence") or 0.0),
        "created_by": row.get("created_by") or "",
        "trace_ref": _deserialize_json(row.get("trace_ref")),
        "tags": _deserialize_json(row.get("tags")),
        "session_id": row.get("session_id"),
        "run_id": row.get("run_id"),
    }


def _build_skill_row(skill: dict[str, Any]) -> dict[str, Any]:
    """将 Skill dict 映射为 skill_store 表行."""
    return {
        "skill_id": str(skill.get("skill_id") or ""),
        "name": str(skill.get("name") or ""),
        "tags": _serialize_json(skill.get("tags") or []),
        "applicable_conditions": _serialize_json(skill.get("applicable_conditions") or []),
        "steps": _serialize_json(skill.get("steps") or []),
        "failure_boundary": str(skill.get("failure_boundary") or ""),
        "confidence": float(skill.get("confidence") or 0.5),
        "write_origin": str(skill.get("write_origin") or "auto"),
        "status": str(skill.get("status") or "active"),
        "usage_count": int(skill.get("usage_count") or 0),
        "success_rate": float(skill.get("success_rate") or 0.0),
        "revision_history": _serialize_json(skill.get("revision_history") or []),
        "source_run_id": skill.get("source_run_id"),
        "source_agent_id": skill.get("source_agent_id"),
        "created_at": int(skill.get("created_at") or 0),
        "updated_at": int(skill.get("updated_at") or 0),
    }


def _parse_skill_row(row: dict[str, Any]) -> dict[str, Any]:
    """将 skill_store 表行映射回 Skill dict."""
    return {
        "skill_id": row.get("skill_id"),
        "name": row.get("name") or "",
        "tags": _deserialize_json(row.get("tags")) or [],
        "applicable_conditions": _deserialize_json(row.get("applicable_conditions")) or [],
        "steps": _deserialize_json(row.get("steps")) or [],
        "failure_boundary": row.get("failure_boundary") or "",
        "confidence": float(row.get("confidence") or 0.5),
        "write_origin": row.get("write_origin") or "auto",
        "status": row.get("status") or "active",
        "usage_count": int(row.get("usage_count") or 0),
        "success_rate": float(row.get("success_rate") or 0.0),
        "revision_history": _deserialize_json(row.get("revision_history")) or [],
        "source_run_id": row.get("source_run_id"),
        "source_agent_id": row.get("source_agent_id"),
        "created_at": int(row.get("created_at") or 0),
        "updated_at": int(row.get("updated_at") or 0),
    }


class PersistenceBackend:
    """MySQL 持久化后端, 异步落盘关键记忆数据."""

    def __init__(self, mysql_url: str | None = None, *, engine: Engine | None = None) -> None:
        """初始化持久化后端.

        Args:
            mysql_url: 可选的 MySQL 连接 URL (未使用, 保留兼容).
            engine: 可选的外部 Engine 实例 (测试注入用).
        """
        self._engine: Engine | None = engine
        self._mysql_url = mysql_url

    def _get_engine(self) -> Engine:
        """获取 SQLAlchemy Engine 实例."""
        if self._engine is not None:
            return self._engine
        return get_engine()

    # ==================== Memory 持久化 ====================

    async def persist_memory_entry(self, entry: dict[str, Any]) -> bool:
        """将 MemoryEntry 落盘到 MySQL. INSERT ON DUPLICATE KEY UPDATE.

        Args:
            entry: 归一化后的记忆条目

        Returns:
            True 表示成功, False 表示失败
        """
        row = _build_memory_row(entry)
        if not row["entry_id"]:
            logger.warning("persist_memory_entry: entry_id is empty, skipping")
            return False

        sql = text("""
            INSERT INTO memory_store (
                entry_id, ts_ms, agent_id, scope, kind, memory_type,
                content, source, confidence, created_by, trace_ref,
                tags, session_id, run_id, ttl_tier
            ) VALUES (
                :entry_id, :ts_ms, :agent_id, :scope, :kind, :memory_type,
                :content, :source, :confidence, :created_by, :trace_ref,
                :tags, :session_id, :run_id, :ttl_tier
            )
            ON DUPLICATE KEY UPDATE
                ts_ms = VALUES(ts_ms),
                agent_id = VALUES(agent_id),
                scope = VALUES(scope),
                kind = VALUES(kind),
                memory_type = VALUES(memory_type),
                content = VALUES(content),
                source = VALUES(source),
                confidence = VALUES(confidence),
                created_by = VALUES(created_by),
                trace_ref = VALUES(trace_ref),
                tags = VALUES(tags),
                session_id = VALUES(session_id),
                run_id = VALUES(run_id),
                ttl_tier = VALUES(ttl_tier)
        """)

        try:
            await asyncio.to_thread(self._execute_write, sql, row)
            return True
        except Exception:
            logger.exception("persist_memory_entry failed: entry_id=%s", row["entry_id"])
            return False

    async def batch_persist_memory(self, entries: list[dict[str, Any]]) -> int:
        """批量落盘记忆条目.

        Args:
            entries: 记忆条目列表

        Returns:
            成功落盘的条目数
        """
        if not entries:
            return 0

        rows = [_build_memory_row(e) for e in entries]
        rows = [r for r in rows if r["entry_id"]]
        if not rows:
            return 0

        sql = text("""
            INSERT INTO memory_store (
                entry_id, ts_ms, agent_id, scope, kind, memory_type,
                content, source, confidence, created_by, trace_ref,
                tags, session_id, run_id, ttl_tier
            ) VALUES (
                :entry_id, :ts_ms, :agent_id, :scope, :kind, :memory_type,
                :content, :source, :confidence, :created_by, :trace_ref,
                :tags, :session_id, :run_id, :ttl_tier
            )
            ON DUPLICATE KEY UPDATE
                ts_ms = VALUES(ts_ms),
                agent_id = VALUES(agent_id),
                scope = VALUES(scope),
                kind = VALUES(kind),
                memory_type = VALUES(memory_type),
                content = VALUES(content),
                source = VALUES(source),
                confidence = VALUES(confidence),
                created_by = VALUES(created_by),
                trace_ref = VALUES(trace_ref),
                tags = VALUES(tags),
                session_id = VALUES(session_id),
                run_id = VALUES(run_id),
                ttl_tier = VALUES(ttl_tier)
        """)

        try:
            count = await asyncio.to_thread(self._execute_batch_write, sql, rows)
            return count
        except Exception:
            logger.exception("batch_persist_memory failed: count=%d", len(rows))
            return 0

    async def load_memory_entries(
        self,
        *,
        run_id: str | None = None,
        agent_id: str | None = None,
        kinds: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """从 MySQL 加载记忆条目.

        Args:
            run_id: 可选的运行 ID 过滤
            agent_id: 可选的 Agent ID 过滤
            kinds: 可选的 kind 过滤
            limit: 返回条数上限

        Returns:
            记忆条目列表
        """
        conditions: list[str] = []
        params: dict[str, Any] = {"limit": limit}

        if run_id is not None:
            conditions.append("run_id = :run_id")
            params["run_id"] = run_id
        if agent_id is not None:
            conditions.append("agent_id = :agent_id")
            params["agent_id"] = agent_id
        if kinds:
            placeholders = ", ".join(f":kind_{i}" for i in range(len(kinds)))
            conditions.append(f"kind IN ({placeholders})")
            for i, k in enumerate(kinds):
                params[f"kind_{i}"] = k

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = text(f"""
            SELECT entry_id, ts_ms, agent_id, scope, kind, memory_type,
                   content, source, confidence, created_by, trace_ref,
                   tags, session_id, run_id
            FROM memory_store
            WHERE {where_clause}
            ORDER BY ts_ms DESC
            LIMIT :limit
        """)

        try:
            rows = await asyncio.to_thread(self._execute_read, sql, params)
            return [_parse_memory_row(dict(r)) for r in rows]
        except Exception:
            logger.exception("load_memory_entries failed")
            return []

    # ==================== Skill 持久化 ====================

    async def persist_skill(self, skill: dict[str, Any]) -> bool:
        """将 Skill 落盘到 MySQL. INSERT ON DUPLICATE KEY UPDATE.

        Args:
            skill: 归一化后的 Skill dict

        Returns:
            True 表示成功
        """
        row = _build_skill_row(skill)
        if not row["skill_id"]:
            logger.warning("persist_skill: skill_id is empty, skipping")
            return False

        sql = text("""
            INSERT INTO skill_store (
                skill_id, name, tags, applicable_conditions, steps,
                failure_boundary, confidence, write_origin, status,
                usage_count, success_rate, revision_history,
                source_run_id, source_agent_id, created_at, updated_at
            ) VALUES (
                :skill_id, :name, :tags, :applicable_conditions, :steps,
                :failure_boundary, :confidence, :write_origin, :status,
                :usage_count, :success_rate, :revision_history,
                :source_run_id, :source_agent_id, :created_at, :updated_at
            )
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                tags = VALUES(tags),
                applicable_conditions = VALUES(applicable_conditions),
                steps = VALUES(steps),
                failure_boundary = VALUES(failure_boundary),
                confidence = VALUES(confidence),
                write_origin = VALUES(write_origin),
                status = VALUES(status),
                usage_count = VALUES(usage_count),
                success_rate = VALUES(success_rate),
                revision_history = VALUES(revision_history),
                source_run_id = VALUES(source_run_id),
                source_agent_id = VALUES(source_agent_id),
                updated_at = VALUES(updated_at)
        """)

        try:
            await asyncio.to_thread(self._execute_write, sql, row)
            return True
        except Exception:
            logger.exception("persist_skill failed: skill_id=%s", row["skill_id"])
            return False

    async def load_skills(self, *, status: str | None = None) -> list[dict[str, Any]]:
        """从 MySQL 加载所有 Skill.

        Args:
            status: 可选的状态过滤

        Returns:
            Skill dict 列表
        """
        conditions: list[str] = []
        params: dict[str, Any] = {}

        if status is not None:
            conditions.append("status = :status")
            params["status"] = status

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = text(f"""
            SELECT skill_id, name, tags, applicable_conditions, steps,
                   failure_boundary, confidence, write_origin, status,
                   usage_count, success_rate, revision_history,
                   source_run_id, source_agent_id, created_at, updated_at
            FROM skill_store
            WHERE {where_clause}
            ORDER BY updated_at DESC
        """)

        try:
            rows = await asyncio.to_thread(self._execute_read, sql, params)
            return [_parse_skill_row(dict(r)) for r in rows]
        except Exception:
            logger.exception("load_skills failed")
            return []

    # ==================== 健康检查 ====================

    async def health_check(self) -> bool:
        """检查 MySQL 连接.

        Returns:
            True 表示连接正常
        """
        try:
            engine = self._get_engine()
            await asyncio.to_thread(
                lambda: engine.connect().exec_driver_sql("SELECT 1").close()
            )
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """关闭后端资源."""
        # Engine 由 mysql_engine 模块管理, 这里不主动 dispose.
        self._engine = None

    # ==================== 内部同步方法 ====================

    def _execute_write(self, sql, params: dict[str, Any]) -> None:
        """执行单条写入 (同步, 在 to_thread 中调用)."""
        engine = self._get_engine()
        with engine.begin() as conn:
            conn.execute(sql, params)

    def _execute_batch_write(self, sql, rows: list[dict[str, Any]]) -> int:
        """执行批量写入 (同步, 在 to_thread 中调用)."""
        engine = self._get_engine()
        with engine.begin() as conn:
            for row in rows:
                conn.execute(sql, row)
        return len(rows)

    def _execute_read(self, sql, params: dict[str, Any]) -> list:
        """执行读取 (同步, 在 to_thread 中调用)."""
        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(sql, params).mappings()
            return result.fetchall()
