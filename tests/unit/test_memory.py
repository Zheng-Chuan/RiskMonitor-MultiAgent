import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def test_memory_entry_validate_and_normalize():
    from riskmonitor_multiagent.contracts.memory_entry import MEMORY_ENTRY_SCHEMA_VERSION, normalize_memory_entry, validate_memory_entry

    entry = normalize_memory_entry(
        {
            "agent_id": "orchestrator",
            "scope": "shared",
            "kind": "plan",
            "content": {"text": "hello"},
        }
    )
    ok, errors = validate_memory_entry(entry)
    assert ok is True
    assert errors == []
    assert entry.get("schema_version") == MEMORY_ENTRY_SCHEMA_VERSION
    assert isinstance(entry.get("entry_id"), str) and entry.get("entry_id")
    assert isinstance(entry.get("ts_ms"), int)


def test_memory_entry_scope_must_be_private_or_shared():
    from riskmonitor_multiagent.contracts.memory_entry import normalize_memory_entry, validate_memory_entry

    entry = normalize_memory_entry(
        {
            "agent_id": "orchestrator",
            "scope": "invalid_scope",
            "kind": "plan",
            "content": {"text": "hello"},
        }
    )
    ok, errors = validate_memory_entry(entry)
    assert ok is True
    assert errors == []
    assert entry.get("scope") == "shared"

    bad = {
        "schema_version": "memory_entry.v1",
        "entry_id": "m1",
        "ts_ms": 1,
        "agent_id": "orchestrator",
        "scope": "bad",
        "kind": "plan",
        "content": {"text": "x"},
    }
    ok2, errors2 = validate_memory_entry(bad)
    assert ok2 is False
    assert "unsupported_scope" in errors2


@pytest.mark.asyncio
async def test_memory_store_roundtrip_with_mock_redis():
    """测试 MemoryStore 使用 mock Redis。"""
    from riskmonitor_multiagent.memory import MemoryStore

    # 模拟存储数据
    _store_data = {}

    # 创建 mock Redis
    mock_redis = MagicMock()

    # mock pipeline
    mock_pipeline = MagicMock()

    def mock_lpush(key, value):
        if key not in _store_data:
            _store_data[key] = []
        _store_data[key].insert(0, value)
        return mock_pipeline

    def mock_ltrim(key, start, end):
        if key in _store_data:
            arr = _store_data[key]
            _store_data[key] = arr[start:end+1]
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
        return arr[start:end+1] if arr else []

    mock_redis.lrange = mock_lrange
    mock_redis.hset = AsyncMock(return_value=True)
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.hkeys = AsyncMock(return_value=[])
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.flushdb = AsyncMock(return_value=True)

    store = MemoryStore()
    store._redis = mock_redis

    # 测试 append
    entry = {
        "agent_id": "risk_analyst",
        "scope": "shared",
        "kind": "analysis",
        "session_id": "s1",
        "run_id": "r1",
        "content": {"text": "abc", "n": 1},
        "tags": ["t1"],
    }
    result = await store.append(entry)
    assert result.get("agent_id") == "risk_analyst"

    # 验证数据已存储
    assert "shared:memory" in _store_data

    # 测试 list_recent
    items = await store.list_recent(
        agent_id="risk_analyst",
        scope="shared",
        session_id="s1",
        run_id="r1",
        limit=10,
    )
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0].get("agent_id") == "risk_analyst"


@pytest.mark.asyncio
async def test_memory_store_run_context_with_mock_redis():
    """测试 MemoryStore 的 run context 功能。"""
    from riskmonitor_multiagent.memory import MemoryStore

    # 创建 mock Redis
    mock_redis = MagicMock()
    mock_redis.hset = AsyncMock(return_value=True)
    mock_redis.hget = AsyncMock(return_value='{"run_id": "r1", "event_id": "e1", "data": {"key": "value"}}')
    mock_redis.hkeys = AsyncMock(return_value=["r1"])
    mock_redis.ping = AsyncMock(return_value=True)

    store = MemoryStore()
    store._redis = mock_redis

    # 测试 save_run_context
    await store.save_run_context(
        run_id="r1",
        event_id="e1",
        data={"key": "value"},
    )
    mock_redis.hset.assert_called()

    # 测试 get_run_context
    context = await store.get_run_context(run_id="r1")
    assert context is not None
    assert context.get("run_id") == "r1"


@pytest.mark.asyncio
async def test_memory_store_run_summary_with_mock_redis():
    """测试 MemoryStore 的 run summary 功能。"""
    from riskmonitor_multiagent.memory import MemoryStore

    # 创建 mock Redis
    mock_redis = MagicMock()
    mock_redis.hset = AsyncMock(return_value=True)
    mock_redis.hget = AsyncMock(return_value='{"text": "总结", "key_points": ["k1"], "receipt_command_ids": ["c1"]}')
    mock_redis.ping = AsyncMock(return_value=True)

    store = MemoryStore()
    store._redis = mock_redis

    # 测试 upsert_run_summary
    await store.upsert_run_summary(
        run_id="run_demo_1",
        summary={"text": "总结", "key_points": ["k1"], "receipt_command_ids": ["c1"]},
    )
    mock_redis.hset.assert_called()

    # 测试 get_run_summary
    summary = await store.get_run_summary(run_id="run_demo_1")
    assert summary is not None
    assert summary.get("text") == "总结"


def test_memory_store_semantic_disabled_by_default(monkeypatch):
    """测试 MemoryStore 默认禁用语义搜索。"""
    monkeypatch.delenv("PAGE_INDEX_ENABLED", raising=False)
    from riskmonitor_multiagent.memory import MemoryStore

    store = MemoryStore()
    # PageIndex 应该未初始化
    assert store._page_index is None
