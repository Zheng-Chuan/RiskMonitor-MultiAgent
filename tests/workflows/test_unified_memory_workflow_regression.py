import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

project_root = Path(__file__).resolve().parents[2]
src_root = project_root / "src"
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))


@pytest.mark.asyncio
async def test_unified_memory_workflow_reuses_shared_plan_and_semantic_case() -> None:
    from riskmonitor_multiagent.memory import MemoryStore

    store_data: dict[str, list[str]] = {}
    mock_redis = MagicMock()
    mock_pipeline = MagicMock()

    def mock_lpush(key: str, value: str):
        store_data.setdefault(key, []).insert(0, value)
        return mock_pipeline

    def mock_ltrim(key: str, start: int, end: int):
        if key in store_data:
            store_data[key] = store_data[key][start:end + 1]
        return mock_pipeline

    def mock_expire(key: str, ttl: int):
        del ttl
        return mock_pipeline

    async def mock_lrange(key: str, start: int, end: int):
        values = store_data.get(key, [])
        return values[start:end + 1] if values else []

    mock_pipeline.lpush = mock_lpush
    mock_pipeline.ltrim = mock_ltrim
    mock_pipeline.expire = mock_expire
    mock_pipeline.execute = AsyncMock(return_value=[True, True, True])
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
    mock_redis.lrange = mock_lrange
    mock_redis.ping = AsyncMock(return_value=True)

    store = MemoryStore()
    store._redis = mock_redis

    await store.append(
        {
            "agent_id": "orchestrator",
            "scope": "shared",
            "kind": "plan",
            "session_id": "workflow-memory",
            "content": {"text": "历史上同类任务先查交易台持仓再看 breach 告警"},
        }
    )
    await store.append(
        {
            "agent_id": "critic",
            "scope": "shared",
            "kind": "semantic_case",
            "memory_type": "semantic",
            "session_id": "workflow-memory",
            "content": {
                "text": "历史 lesson 表明 延迟异常应先复用排查路径再输出建议",
                "decision_pattern": "先引用 lesson -> 再核对延迟 -> 最后给建议",
                "failure_boundary": ["不要伪造历史 lesson"],
                "applicable_conditions": ["延迟异常"],
                "evidence_refs": ["bootstrap:workflow"],
            },
        }
    )

    summary = await store.retrieve_for_planning(
        task={
            "task_id": "workflow-memory-1",
            "session_id": "workflow-memory",
            "payload": {"content": "查询交易台风险并参考历史经验"},
        },
        intent={"primary_intent_type": "query_positions"},
        limit=3,
    )

    summary_block = summary.get("summary") or {}
    assert summary_block.get("hit_count") >= 2
    assert summary_block.get("few_shot_example_count") >= 1
    assert summary_block.get("few_shot_examples")
