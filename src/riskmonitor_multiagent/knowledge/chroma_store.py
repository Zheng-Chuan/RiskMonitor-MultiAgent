from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from typing import Any

import chromadb

from riskmonitor_multiagent import config
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def embed_text_dense(text: str, *, dims: int = 256) -> list[float]:
    tokens = _tokenize(text)
    vec = [0.0] * int(dims)
    if not tokens:
        return vec
    for tok in tokens:
        idx = hash(tok) % dims
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0.0:
        return vec
    return [v / norm for v in vec]


@dataclass(frozen=True)
class SimilarDoc:
    doc_id: str
    similarity: float
    document: str
    metadata: dict[str, Any]


class ChromaVectorStore:
    def __init__(
        self,
        *,
        collection: str | None = None,
        dims: int = 256,
    ) -> None:
        self._dims = int(dims)
        self._collection_name = (collection or config.get_chroma_collection()).strip() or config.get_chroma_collection()

    def _client(self):
        persist_dir = config.get_chroma_persist_dir()
        if persist_dir:
            return chromadb.PersistentClient(path=persist_dir)
        return chromadb.HttpClient(host=config.get_chroma_host(), port=config.get_chroma_port())

    def _collection(self):
        client = self._client()
        return client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_alert(self, *, alert_id: str, document: str, metadata: dict[str, Any]) -> None:
        started = time.monotonic()
        col = self._collection()
        embedding = embed_text_dense(document, dims=self._dims)
        col.upsert(
            ids=[alert_id],
            documents=[document],
            metadatas=[metadata],
            embeddings=[embedding],
        )
        observe_ms("rm_chroma_upsert", (time.monotonic() - started) * 1000.0, labels={"collection": self._collection_name})
        inc_counter("rm_chroma_upserts_total", labels={"collection": self._collection_name})

    def query_alerts(self, *, query_text: str, top_k: int = 5) -> list[SimilarDoc]:
        q = (query_text or "").strip()
        if not q:
            return []
        k = max(1, int(top_k))
        started = time.monotonic()
        qemb = embed_text_dense(q, dims=self._dims)
        col = self._collection()
        out = col.query(
            query_embeddings=[qemb],
            n_results=k,
            include=["metadatas", "documents", "distances"],
        )
        ids = (out.get("ids") or [[]])[0]
        docs = (out.get("documents") or [[]])[0]
        metas = (out.get("metadatas") or [[]])[0]
        dists = (out.get("distances") or [[]])[0]

        results: list[SimilarDoc] = []
        for i in range(min(len(ids), len(docs), len(metas), len(dists))):
            doc_id = str(ids[i])
            doc = str(docs[i] or "")
            meta = metas[i] if isinstance(metas[i], dict) else {}
            dist = float(dists[i]) if dists[i] is not None else 1.0
            similarity = max(0.0, min(1.0, 1.0 - dist))
            results.append(SimilarDoc(doc_id=doc_id, similarity=similarity, document=doc, metadata=meta))
        observe_ms("rm_chroma_query", (time.monotonic() - started) * 1000.0, labels={"collection": self._collection_name})
        inc_counter("rm_chroma_queries_total", labels={"collection": self._collection_name})
        inc_counter("rm_chroma_hits_total", labels={"collection": self._collection_name}, value=len(results))
        return results
