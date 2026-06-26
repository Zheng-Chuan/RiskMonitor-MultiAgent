"""PersistenceBackend 单元测试.

使用内存 SQLite 引擎模拟 MySQL, 不依赖真实 Docker 服务.
测试覆盖:
1. 记忆条目落盘和加载
2. 批量落盘
3. Skill 落盘和加载
4. ON DUPLICATE KEY UPDATE (同 entry_id 重复写入)
5. 按 run_id 过滤加载
6. 按 kind 过滤加载
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from typing import Any

import pytest
from sqlalchemy import create_engine, text as sa_text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


# ==================== SQLite Mock Engine ====================


def _create_sqlite_engine() -> Engine:
    """创建内存 SQLite 引擎并初始化表结构.

    使用 StaticPool 共享连接, 确保跨线程 (asyncio.to_thread) 时
    访问同一个 in-memory 数据库.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # SQLite 使用 TEXT 代替 JSON, 不支持 ON DUPLICATE KEY UPDATE
    # 所以测试使用 INSERT OR REPLACE 模拟 upsert
    with engine.begin() as conn:
        conn.execute(sa_text("""
            CREATE TABLE memory_store (
                entry_id TEXT PRIMARY KEY,
                ts_ms INTEGER NOT NULL,
                agent_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                kind TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT,
                confidence REAL DEFAULT 0.0,
                created_by TEXT,
                trace_ref TEXT,
                tags TEXT,
                session_id TEXT,
                run_id TEXT,
                ttl_tier TEXT DEFAULT 'short_term'
            )
        """))
        conn.execute(sa_text("""
            CREATE TABLE skill_store (
                skill_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                tags TEXT,
                applicable_conditions TEXT,
                steps TEXT,
                failure_boundary TEXT,
                confidence REAL DEFAULT 0.5,
                write_origin TEXT DEFAULT 'auto',
                status TEXT DEFAULT 'active',
                usage_count INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 0.0,
                revision_history TEXT,
                source_run_id TEXT,
                source_agent_id TEXT,
                created_at INTEGER,
                updated_at INTEGER
            )
        """))
    return engine


