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

