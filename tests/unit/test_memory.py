import json
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
    assert entry.get("memory_type") == "episodic"
    assert entry.get("source") == "plan"
    assert entry.get("created_by") == "orchestrator"
    assert isinstance(entry.get("trace_ref"), dict)


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
    """测试 MemoryStore 使用 mock Redis."""
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
    """测试 MemoryStore 的 run context 功能."""
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
    """测试 MemoryStore 的 run summary 功能."""
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


def test_memory_store_semantic_enabled_by_default(monkeypatch):
    """测试 MemoryStore 默认启用内置语义搜索."""
    monkeypatch.delenv("PAGE_INDEX_ENABLED", raising=False)
    monkeypatch.delenv("SEMANTIC_MEMORY_ENABLED", raising=False)
    from riskmonitor_multiagent.memory import MemoryStore

    store = MemoryStore()
    assert store._config.enable_semantic_memory is True


@pytest.mark.asyncio
async def test_memory_store_retrieve_for_planning_summarizes_recent_hits():
    """测试 plan 前 retrieval 会汇总近期记忆."""
    from riskmonitor_multiagent.memory import MemoryStore

    _store_data = {}
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
    mock_redis.ping = AsyncMock(return_value=True)

    store = MemoryStore()
    store._redis = mock_redis

    await store.append(
        {
            "agent_id": "orchestrator",
            "scope": "shared",
            "kind": "plan",
            "session_id": "s_plan",
            "content": {"text": "上次同类任务先查交易台再查告警"},
        }
    )
    await store.append(
        {
            "agent_id": "critic",
            "scope": "shared",
            "kind": "semantic_case",
            "memory_type": "semantic",
            "session_id": "s_plan",
            "content": {
                "text": "历史 lesson 显示 延迟异常应先复用排查路径再输出建议",
                "decision_pattern": "先引用 lesson -> 再核对延迟 -> 最后给建议",
                "failure_boundary": ["不要伪造历史 lesson"],
                "applicable_conditions": ["延迟异常"],
                "evidence_refs": ["bootstrap:memory"],
            },
        }
    )
    summary = await store.retrieve_for_planning(
        task={"task_id": "t1", "session_id": "s_plan", "payload": {"content": "查询交易台风险"}},
        intent={"primary_intent_type": "query_positions"},
        limit=3,
    )

    assert isinstance(summary.get("hits"), list)
    assert len(summary.get("hits") or []) >= 2
    summary_block = summary.get("summary") or {}
    assert summary_block.get("hit_count") >= 2
    assert isinstance(summary_block.get("texts"), list)
    assert "plan" in summary_block.get("texts")[0]
    assert summary_block.get("few_shot_example_count") >= 1
    assert summary_block.get("few_shot_examples")


@pytest.mark.asyncio
async def test_memory_store_semantic_search_returns_real_hits():
    """测试 semantic search 走真实命中路径而不是空实现."""
    from riskmonitor_multiagent.memory import MemoryConfig, MemoryStore

    _store_data = {}
    mock_redis = MagicMock()
    mock_pipeline = MagicMock()

    def mock_lpush(key, value):
        if key not in _store_data:
            _store_data[key] = []
        _store_data[key].insert(0, value)
        return mock_pipeline

    def mock_ltrim(key, start, end):
        if key in _store_data:
            _store_data[key] = _store_data[key][start:end + 1]
        return mock_pipeline

    def mock_expire(key, ttl):
        return mock_pipeline

    mock_pipeline.lpush = mock_lpush
    mock_pipeline.ltrim = mock_ltrim
    mock_pipeline.expire = mock_expire
    mock_pipeline.execute = AsyncMock(return_value=[True, True, True])
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
    mock_redis.ping = AsyncMock(return_value=True)

    store = MemoryStore(
        config=MemoryConfig(
            redis_url="redis://unused",
            enable_semantic_memory=True,
        )
    )
    store._redis = mock_redis

    await store.append(
        {
            "agent_id": "critic",
            "scope": "shared",
            "kind": "semantic_case",
            "memory_type": "semantic",
            "content": {"text": "交易台风险告警需要先核对持仓再核对限额"},
        }
    )

    hits = await store.search_semantic("核对交易台持仓和限额风险", agent_id="orchestrator", limit=3)
    assert len(hits) >= 1
    assert hits[0].get("semantic_score", 0.0) > 0.0
    assert "交易台风险告警" in (hits[0].get("content") or {}).get("text", "")


