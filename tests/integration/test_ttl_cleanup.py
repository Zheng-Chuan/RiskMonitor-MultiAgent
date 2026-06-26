"""TTL 清理集成测试.

Phase 6 Checkpoint 14.4.2: 记忆分级 TTL 策略.

测试场景:
1. 过期清理: 创建多个不同 TTL 的 entry → 等待 → cleanup_expired → 只清理过期的
2. 永久记忆不被清理: lesson 和 skill → cleanup 后仍然存在
3. TTL 自动分配: append 不同 kind 的 entry → 检查 TTL 设置正确
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


# ==================== Mock Redis 工厂 ====================


def _create_mock_redis() -> tuple[MagicMock, dict[str, list[str]]]:
    """创建支持 lpush/ltrim/expire/lrange/lrem 的 mock Redis.

    Returns:
        (mock_redis, store_data) 元组
    """
    _store_data: dict[str, list[str]] = {}

    mock_redis = MagicMock()
    mock_pipeline = MagicMock()

    def mock_lpush(key, value):
        if key not in _store_data:
            _store_data[key] = []
        _store_data[key].insert(0, value)
        return mock_pipeline

    def mock_ltrim(key, start, end):
        if key in _store_data:
            arr = _store_data[key]
            _store_data[key] = arr[start:end + 1]
        return mock_pipeline

    def mock_expire(key, ttl):
        return mock_pipeline

    mock_pipeline.lpush = mock_lpush
    mock_pipeline.ltrim = mock_ltrim
    mock_pipeline.expire = mock_expire
    mock_pipeline.execute = AsyncMock(return_value=[True, True, True])
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

    async def mock_lrange(key, start, end):
        arr = _store_data.get(key, [])
        return arr[start:end + 1] if arr else []

    mock_redis.lrange = mock_lrange

    async def mock_lrem(key, count, value):
        if key in _store_data:
            arr = _store_data[key]
            removed = 0
            new_arr = []
            for item in arr:
                if item == value and removed < count:
                    removed += 1
                else:
                    new_arr.append(item)
            _store_data[key] = new_arr
            return removed
        return 0

    mock_redis.lrem = mock_lrem
    mock_redis.hset = AsyncMock(return_value=True)
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.hkeys = AsyncMock(return_value=[])
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.flushdb = AsyncMock(return_value=True)

    return mock_redis, _store_data


def _make_mock_persistence():
    """创建 mock 持久化后端."""
    mock_persist = MagicMock()
    mock_persist.persist_memory_entry = AsyncMock(return_value=True)
    mock_persist.batch_persist_memory = AsyncMock(return_value=0)
    mock_persist.health_check = AsyncMock(return_value=True)
    mock_persist.close = AsyncMock(return_value=None)
    return mock_persist


def _create_store_with_mock(mock_redis, mock_persist=None):
    """创建带 mock Redis 的 MemoryStore."""
    from riskmonitor_multiagent.memory import MemoryConfig, MemoryStore

    store = MemoryStore(
        config=MemoryConfig(
            redis_url="redis://unused",
            enable_semantic_memory=True,
        )
    )
    store._redis = mock_redis
    store._backend._redis = mock_redis
    if mock_persist is not None:
        store._set_persistence(mock_persist)
    return store


# ==================== 测试 1: 过期清理 ====================


@pytest.mark.asyncio
async def test_cleanup_expired_removes_only_expired_entries():
    """测试 cleanup_expired 只清理已过期的 entry."""
    store_mock_redis, _ = _create_mock_redis()
    mock_persist = _make_mock_persistence()
    store = _create_store_with_mock(store_mock_redis, mock_persist)

    now_ms = int(time.time() * 1000)

    # 创建不同 TTL 的 entry
    # 1. ephemeral (working) - 已过期 (48h前)
    await store.append({
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "working",
        "memory_type": "episodic",
        "ts_ms": now_ms - 48 * 3600 * 1000,
        "content": {"text": "expired working"},
    })

    # 2. ephemeral (plan) - 未过期 (1h前)
    await store.append({
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "plan",
        "memory_type": "episodic",
        "ts_ms": now_ms - 1 * 3600 * 1000,
        "content": {"text": "active plan"},
    })

    # 3. short_term (final) - 已过期 (10d前)
    await store.append({
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "final",
        "memory_type": "episodic",
        "ts_ms": now_ms - 10 * 24 * 3600 * 1000,
        "content": {"text": "expired final"},
    })

    # 4. short_term (analysis) - 未过期 (1d前)
    await store.append({
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "analysis",
        "memory_type": "episodic",
        "ts_ms": now_ms - 1 * 24 * 3600 * 1000,
        "content": {"text": "active analysis"},
    })

    # 执行清理 - 使用当前时间
    cleaned = await store.cleanup_expired(now_ms=now_ms)

    # 应该清理 2 个过期条目
    assert cleaned == 2

    # 验证剩余条目
    remaining = await store.list_recent(
        agent_id="orchestrator", scope="shared", limit=50,
    )
    remaining_kinds = {e.get("kind") for e in remaining}
    assert "plan" in remaining_kinds
    assert "analysis" in remaining_kinds
    assert "working" not in remaining_kinds
    assert "final" not in remaining_kinds


# ==================== 测试 2: 永久记忆不被清理 ====================


@pytest.mark.asyncio
async def test_cleanup_expired_preserves_permanent_entries():
    """测试 lesson 和 skill 永久记忆不被清理."""
    store_mock_redis, _ = _create_mock_redis()
    mock_persist = _make_mock_persistence()
    store = _create_store_with_mock(store_mock_redis, mock_persist)

    now_ms = int(time.time() * 1000)
    very_old_ts = now_ms - 365 * 24 * 3600 * 1000  # 1年前

    # 创建永久记忆 - 即使时间很久远也不会过期
    await store.append({
        "agent_id": "critic",
        "scope": "shared",
        "kind": "lesson",
        "memory_type": "procedural",
        "ts_ms": very_old_ts,
        "content": {"text": "重要经验教训"},
    })

    await store.append({
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "semantic_case",
        "memory_type": "semantic",
        "ts_ms": very_old_ts,
        "content": {"text": "重要语义案例"},
    })

    await store.append({
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "skill",
        "ts_ms": very_old_ts,
        "content": {"text": "技能定义"},
    })

    # 创建一个已过期的 ephemeral entry 作为对照
    await store.append({
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "working",
        "memory_type": "episodic",
        "ts_ms": now_ms - 48 * 3600 * 1000,
        "content": {"text": "已过期的工作记忆"},
    })

    # 执行清理
    cleaned = await store.cleanup_expired(now_ms=now_ms)

    # 只清理了 1 个过期条目
    assert cleaned == 1

    # 永久记忆仍然存在
    remaining = await store.list_recent(
        agent_id="orchestrator", scope="shared", limit=50,
    )
    remaining_kinds = {e.get("kind") for e in remaining}
    assert "lesson" in remaining_kinds
    assert "semantic_case" in remaining_kinds
    assert "skill" in remaining_kinds
    assert "working" not in remaining_kinds


@pytest.mark.asyncio
async def test_cleanup_expired_preserves_policy_and_config():
    """测试 policy 和 config 永久记忆不被清理."""
    store_mock_redis, _ = _create_mock_redis()
    mock_persist = _make_mock_persistence()
    store = _create_store_with_mock(store_mock_redis, mock_persist)

    now_ms = int(time.time() * 1000)
    very_old_ts = now_ms - 365 * 24 * 3600 * 1000

    await store.append({
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "policy",
        "ts_ms": very_old_ts,
        "content": {"text": "系统策略"},
    })

    await store.append({
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "config",
        "ts_ms": very_old_ts,
        "content": {"text": "系统配置"},
    })

    # 执行清理
    cleaned = await store.cleanup_expired(now_ms=now_ms)
    assert cleaned == 0

    remaining = await store.list_recent(
        agent_id="orchestrator", scope="shared", limit=50,
    )
    remaining_kinds = {e.get("kind") for e in remaining}
    assert "policy" in remaining_kinds
    assert "config" in remaining_kinds


# ==================== 测试 3: TTL 自动分配 ====================


@pytest.mark.asyncio
async def test_ttl_auto_assigned_on_append_ephemeral():
    """测试 append working kind 时自动设置 EPHEMERAL ttl_tier."""
    store_mock_redis, _ = _create_mock_redis()
    mock_persist = _make_mock_persistence()
    store = _create_store_with_mock(store_mock_redis, mock_persist)

    result = await store.append({
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "working",
        "memory_type": "episodic",
        "content": {"text": "test"},
    })

    assert result.get("ttl_tier") == "ephemeral"


@pytest.mark.asyncio
async def test_ttl_auto_assigned_on_append_short_term():
    """测试 append final kind 时自动设置 SHORT_TERM ttl_tier."""
    store_mock_redis, _ = _create_mock_redis()
    mock_persist = _make_mock_persistence()
    store = _create_store_with_mock(store_mock_redis, mock_persist)

    result = await store.append({
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "final",
        "memory_type": "episodic",
        "content": {"text": "test"},
    })

    assert result.get("ttl_tier") == "short_term"


@pytest.mark.asyncio
async def test_ttl_auto_assigned_on_append_long_term():
    """测试 append lesson kind 时自动设置 LONG_TERM ttl_tier."""
    store_mock_redis, _ = _create_mock_redis()
    mock_persist = _make_mock_persistence()
    store = _create_store_with_mock(store_mock_redis, mock_persist)

    result = await store.append({
        "agent_id": "critic",
        "scope": "shared",
        "kind": "lesson",
        "memory_type": "procedural",
        "content": {"text": "test lesson"},
    })

    assert result.get("ttl_tier") == "long_term"


@pytest.mark.asyncio
async def test_ttl_auto_assigned_on_append_permanent():
    """测试 append skill kind 时自动设置 PERMANENT ttl_tier."""
    store_mock_redis, _ = _create_mock_redis()
    mock_persist = _make_mock_persistence()
    store = _create_store_with_mock(store_mock_redis, mock_persist)

    result = await store.append({
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "skill",
        "content": {"text": "test skill"},
    })

    assert result.get("ttl_tier") == "permanent"


@pytest.mark.asyncio
async def test_ttl_auto_assigned_various_kinds():
    """测试多种 kind 的自动 TTL 分配."""
    store_mock_redis, _ = _create_mock_redis()
    mock_persist = _make_mock_persistence()
    store = _create_store_with_mock(store_mock_redis, mock_persist)

    test_cases = [
        ("plan", "ephemeral"),
        ("step", "ephemeral"),
        ("command", "ephemeral"),
        ("approval", "ephemeral"),
        ("analysis", "short_term"),
        ("task", "short_term"),
        ("lesson", "long_term"),
        ("semantic_case", "long_term"),
        ("few_shot", "long_term"),
        ("skill", "permanent"),
        ("policy", "permanent"),
        ("config", "permanent"),
    ]

    for kind, expected_tier in test_cases:
        result = await store.append({
            "agent_id": "orchestrator",
            "scope": "shared",
            "kind": kind,
            "content": {"text": f"test {kind}"},
        })
        assert result.get("ttl_tier") == expected_tier, (
            f"kind={kind} should have ttl_tier={expected_tier}, got {result.get('ttl_tier')}"
        )


# ==================== 测试: cleanup 不影响运行中任务 ====================


@pytest.mark.asyncio
async def test_cleanup_expired_does_not_affect_private_memory():
    """测试清理 shared memory 不影响 private memory."""
    store_mock_redis, _ = _create_mock_redis()
    mock_persist = _make_mock_persistence()
    store = _create_store_with_mock(store_mock_redis, mock_persist)

    now_ms = int(time.time() * 1000)

    # 在 shared 中创建过期条目
    await store.append({
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "working",
        "memory_type": "episodic",
        "ts_ms": now_ms - 48 * 3600 * 1000,
        "content": {"text": "expired shared"},
    })

    # 在 private 中创建未过期条目
    await store.append(
        {
            "agent_id": "risk_analyst",
            "scope": "private",
            "kind": "private_task_state",
            "memory_type": "episodic",
            "ts_ms": now_ms - 1 * 3600 * 1000,
            "content": {"text": "active private"},
        },
        agent_id="risk_analyst",
        scope="private",
    )

    # 清理
    cleaned = await store.cleanup_expired(now_ms=now_ms)
    assert cleaned == 1

    # private 条目仍在
    private_entries = await store.list_recent(
        agent_id="risk_analyst", scope="private", limit=50,
    )
    assert len(private_entries) == 1
    assert private_entries[0].get("kind") == "private_task_state"


@pytest.mark.asyncio
async def test_cleanup_expired_with_no_entries():
    """测试空列表清理返回 0."""
    store_mock_redis, _ = _create_mock_redis()
    mock_persist = _make_mock_persistence()
    store = _create_store_with_mock(store_mock_redis, mock_persist)

    cleaned = await store.cleanup_expired()
    assert cleaned == 0


@pytest.mark.asyncio
async def test_cleanup_expired_all_current():
    """测试全部未过期时清理返回 0."""
    store_mock_redis, _ = _create_mock_redis()
    mock_persist = _make_mock_persistence()
    store = _create_store_with_mock(store_mock_redis, mock_persist)

    now_ms = int(time.time() * 1000)

    # 创建未过期条目
    await store.append({
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "working",
        "memory_type": "episodic",
        "ts_ms": now_ms,
        "content": {"text": "fresh entry"},
    })

    cleaned = await store.cleanup_expired(now_ms=now_ms)
    assert cleaned == 0
