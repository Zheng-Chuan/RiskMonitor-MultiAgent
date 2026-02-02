from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def test_chroma_vector_store_query_returns_best_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore

    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("CHROMA_COLLECTION", "test-knowledge-unit")

    store = ChromaVectorStore()
    store.upsert_alert(
        alert_id="a1",
        document="desk Equity Derivatives severity CRITICAL delta breach",
        metadata={"alert_id": "a1", "desk": "Equity Derivatives"},
    )
    store.upsert_alert(
        alert_id="a2",
        document="desk Fixed Income severity INFO ok",
        metadata={"alert_id": "a2", "desk": "Fixed Income"},
    )

    res = store.query_alerts(query_text="Equity Derivatives breach", top_k=1)
    assert len(res) == 1
    assert res[0].doc_id == "a1"
    assert res[0].metadata.get("desk") == "Equity Derivatives"


def test_embed_text_empty_returns_empty_vector() -> None:
    from riskmonitor_multiagent.knowledge.chroma_store import embed_text_dense

    assert embed_text_dense("") == [0.0] * 256