class MockPersistenceBackend:
    """使用 SQLite 后端的 Mock PersistenceBackend.

    继承 PersistenceBackend, 注入 SQLite 引擎.
    使用 INSERT OR REPLACE 代替 ON DUPLICATE KEY UPDATE.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _get_engine(self) -> Engine:
        return self._engine

    async def persist_memory_entry(self, entry: dict[str, Any]) -> bool:
        from riskmonitor_multiagent.memory.persistence_backend import _build_memory_row
        row = _build_memory_row(entry)
        if not row["entry_id"]:
            return False
        sql = sa_text("""
            INSERT OR REPLACE INTO memory_store (
                entry_id, ts_ms, agent_id, scope, kind, memory_type,
                content, source, confidence, created_by, trace_ref,
                tags, session_id, run_id, ttl_tier
            ) VALUES (
                :entry_id, :ts_ms, :agent_id, :scope, :kind, :memory_type,
                :content, :source, :confidence, :created_by, :trace_ref,
                :tags, :session_id, :run_id, :ttl_tier
            )
        """)
        import asyncio
        try:
            await asyncio.to_thread(self._execute_write, sql, row)
            return True
        except Exception:
            return False

    async def batch_persist_memory(self, entries: list[dict[str, Any]]) -> int:
        from riskmonitor_multiagent.memory.persistence_backend import _build_memory_row
        rows = [_build_memory_row(e) for e in entries]
        rows = [r for r in rows if r["entry_id"]]
        if not rows:
            return 0
        sql = sa_text("""
            INSERT OR REPLACE INTO memory_store (
                entry_id, ts_ms, agent_id, scope, kind, memory_type,
                content, source, confidence, created_by, trace_ref,
                tags, session_id, run_id, ttl_tier
            ) VALUES (
                :entry_id, :ts_ms, :agent_id, :scope, :kind, :memory_type,
                :content, :source, :confidence, :created_by, :trace_ref,
                :tags, :session_id, :run_id, :ttl_tier
            )
        """)
        import asyncio
        try:
            count = await asyncio.to_thread(self._execute_batch_write, sql, rows)
            return count
        except Exception:
            return 0

    async def load_memory_entries(
        self, *, run_id: str | None = None, agent_id: str | None = None,
        kinds: list[str] | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        from riskmonitor_multiagent.memory.persistence_backend import _parse_memory_row
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
        sql = sa_text(f"""
            SELECT entry_id, ts_ms, agent_id, scope, kind, memory_type,
                   content, source, confidence, created_by, trace_ref,
                   tags, session_id, run_id
            FROM memory_store
            WHERE {where_clause}
            ORDER BY ts_ms DESC
            LIMIT :limit
        """)
        import asyncio
        try:
            rows = await asyncio.to_thread(self._execute_read, sql, params)
            return [_parse_memory_row(dict(r)) for r in rows]
        except Exception:
            return []

    async def persist_skill(self, skill: dict[str, Any]) -> bool:
        from riskmonitor_multiagent.memory.persistence_backend import _build_skill_row
        row = _build_skill_row(skill)
        if not row["skill_id"]:
            return False
        sql = sa_text("""
            INSERT OR REPLACE INTO skill_store (
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
        """)
        import asyncio
        try:
            await asyncio.to_thread(self._execute_write, sql, row)
            return True
        except Exception:
            return False

    async def load_skills(self, *, status: str | None = None) -> list[dict[str, Any]]:
        from riskmonitor_multiagent.memory.persistence_backend import _parse_skill_row
        conditions: list[str] = []
        params: dict[str, Any] = {}
        if status is not None:
            conditions.append("status = :status")
            params["status"] = status
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = sa_text(f"""
            SELECT skill_id, name, tags, applicable_conditions, steps,
                   failure_boundary, confidence, write_origin, status,
                   usage_count, success_rate, revision_history,
                   source_run_id, source_agent_id, created_at, updated_at
            FROM skill_store
            WHERE {where_clause}
            ORDER BY updated_at DESC
        """)
        import asyncio
        try:
            rows = await asyncio.to_thread(self._execute_read, sql, params)
            return [_parse_skill_row(dict(r)) for r in rows]
        except Exception:
            return []

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        self._engine = None

    def _execute_write(self, sql, params: dict[str, Any]) -> None:
        engine = self._get_engine()
        with engine.begin() as conn:
            conn.execute(sql, params)

    def _execute_batch_write(self, sql, rows: list[dict[str, Any]]) -> int:
        engine = self._get_engine()
        with engine.begin() as conn:
            for row in rows:
                conn.execute(sql, row)
        return len(rows)

    def _execute_read(self, sql, params: dict[str, Any]) -> list:
        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(sql, params).mappings()
            return result.fetchall()


# ==================== Fixtures ====================


@pytest.fixture
def mock_backend():
    """创建 MockPersistenceBackend."""
    engine = _create_sqlite_engine()
    backend = MockPersistenceBackend(engine)
    yield backend


def _make_memory_entry(**kwargs) -> dict[str, Any]:
    """构造测试用 MemoryEntry."""
    base: dict[str, Any] = {
        "entry_id": "mem_test_001",
        "ts_ms": 1700000000000,
        "agent_id": "critic",
        "scope": "shared",
        "kind": "lesson",
        "memory_type": "procedural",
        "content": {"text": "测试记忆条目", "task_id": "task-1"},
        "source": "critic_final_review",
        "confidence": 0.95,
        "created_by": "critic",
        "trace_ref": {"run_id": "run_test_001"},
        "tags": ["lesson", "procedure"],
        "session_id": "session_1",
        "run_id": "run_test_001",
    }
    base.update(kwargs)
    return base


def _make_skill(**kwargs) -> dict[str, Any]:
    """构造测试用 Skill."""
    base: dict[str, Any] = {
        "skill_id": "skill_test001",
        "name": "交易台风险排查",
        "tags": ["risk", "trading"],
        "applicable_conditions": ["延迟异常", "告警触发"],
        "steps": [
            {"description": "查询持仓数据", "expected_outcome": "获取当前持仓"},
            {"description": "核对限额", "expected_outcome": "确认是否超限"},
        ],
        "failure_boundary": "禁止伪造数据",
        "confidence": 0.85,
        "write_origin": "auto",
        "status": "active",
        "usage_count": 0,
        "success_rate": 0.0,
        "revision_history": [],
        "source_run_id": "run_test_001",
        "source_agent_id": "critic",
        "created_at": 1700000000000,
        "updated_at": 1700000000000,
    }
    base.update(kwargs)
    return base


# ==================== 测试: 记忆条目落盘和加载 ====================


@pytest.mark.asyncio
async def test_persist_and_load_memory_entry(mock_backend):
    """测试记忆条目落盘和加载: persist -> load -> 数据一致."""
    entry = _make_memory_entry()
    ok = await mock_backend.persist_memory_entry(entry)
    assert ok is True

    loaded = await mock_backend.load_memory_entries(run_id="run_test_001")
    assert len(loaded) == 1
    result = loaded[0]
    assert result["entry_id"] == "mem_test_001"
    assert result["agent_id"] == "critic"
    assert result["kind"] == "lesson"
    assert result["memory_type"] == "procedural"
    assert result["content"]["text"] == "测试记忆条目"
    assert result["confidence"] == pytest.approx(0.95)
    assert result["run_id"] == "run_test_001"
    assert result["tags"] == ["lesson", "procedure"]


# ==================== 测试: 批量落盘 ====================


@pytest.mark.asyncio
async def test_batch_persist_memory(mock_backend):
    """测试批量落盘: batch_persist -> 全部加载."""
    entries = [
        _make_memory_entry(entry_id=f"mem_batch_{i}", run_id=f"run_batch_{i}")
        for i in range(5)
    ]
    count = await mock_backend.batch_persist_memory(entries)
    assert count == 5

    # 验证每个都能加载
    for i in range(5):
        loaded = await mock_backend.load_memory_entries(run_id=f"run_batch_{i}")
        assert len(loaded) == 1
        assert loaded[0]["entry_id"] == f"mem_batch_{i}"


# ==================== 测试: Skill 落盘和加载 ====================


@pytest.mark.asyncio
async def test_persist_and_load_skill(mock_backend):
    """测试 Skill 落盘和加载: persist_skill -> load_skills -> 数据一致."""
    skill = _make_skill()
    ok = await mock_backend.persist_skill(skill)
    assert ok is True

    loaded = await mock_backend.load_skills()
    assert len(loaded) == 1
    result = loaded[0]
    assert result["skill_id"] == "skill_test001"
    assert result["name"] == "交易台风险排查"
    assert result["tags"] == ["risk", "trading"]
    assert result["confidence"] == pytest.approx(0.85)
    assert result["status"] == "active"
    assert len(result["steps"]) == 2
    assert result["source_run_id"] == "run_test_001"


# ==================== 测试: ON DUPLICATE KEY UPDATE ====================


@pytest.mark.asyncio
async def test_upsert_same_entry_id(mock_backend):
    """测试同一 entry_id 重复写入 -> 更新而非报错."""
    entry1 = _make_memory_entry(content={"text": "原始内容"})
    ok1 = await mock_backend.persist_memory_entry(entry1)
    assert ok1 is True

    # 用相同 entry_id 写入新内容
    entry2 = _make_memory_entry(content={"text": "更新后内容"})
    ok2 = await mock_backend.persist_memory_entry(entry2)
    assert ok2 is True

    loaded = await mock_backend.load_memory_entries(run_id="run_test_001")
    assert len(loaded) == 1
    assert loaded[0]["content"]["text"] == "更新后内容"


@pytest.mark.asyncio
async def test_upsert_same_skill_id(mock_backend):
    """测试同一 skill_id 重复写入 -> 更新而非报错."""
    skill1 = _make_skill(confidence=0.5)
    ok1 = await mock_backend.persist_skill(skill1)
    assert ok1 is True

    skill2 = _make_skill(confidence=0.9, status="deprecated")
    ok2 = await mock_backend.persist_skill(skill2)
    assert ok2 is True

    loaded = await mock_backend.load_skills()
    assert len(loaded) == 1
    assert loaded[0]["confidence"] == pytest.approx(0.9)
    assert loaded[0]["status"] == "deprecated"


# ==================== 测试: 按 run_id 过滤加载 ====================


@pytest.mark.asyncio
async def test_load_by_run_id(mock_backend):
    """测试按 run_id 过滤加载: 只返回指定 run_id 的条目."""
    # 写入 3 个条目, 2 个属于 run_A, 1 个属于 run_B
    await mock_backend.persist_memory_entry(_make_memory_entry(entry_id="mem_a1", run_id="run_A"))
    await mock_backend.persist_memory_entry(_make_memory_entry(entry_id="mem_a2", run_id="run_A"))
    await mock_backend.persist_memory_entry(_make_memory_entry(entry_id="mem_b1", run_id="run_B"))

    loaded_a = await mock_backend.load_memory_entries(run_id="run_A")
    assert len(loaded_a) == 2
    entry_ids = {e["entry_id"] for e in loaded_a}
    assert entry_ids == {"mem_a1", "mem_a2"}

    loaded_b = await mock_backend.load_memory_entries(run_id="run_B")
    assert len(loaded_b) == 1
    assert loaded_b[0]["entry_id"] == "mem_b1"


# ==================== 测试: 按 kind 过滤加载 ====================


@pytest.mark.asyncio
async def test_load_by_kind(mock_backend):
    """测试按 kind 过滤加载: 只返回指定 kind 的条目."""
    await mock_backend.persist_memory_entry(_make_memory_entry(
        entry_id="mem_lesson1", kind="lesson", run_id="run_K",
    ))
    await mock_backend.persist_memory_entry(_make_memory_entry(
        entry_id="mem_plan1", kind="plan", run_id="run_K",
    ))
    await mock_backend.persist_memory_entry(_make_memory_entry(
        entry_id="mem_lesson2", kind="lesson", run_id="run_K",
    ))

    loaded_lessons = await mock_backend.load_memory_entries(run_id="run_K", kinds=["lesson"])
    assert len(loaded_lessons) == 2
    for entry in loaded_lessons:
        assert entry["kind"] == "lesson"

    loaded_plans = await mock_backend.load_memory_entries(run_id="run_K", kinds=["plan"])
    assert len(loaded_plans) == 1
    assert loaded_plans[0]["kind"] == "plan"

    loaded_both = await mock_backend.load_memory_entries(run_id="run_K", kinds=["lesson", "plan"])
    assert len(loaded_both) == 3


# ==================== 测试: 空数据处理 ====================


@pytest.mark.asyncio
async def test_load_empty(mock_backend):
    """测试从空表加载返回空列表."""
    loaded = await mock_backend.load_memory_entries(run_id="nonexistent")
    assert loaded == []


@pytest.mark.asyncio
async def test_batch_persist_empty(mock_backend):
    """测试批量落盘空列表."""
    count = await mock_backend.batch_persist_memory([])
    assert count == 0


@pytest.mark.asyncio
async def test_load_skills_empty(mock_backend):
    """测试从空表加载 Skill."""
    loaded = await mock_backend.load_skills()
    assert loaded == []


# ==================== 测试: 按 status 过滤 Skill ====================


@pytest.mark.asyncio
async def test_load_skills_by_status(mock_backend):
    """测试按 status 过滤加载 Skill."""
    await mock_backend.persist_skill(_make_skill(skill_id="skill_active", status="active"))
    await mock_backend.persist_skill(_make_skill(skill_id="skill_deprecated", status="deprecated"))
    await mock_backend.persist_skill(_make_skill(skill_id="skill_archived", status="archived"))

    active = await mock_backend.load_skills(status="active")
    assert len(active) == 1
    assert active[0]["skill_id"] == "skill_active"

    deprecated = await mock_backend.load_skills(status="deprecated")
    assert len(deprecated) == 1
    assert deprecated[0]["skill_id"] == "skill_deprecated"

    all_skills = await mock_backend.load_skills()
    assert len(all_skills) == 3


# ==================== 测试: JSON 字段序列化 ====================


@pytest.mark.asyncio
async def test_json_fields_roundtrip(mock_backend):
    """测试 JSON 字段 (content, trace_ref, tags) 序列化往返."""
    entry = _make_memory_entry(
        content={"nested": {"deep": {"value": 42}}, "list": [1, 2, 3]},
        trace_ref={"run_id": "run_test", "step_id": "s1", "command_id": "cmd-1"},
        tags=["tag1", "tag2", "中文标签"],
    )
    await mock_backend.persist_memory_entry(entry)

    loaded = await mock_backend.load_memory_entries(run_id="run_test_001")
    assert len(loaded) == 1
    result = loaded[0]
    assert result["content"]["nested"]["deep"]["value"] == 42
    assert result["content"]["list"] == [1, 2, 3]
    assert result["trace_ref"]["step_id"] == "s1"
    assert result["trace_ref"]["command_id"] == "cmd-1"
    assert "中文标签" in result["tags"]


@pytest.mark.asyncio
async def test_skill_json_fields_roundtrip(mock_backend):
    """测试 Skill JSON 字段 (tags, applicable_conditions, steps, revision_history) 往返."""
    skill = _make_skill(
        tags=["风险", "交易台"],
        applicable_conditions=["延迟 > 100ms", "告警数量 > 5"],
        steps=[
            {"description": "查询持仓", "expected_outcome": "返回持仓数据"},
            {"description": "计算敞口", "expected_outcome": "返回敞口金额"},
        ],
        revision_history=[{"run_id": "run_1", "action": "created", "changes": ["新增步骤"]}],
    )
    await mock_backend.persist_skill(skill)

    loaded = await mock_backend.load_skills()
    assert len(loaded) == 1
    result = loaded[0]
    assert "风险" in result["tags"]
    assert "延迟 > 100ms" in result["applicable_conditions"]
    assert len(result["steps"]) == 2
    assert result["steps"][0]["description"] == "查询持仓"
    assert result["revision_history"][0]["action"] == "created"