@pytest.mark.asyncio
async def test_memory_store_build_resume_payload_uses_run_context_and_memory_state():
    """测试 run_id 恢复会复用运行上下文和 memory state."""
    from riskmonitor_multiagent.memory import MemoryStore

    context_payload = {
        "run_id": "run_demo_2",
        "event_id": "task-1",
        "data": {
            "task_graph": {"schema_version": "task_graph.v1", "nodes": [{"step_id": "s1"}], "edges": []},
            "task_graph_execution": {"status": "failed", "failed_step_id": "s2", "completed_steps": ["s1"]},
        },
    }
    summary_payload = {"text": "run summary", "key_points": ["k1"]}
    working_memory_entry = {
        "entry_id": "m1",
        "agent_id": "orchestrator",
        "scope": "shared",
        "kind": "working_memory",
        "memory_type": "episodic",
        "run_id": "run_demo_2",
        "content": {"text": "step s1 completed"},
    }

    mock_redis = MagicMock()

    async def mock_hget(key, field):
        if key == "context:run_demo_2":
            return json.dumps(context_payload, ensure_ascii=False)
        if key == "summary:run_demo_2":
            return json.dumps(summary_payload, ensure_ascii=False)
        return None

    async def mock_lrange(key, start, end):
        if key == "shared:memory":
            return [json.dumps(working_memory_entry, ensure_ascii=False)]
        return []

    mock_redis.hget = mock_hget
    mock_redis.lrange = mock_lrange
    mock_redis.ping = AsyncMock(return_value=True)

    store = MemoryStore()
    store._redis = mock_redis

    payload = await store.build_resume_payload(run_id="run_demo_2")
    assert payload is not None
    assert payload.get("resume_from_step_id") == "s2"
    assert (payload.get("task_graph") or {}).get("schema_version") == "task_graph.v1"
    assert len(payload.get("memory_state") or []) == 1
    assert isinstance(payload.get("shared_memory_board"), list)
    assert isinstance(payload.get("private_memory_state"), dict)
    assert (payload.get("run_summary") or {}).get("text") == "run summary"


@pytest.mark.asyncio
async def test_memory_store_build_resume_payload_prefers_blocked_step_id():
    from riskmonitor_multiagent.memory import MemoryStore

    context_payload = {
        "run_id": "run_demo_blocked",
        "event_id": "task-2",
        "data": {
            "task_graph": {"schema_version": "task_graph.v1", "nodes": [{"step_id": "s1"}], "edges": []},
            "task_graph_execution": {
                "status": "blocked",
                "blocked_step_id": "s3",
                "failed_step_id": "s9",
                "completed_steps": ["s1", "s2"],
            },
        },
    }

    mock_redis = MagicMock()

    async def mock_hget(key, field):
        if key == "context:run_demo_blocked":
            return json.dumps(context_payload, ensure_ascii=False)
        if key == "summary:run_demo_blocked":
            return json.dumps({"text": "blocked summary"}, ensure_ascii=False)
        return None

    async def mock_lrange(key, start, end):
        del key, start, end
        return []

    mock_redis.hget = mock_hget
    mock_redis.lrange = mock_lrange
    mock_redis.ping = AsyncMock(return_value=True)

    store = MemoryStore()
    store._redis = mock_redis

    payload = await store.build_resume_payload(run_id="run_demo_blocked")

    assert payload is not None
    assert payload.get("resume_from_step_id") == "s3"


