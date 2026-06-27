from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from riskmonitor_multiagent.memory.redis_backend import RedisBackend


class _FakePipeline:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def lpush(self, *args: object) -> "_FakePipeline":
        self.calls.append(("lpush", args))
        return self

    def ltrim(self, *args: object) -> "_FakePipeline":
        self.calls.append(("ltrim", args))
        return self

    def expire(self, *args: object) -> "_FakePipeline":
        self.calls.append(("expire", args))
        return self

    async def execute(self) -> list[bool]:
        return [True]


@pytest.mark.asyncio
async def test_redis_backend_ensure_connected_and_list_ops(monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = _FakePipeline()
    redis_obj = MagicMock()
    redis_obj.pipeline.return_value = pipeline
    redis_obj.lrange = AsyncMock(return_value=["a", "b"])

    from_url = AsyncMock(return_value=redis_obj)
    monkeypatch.setattr("riskmonitor_multiagent.memory.redis_backend.redis.from_url", from_url)

    backend = RedisBackend("redis://demo")
    first = await backend.ensure_connected()
    second = await backend.ensure_connected()
    assert first is second
    assert from_url.await_count == 1

    await backend.append_to_list("memory:key", '{"x":1}', max_len=5, ttl=60)
    assert pipeline.calls == [
        ("lpush", ("memory:key", '{"x":1}')),
        ("ltrim", ("memory:key", 0, 4)),
        ("expire", ("memory:key", 60)),
    ]
    assert await backend.list_from_key("memory:key", limit=2) == ["a", "b"]


@pytest.mark.asyncio
async def test_redis_backend_run_context_roundtrip_and_update(monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict[tuple[str, str], object] = {}

    async def hset(key: str, *args, mapping: dict[str, object] | None = None) -> bool:
        if mapping is not None:
            for field, value in mapping.items():
                store[(key, field)] = value
            return True
        if len(args) == 2:
            field, value = args
            store[(key, str(field))] = value
        return True

    async def hget(key: str, field: str):
        return store.get((key, field))

    async def hkeys(key: str):
        return [field for (bucket, field), _ in store.items() if bucket == key]

    redis_obj = MagicMock()
    redis_obj.hset = hset
    redis_obj.hget = hget
    redis_obj.hkeys = hkeys
    redis_obj.close = AsyncMock()
    redis_obj.ping = AsyncMock(return_value=True)

    backend = RedisBackend("redis://demo")
    backend._redis = redis_obj

    await backend.save_run_context("run-2", "event-1", {"step": 1})
    payload = await backend.get_run_context("run-2")
    assert payload is not None
    assert payload["run_id"] == "run-2"
    assert payload["data"] == {"step": 1}

    await backend.update_run_context("run-2", {"step": 2, "new": True})
    payload = await backend.get_run_context("run-2")
    assert payload is not None
    assert payload["data"] == {"step": 2, "new": True}

    latest = await backend.get_context_by_event("event-1", latest=True)
    earliest = await backend.get_context_by_event("event-1", latest=False)
    assert latest == earliest == payload

    with pytest.raises(ValueError, match="Run context not found"):
        await backend.update_run_context("missing", {"x": 1})

    store[("context:bad", "payload")] = "{bad-json}"
    assert await backend.get_run_context("bad") is None


@pytest.mark.asyncio
async def test_redis_backend_summary_close_and_health_check() -> None:
    store: dict[tuple[str, str], object] = {}

    async def hset(key: str, mapping: dict[str, object]) -> bool:
        for field, value in mapping.items():
            store[(key, field)] = value
        return True

    async def hget(key: str, field: str):
        return store.get((key, field))

    redis_obj = MagicMock()
    redis_obj.hset = hset
    redis_obj.hget = hget
    redis_obj.close = AsyncMock()
    redis_obj.ping = AsyncMock(return_value=True)

    backend = RedisBackend("redis://demo")
    backend._redis = redis_obj

    await backend.upsert_run_summary(run_id="run-s", summary={"text": "done"})
    assert await backend.get_run_summary("run-s") == {"text": "done"}
    store[("summary:bad", "payload")] = "{bad-json}"
    assert await backend.get_run_summary("bad") is None

    assert await backend.health_check() is True
    redis_obj.ping = AsyncMock(side_effect=RuntimeError("down"))
    assert await backend.health_check() is False

    await backend.close()
    redis_obj.close.assert_awaited_once()
    assert backend._redis is None
