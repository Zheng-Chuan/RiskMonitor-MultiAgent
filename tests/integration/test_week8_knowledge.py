from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


@pytest.mark.asyncio
async def test_week8_ingest_and_search_similar_alerts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from riskmonitor_multiagent.data_access import alerts_repository
    from riskmonitor_multiagent.knowledge.ingest import ingest_recent_alerts
    from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore
    from riskmonitor_multiagent.services import alert_rules_service
    from riskmonitor_multiagent.tools.mcp_tools import search_similar_alerts

    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("CHROMA_COLLECTION", "test-knowledge-integration")

    desk = f"Week8 Knowledge Desk {pytest.__version__}"
    request_id = f"week8-kb-{pytest.__version__}"

    alerts = alert_rules_service.evaluate_desk_delta_breach(
        desk=desk,
        abs_delta=1500000.0,
        threshold=1000000.0,
        request_id=request_id,
    )
    alerts_repository.save_alerts_batch(alerts)

    ingest_result = ingest_recent_alerts(limit=50, desk=desk)
    assert ingest_result["ingested"] >= 1

    store = ChromaVectorStore()
    res = store.query_alerts(query_text=f"{desk} breach", top_k=5)
    assert len(res) >= 1
    assert res[0].metadata.get("desk") == desk

    tool_out = search_similar_alerts(query=f"{desk} breach", top_k=3, ctx=None)
    assert tool_out["top_k"] == 3
    assert isinstance(tool_out["results"], list)
    assert len(tool_out["results"]) >= 1