@pytest.mark.asyncio
async def test_memory_store_record_working_memory_builds_private_and_shared_views():
    from riskmonitor_multiagent.memory import MemoryStore

    _store_data = {}
    mock_redis = MagicMock()
    mock_pipeline = MagicMock()

    def mock_lpush(key, value):
        if key not in _store_data:
            _store_data[key] = []
        _store_data[key].insert(0, value)
        return mock_pipeline

    def mock_ltrim(key, start, end):
        if key in _store_data:
            _store_data[key] = _store_data[key][start:end + 1]
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
    mock_redis.ping = AsyncMock(return_value=True)

    store = MemoryStore()
    store._redis = mock_redis

    await store.record_working_memory(
        run_id="run_private_1",
        task={"task_id": "task-private-1", "session_id": "s-private", "payload": {"content": "排查交易台异常"}},
        trace_entry={"step_id": "s1", "kind": "delegate", "status": "completed", "target_agent": "risk_analyst"},
        node={"step_id": "s1", "target_agent": "risk_analyst"},
        node_result={"output": {"report": "先核对持仓", "confidence": 0.9}},
    )

    private_state = await store.get_private_memory_state(
        run_id="run_private_1",
        agent_ids=["risk_analyst"],
        limit=5,
    )
    board = await store.get_shared_memory_board(run_id="run_private_1", limit=5)

    assert len(private_state.get("risk_analyst") or []) == 1
    private_content = (private_state["risk_analyst"][0].get("content") or {})
    assert private_content.get("role") == "risk_analyst"
    assert private_content.get("next_intended_action") == "handoff_to_next_step"
    assert len(board) == 1
    assert board[0].get("agent_role") == "risk_analyst"
    assert board[0].get("agent_perspective") == "business_risk"


@pytest.mark.asyncio
async def test_memory_store_persist_run_artifacts_builds_long_term_experience():
    from riskmonitor_multiagent.memory import MemoryConfig, MemoryStore

    _store_data = {}
    mock_redis = MagicMock()
    mock_pipeline = MagicMock()

    def mock_lpush(key, value):
        if key not in _store_data:
            _store_data[key] = []
        _store_data[key].insert(0, value)
        return mock_pipeline

    def mock_ltrim(key, start, end):
        if key in _store_data:
            _store_data[key] = _store_data[key][start:end + 1]
        return mock_pipeline

    def mock_expire(key, ttl):
        return mock_pipeline

    mock_pipeline.lpush = mock_lpush
    mock_pipeline.ltrim = mock_ltrim
    mock_pipeline.expire = mock_expire
    mock_pipeline.execute = AsyncMock(return_value=[True, True, True])
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
    mock_redis.hset = AsyncMock(return_value=True)
    mock_redis.ping = AsyncMock(return_value=True)

    store = MemoryStore(
        config=MemoryConfig(
            redis_url="redis://unused",
            enable_semantic_memory=True,
        )
    )
    store._redis = mock_redis

    persisted = await store.persist_run_artifacts(
        run_id="run_exp_1",
        task={"task_id": "task-exp-1", "session_id": "s-exp", "payload": {"content": "分析风险并给出结论"}},
        final_output={"summary": "完成", "receipt_command_ids": ["cmd-1"]},
        critic_final={
            "ok": True,
            "confidence": 0.95,
            "issues": [],
            "evidence": {"receipt_command_ids": ["cmd-1"]},
            "run_summary": {"text": "完成总结", "key_points": ["先查持仓", "再查限额"]},
        },
    )

    experience = persisted.get("long_term_experience") or {}
    assert experience.get("kind") == "semantic_case"
    assert (experience.get("content") or {}).get("decision_pattern")
    assert (persisted.get("memory_policy") or {}).get("accepted") is True
