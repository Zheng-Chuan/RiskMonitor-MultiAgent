import sys
from pathlib import Path

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
async def test_sql_memory_store_roundtrip(tmp_path):
    from riskmonitor_multiagent.memory.stores import MemoryQuery, SqlMemoryStore

    url = f"sqlite:///{tmp_path / 'mem.sqlite'}"
    store = SqlMemoryStore(url=url)
    await store.append(
        {
            "agent_id": "risk_analyst",
            "scope": "shared",
            "kind": "analysis",
            "session_id": "s1",
            "run_id": "r1",
            "content": {"text": "abc", "n": 1},
            "tags": ["t1"],
        }
    )
    items = await store.list_recent(MemoryQuery(agent_id="risk_analyst", scope="shared", session_id="s1", run_id="r1", limit=10))
    assert isinstance(items, list) and len(items) == 1
    it = items[0]
    assert it.get("agent_id") == "risk_analyst"
    assert it.get("scope") == "shared"
    assert it.get("kind") == "analysis"
    assert it.get("session_id") == "s1"
    assert it.get("run_id") == "r1"
    assert isinstance(it.get("content"), dict)


@pytest.mark.asyncio
async def test_redis_memory_store_private_shared_roundtrip(monkeypatch):
    import sys
    import types

    class _FakePipeline:
        def __init__(self, store):
            self._store = store
            self._ops = []

        def rpush(self, key, value):
            self._ops.append(("rpush", key, value))
            return self

        def ltrim(self, key, start, end):
            self._ops.append(("ltrim", key, start, end))
            return self

        def expire(self, key, _ttl):
            self._ops.append(("expire", key, _ttl))
            return self

        async def execute(self):
            for op in self._ops:
                if op[0] == "rpush":
                    self._store.setdefault(op[1], []).append(op[2])
                elif op[0] == "ltrim":
                    key = op[1]
                    arr = self._store.get(key, [])
                    start = int(op[2])
                    end = int(op[3])
                    if start < 0:
                        start = max(0, len(arr) + start)
                    if end < 0:
                        end = len(arr) + end
                    self._store[key] = arr[start : end + 1]
            return True

    class _FakeRedisClient:
        def __init__(self):
            self._store = {}

        def pipeline(self):
            return _FakePipeline(self._store)

        async def lrange(self, key, start, end):
            arr = self._store.get(key, [])
            s = int(start)
            e = int(end)
            if s < 0:
                s = max(0, len(arr) + s)
            if e < 0:
                e = len(arr) + e
            return arr[s : e + 1]

    class _FakeRedisModule:
        @staticmethod
        def from_url(_url):
            return _FakeRedisClient()

    monkeypatch.setitem(sys.modules, "redis.asyncio", _FakeRedisModule)
    monkeypatch.setitem(sys.modules, "redis", types.SimpleNamespace(asyncio=_FakeRedisModule))

    from riskmonitor_multiagent.memory.stores import MemoryQuery, RedisMemoryStore

    store = RedisMemoryStore(url="redis://fake", max_len=20, ttl_s=3600)
    await store.append({"agent_id": "agent_a", "scope": "private", "kind": "analysis", "session_id": "s1", "content": {"text": "p1"}})
    await store.append({"agent_id": "agent_b", "scope": "private", "kind": "analysis", "session_id": "s1", "content": {"text": "p2"}})
    await store.append({"agent_id": "agent_a", "scope": "shared", "kind": "analysis", "session_id": "s1", "content": {"text": "sh1"}})

    a_private = await store.list_recent(MemoryQuery(agent_id="agent_a", scope="private", session_id="s1", limit=10))
    b_private = await store.list_recent(MemoryQuery(agent_id="agent_b", scope="private", session_id="s1", limit=10))
    shared = await store.list_recent(MemoryQuery(agent_id="agent_a", scope="shared", session_id="s1", limit=10))

    assert len(a_private) == 1 and a_private[0].get("content", {}).get("text") == "p1"
    assert len(b_private) == 1 and b_private[0].get("content", {}).get("text") == "p2"
    assert len(shared) == 1 and shared[0].get("content", {}).get("text") == "sh1"


@pytest.mark.asyncio
async def test_mongo_run_summary_store_upsert_with_mock_client(monkeypatch):
    import sys
    import types

    class _FakeCollection:
        def __init__(self):
            self._docs = {}

        def replace_one(self, filt, doc, upsert=False):
            if upsert and isinstance(filt, dict):
                self._docs[str(filt.get("_id"))] = dict(doc)

        def find_one(self, filt):
            return self._docs.get(str(filt.get("_id")))

    class _FakeDB:
        def __init__(self, coll):
            self._coll = coll

        def __getitem__(self, _name):
            return self._coll

    class _FakeClient:
        def __init__(self, *_args, **_kwargs):
            self._coll = _FakeCollection()

        def __getitem__(self, _db):
            return _FakeDB(self._coll)

    fake_pymongo = types.SimpleNamespace(MongoClient=_FakeClient)
    monkeypatch.setitem(sys.modules, "pymongo", fake_pymongo)

    from riskmonitor_multiagent.memory.mongo_run_summary_store import MongoRunSummaryStore

    store = MongoRunSummaryStore(url="mongodb://fake", db="riskmonitor", collection="run_summaries")
    await store.upsert(
        run_id="run_demo_1",
        summary={"text": "总结", "key_points": ["k1"], "receipt_command_ids": ["c1"], "evidence": {"fields": ["task.payload.content"]}},
    )
    out = await store.get(run_id="run_demo_1")
    assert isinstance(out, dict)
    assert out.get("run_id") == "run_demo_1"
    assert out.get("schema_version") == "run_summary.v1"
    assert isinstance(out.get("evidence"), dict)


def test_unified_memory_semantic_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("MEMORY_ENABLE_SEMANTIC_APPEND", raising=False)
    monkeypatch.setenv("MEMORY_SQLITE_PATH", str(tmp_path / "memory.sqlite"))
    from riskmonitor_multiagent.memory.unified_memory import UnifiedMemory

    mem = UnifiedMemory()
    assert getattr(mem, "_semantic", None) is None
