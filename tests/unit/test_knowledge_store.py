from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def test_sqlite_vector_store_query_returns_best_match(tmp_path: Path) -> None:
    from riskmonitor_multiagent.knowledge.store import SqliteVectorStore

    db_path = tmp_path / "kb.sqlite"
    store = SqliteVectorStore(path=db_path)
    store.init()

    store.upsert(
        doc_id="a1",
        doc_type="alert",
        content="desk Equity Derivatives severity CRITICAL delta breach",
        metadata={"alert_id": "a1", "desk": "Equity Derivatives"},
        updated_at_ms=1,
    )
    store.upsert(
        doc_id="a2",
        doc_type="alert",
        content="desk Fixed Income severity INFO ok",
        metadata={"alert_id": "a2", "desk": "Fixed Income"},
        updated_at_ms=1,
    )

    res = store.query(query_text="Equity Derivatives breach", top_k=1, doc_type="alert")
    assert len(res) == 1
    assert res[0].doc_id == "a1"
    assert res[0].metadata.get("desk") == "Equity Derivatives"


def test_embed_text_empty_returns_empty_vector() -> None:
    from riskmonitor_multiagent.knowledge.store import embed_text

    assert embed_text("") == {}

