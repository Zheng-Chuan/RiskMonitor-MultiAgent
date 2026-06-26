"""记忆持久化集成测试.

测试场景:
1. Redis 重启模拟: 写入 Redis → 落盘 MySQL → 清空内存 → 从 MySQL 恢复 → 数据一致
2. Skill 恢复: 创建 Skill → 落盘 → 重建 SkillStore → 从 MySQL 恢复 → Skill 可检索
3. 异步落盘不阻塞: 记录 append 耗时 → 确认落盘是异步的
4. 关键数据优先落盘: lesson 和 long_term_experience 立即落盘

依赖: Docker 服务 (MySQL + Redis)
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text as sa_text

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


# ==================== Fixtures ====================


@pytest.fixture
def persistence_backend(real_db_engine):
    """创建使用真实 MySQL 的 PersistenceBackend."""
    from riskmonitor_multiagent.memory.persistence_backend import PersistenceBackend
    backend = PersistenceBackend(engine=real_db_engine)
    yield backend
    # 清理测试数据
    try:
        with real_db_engine.begin() as conn:
            conn.execute(sa_text("DELETE FROM memory_store WHERE entry_id LIKE 'test_integ_%'"))
            conn.execute(sa_text("DELETE FROM skill_store WHERE skill_id LIKE 'test_integ_%'"))
    except Exception:
        pass


@pytest.fixture
async def memory_store_with_persistence(real_db_engine):
    """创建集成了真实持久化后端的 MemoryStore."""
    from riskmonitor_multiagent.memory import MemoryConfig, MemoryStore
    from riskmonitor_multiagent.memory.persistence_backend import PersistenceBackend

    store = MemoryStore(config=MemoryConfig(redis_url="redis://localhost:6379/0"))
    backend = PersistenceBackend(engine=real_db_engine)
    store._set_persistence(backend)

    # 确保连接
    await store._ensure_connected()

    yield store

    # 清理 Redis
    try:
        r = await store._ensure_connected()
        await r.flushdb()
    except Exception:
        pass
    # 清理 MySQL
    try:
        with real_db_engine.begin() as conn:
            conn.execute(sa_text("DELETE FROM memory_store WHERE entry_id LIKE 'test_integ_%'"))
    except Exception:
        pass
    # 关闭连接 (redis 5.x 的 close() 可能被废弃, 用 aclose)
    try:
        if hasattr(store._backend._redis, "aclose"):
            await store._backend._redis.aclose()
        elif store._backend._redis is not None:
            await store._backend._redis.close()
    except Exception:
        pass
    store._redis = None
    store._backend._redis = None


@pytest.fixture
async def skill_store_with_persistence(real_db_engine):
    """创建集成了真实持久化后端的 SkillStore."""
    from riskmonitor_multiagent.skills import SkillStore
    from riskmonitor_multiagent.memory.persistence_backend import PersistenceBackend

    store = SkillStore()
    backend = PersistenceBackend(engine=real_db_engine)
    store._set_persistence(backend)

    yield store

    # 清理
    try:
        with real_db_engine.begin() as conn:
            conn.execute(sa_text("DELETE FROM skill_store WHERE skill_id LIKE 'test_integ_%'"))
    except Exception:
        pass


# ==================== 辅助函数 ====================


def _make_lesson_entry(run_id: str = "test_integ_run_001") -> dict[str, Any]:
    """构造测试用 lesson 记忆条目."""
    return {
        "entry_id": "test_integ_lesson_001",
        "ts_ms": int(time.time() * 1000),
        "agent_id": "critic",
        "scope": "shared",
        "kind": "lesson",
        "memory_type": "procedural",
        "content": {"text": "集成测试: lesson 内容", "task_id": "task-1"},
        "source": "critic_final_review",
        "confidence": 0.9,
        "created_by": "critic",
        "trace_ref": {"run_id": run_id},
        "tags": ["lesson", "procedure"],
        "session_id": "test_session_1",
        "run_id": run_id,
    }


def _make_semantic_entry(run_id: str = "test_integ_run_001") -> dict[str, Any]:
    """构造测试用 semantic_case 记忆条目."""
    return {
        "entry_id": "test_integ_semantic_001",
        "ts_ms": int(time.time() * 1000),
        "agent_id": "critic",
        "scope": "shared",
        "kind": "semantic_case",
        "memory_type": "semantic",
        "content": {"text": "集成测试: 语义经验", "decision_pattern": "先查持仓再查限额"},
        "source": "critic_confidence_policy",
        "confidence": 0.85,
        "created_by": "critic",
        "trace_ref": {"run_id": run_id},
        "tags": ["experience", "few_shot"],
        "session_id": "test_session_1",
        "run_id": run_id,
    }


def _make_test_skill(**kwargs) -> dict[str, Any]:
    """构造测试用 Skill."""
    base: dict[str, Any] = {
        "skill_id": "test_integ_skill_001",
        "name": "集成测试 Skill",
        "tags": ["risk", "integration"],
        "applicable_conditions": ["延迟异常"],
        "steps": [
            {"description": "查询持仓", "expected_outcome": "获取持仓数据"},
        ],
        "failure_boundary": "禁止伪造",
        "confidence": 0.8,
        "source_run_id": "test_integ_run_001",
        "source_agent_id": "critic",
    }
    base.update(kwargs)
    return base


# ==================== 测试 1: Redis 重启模拟 ====================


@pytest.mark.asyncio
async def test_redis_restart_recovery(memory_store_with_persistence, real_db_engine):
    """Redis 重启模拟: 写入 Redis → 落盘 MySQL → 清空内存 → 从 MySQL 恢复 → 数据一致."""
    store = memory_store_with_persistence
    run_id = "test_integ_run_001"

    # 1. 写入记忆条目 (lesson 是关键数据, 会自动落盘)
    lesson_entry = _make_lesson_entry(run_id)
    await store.append(lesson_entry)

    # 等待异步落盘完成
    await asyncio.sleep(0.5)

    # 2. 显式 flush 落盘
    flushed = await store.flush_to_persistence()
    assert flushed >= 1

    # 3. 验证 MySQL 中有数据
    with real_db_engine.connect() as conn:
        rows = conn.execute(
            sa_text("SELECT entry_id FROM memory_store WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).fetchall()
        assert len(rows) >= 1

    # 4. 清空 Redis (模拟重启)
    r = await store._ensure_connected()
    await r.flushdb()

    # 5. 从 MySQL 恢复
    restored = await store.restore_from_persistence(run_id=run_id)
    assert restored >= 1

    # 6. 验证恢复后数据一致
    loaded = await store.list_recent(
        agent_id="critic", scope="shared", run_id=run_id, limit=10,
    )
    assert len(loaded) >= 1
    # 找到 lesson 条目
    lessons = [e for e in loaded if e.get("kind") == "lesson"]
    assert len(lessons) >= 1
    assert lessons[0]["content"]["text"] == "集成测试: lesson 内容"
    assert lessons[0]["entry_id"] == "test_integ_lesson_001"


# ==================== 测试 2: Skill 恢复 ====================


@pytest.mark.asyncio
async def test_skill_recovery(skill_store_with_persistence, real_db_engine):
    """Skill 恢复: 创建 Skill → 落盘 → 重建 SkillStore → 从 MySQL 恢复 → Skill 可检索."""
    store = skill_store_with_persistence

    # 1. 创建 Skill (会自动异步落盘)
    skill_data = _make_test_skill()
    created = await store.create(skill_data)
    assert created["skill_id"] == "test_integ_skill_001"

    # 等待异步落盘
    await asyncio.sleep(0.5)

    # 2. 显式 flush
    flushed = await store.flush_to_persistence()
    assert flushed >= 1

    # 3. 验证 MySQL 中有数据
    with real_db_engine.connect() as conn:
        rows = conn.execute(
            sa_text("SELECT skill_id FROM skill_store WHERE skill_id = :sid"),
            {"sid": "test_integ_skill_001"},
        ).fetchall()
        assert len(rows) == 1

    # 4. 重建 SkillStore (模拟重启)
    from riskmonitor_multiagent.skills import SkillStore
    from riskmonitor_multiagent.memory.persistence_backend import PersistenceBackend
    new_store = SkillStore()
    new_store._set_persistence(PersistenceBackend(engine=real_db_engine))

    # 5. 从 MySQL 恢复
    restored = await new_store.restore_from_persistence()
    assert restored >= 1

    # 6. 验证 Skill 可检索
    fetched = await new_store.get("test_integ_skill_001")
    assert fetched is not None
    assert fetched["name"] == "集成测试 Skill"
    assert fetched["tags"] == ["risk", "integration"]
    assert fetched["confidence"] == pytest.approx(0.8)

    # 7. 验证语义检索可用
    hits = await new_store.search("集成测试", limit=5)
    assert len(hits) >= 1
    assert any(h["skill_id"] == "test_integ_skill_001" for h in hits)


# ==================== 测试 3: 异步落盘不阻塞 ====================


@pytest.mark.asyncio
async def test_append_does_not_block_on_persistence(memory_store_with_persistence):
    """异步落盘不阻塞: 记录 append 耗时 → 确认落盘是异步的."""
    store = memory_store_with_persistence

    # 记录 append 耗时 (应该在毫秒级, 因为落盘是 fire-and-forget)
    entry = _make_lesson_entry("test_integ_perf_001")
    entry["entry_id"] = "test_integ_perf_001"

    start = time.monotonic()
    await store.append(entry)
    elapsed = time.monotonic() - start

    # append 应该快速完成 (< 100ms), 因为 MySQL 落盘是异步的
    assert elapsed < 0.5, f"append took {elapsed:.3f}s, expected < 0.5s"

    # 等待异步落盘完成
    await asyncio.sleep(1.0)

    # 验证数据确实落盘了
    loaded = await store.persistence.load_memory_entries(
        run_id="test_integ_perf_001", limit=10,
    )
    assert len(loaded) >= 1
    assert loaded[0]["entry_id"] == "test_integ_perf_001"


# ==================== 测试 4: 关键数据优先落盘 ====================


@pytest.mark.asyncio
async def test_critical_data_immediate_persistence(memory_store_with_persistence, real_db_engine):
    """关键数据优先落盘: lesson 和 long_term_experience 立即落盘."""
    store = memory_store_with_persistence
    run_id = "test_integ_critical_001"

    # 写入 lesson (关键数据)
    lesson_entry = _make_lesson_entry(run_id)
    lesson_entry["entry_id"] = "test_integ_critical_lesson"
    await store.append(lesson_entry)

    # 写入 semantic_case (关键数据)
    semantic_entry = _make_semantic_entry(run_id)
    semantic_entry["entry_id"] = "test_integ_critical_semantic"
    await store.append(semantic_entry)

    # 等待异步落盘完成
    await asyncio.sleep(1.0)

    # 验证两个关键数据都已落盘
    loaded = await store.persistence.load_memory_entries(run_id=run_id, limit=10)
    entry_ids = {e["entry_id"] for e in loaded}
    assert "test_integ_critical_lesson" in entry_ids
    assert "test_integ_critical_semantic" in entry_ids

    # 验证数据内容正确
    lessons = [e for e in loaded if e["kind"] == "lesson"]
    assert len(lessons) >= 1
    assert lessons[0]["content"]["text"] == "集成测试: lesson 内容"

    semantics = [e for e in loaded if e["kind"] == "semantic_case"]
    assert len(semantics) >= 1
    assert semantics[0]["content"]["decision_pattern"] == "先查持仓再查限额"


# ==================== 测试 5: persist_run_artifacts 落盘 ====================


@pytest.mark.asyncio
async def test_persist_run_artifacts_persists_lesson_and_experience(
    memory_store_with_persistence, real_db_engine,
):
    """persist_run_artifacts 中的 lesson 和 long_term_experience 触发立即落盘."""
    from riskmonitor_multiagent.memory import MemoryConfig, MemoryStore
    from riskmonitor_multiagent.memory.persistence_backend import PersistenceBackend

    store = memory_store_with_persistence
    run_id = "test_integ_artifacts_001"

    # 直接调用 persist_run_artifacts
    result = await store.persist_run_artifacts(
        run_id=run_id,
        task={"task_id": "task-artifacts", "session_id": "s-artifacts",
              "payload": {"content": "分析风险并给出结论"}},
        final_output={"summary": "完成", "receipt_command_ids": ["cmd-1"]},
        critic_final={
            "ok": True,
            "confidence": 0.95,
            "issues": [],
            "evidence": {"receipt_command_ids": ["cmd-1"]},
            "run_summary": {"text": "完成总结", "key_points": ["先查持仓", "再查限额"]},
        },
    )

    # 等待异步落盘完成
    await asyncio.sleep(1.0)

    # 验证 lesson 和 long_term_experience 都已落盘
    loaded = await store.persistence.load_memory_entries(run_id=run_id, limit=10)
    kinds = {e["kind"] for e in loaded}
    assert "lesson" in kinds
    assert "semantic_case" in kinds

    # 验证 persist_run_artifacts 返回了正确的结构
    assert result.get("lesson_entry") is not None
    assert result.get("long_term_experience") is not None
    assert result.get("memory_policy", {}).get("accepted") is True


# ==================== 测试 6: Skill update 后落盘 ====================


@pytest.mark.asyncio
async def test_skill_update_persists_changes(skill_store_with_persistence, real_db_engine):
    """Skill update 后变更异步落盘到 MySQL."""
    store = skill_store_with_persistence

    # 创建
    created = await store.create(_make_test_skill())
    await asyncio.sleep(0.5)

    # 更新
    updated = await store.update(created["skill_id"], {"confidence": 0.95, "tags": ["updated"]})
    await asyncio.sleep(0.5)

    # 验证 MySQL 中的数据是更新后的
    with real_db_engine.connect() as conn:
        row = conn.execute(
            sa_text("SELECT confidence, name FROM skill_store WHERE skill_id = :sid"),
            {"sid": "test_integ_skill_001"},
        ).mappings().fetchone()
        assert row is not None
        assert float(row["confidence"]) == pytest.approx(0.95)
        assert row["name"] == "集成测试 Skill"
