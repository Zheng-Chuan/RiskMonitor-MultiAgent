import os
import sys
import time
import uuid

import pytest

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def _in_compose_network() -> bool:
    return os.getenv("MYSQL_HOST", "").strip() == "mysql"


def _chroma_host_port() -> tuple[str, int]:
    host = os.getenv("CHROMA_HOST", "").strip()
    port = os.getenv("CHROMA_PORT", "").strip()
    if host and port.isdigit():
        return host, int(port)
    if _in_compose_network():
        return "chroma", 8000
    return "localhost", 8001


def _wait_chroma(timeout_s: float = 20.0) -> None:
    from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore

    started = time.monotonic()
    while time.monotonic() - started < timeout_s:
        try:
            store = ChromaVectorStore(collection=f"it-{uuid.uuid4().hex[:8]}")
            store.query_alerts(query_text="health_check", top_k=1)
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("chroma_not_ready")


def test_chroma_http_client_can_upsert_and_query_alerts(monkeypatch):
    tmp = Path(os.getenv("TMPDIR", "/tmp"))
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp / f"chroma-it-{uuid.uuid4().hex[:8]}"))

    from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore

    col = f"it-alerts-{uuid.uuid4().hex[:8]}"
    store = ChromaVectorStore(collection=col)
    doc_id = f"a-{uuid.uuid4().hex[:8]}"
    store.upsert_alert(alert_id=doc_id, document="alert desk Equity Derivatives severity WARNING test", metadata={"alert_id": doc_id, "desk": "Equity Derivatives"})
    out = store.query_alerts(query_text="Equity Derivatives WARNING", top_k=3)
    assert isinstance(out, list)
    assert any(r.doc_id == doc_id for r in out)
