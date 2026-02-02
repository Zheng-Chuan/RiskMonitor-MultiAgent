from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def embed_text(text: str, *, dims: int = 256) -> dict[int, float]:
    tokens = _tokenize(text)
    if not tokens:
        return {}

    counts: dict[int, float] = {}
    for tok in tokens:
        idx = hash(tok) % dims
        counts[idx] = counts.get(idx, 0.0) + 1.0

    norm = math.sqrt(sum(v * v for v in counts.values()))
    if norm <= 0.0:
        return {}
    return {k: v / norm for k, v in counts.items()}


def cosine_sim(a: dict[int, float], b: dict[int, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return float(sum(v * b.get(k, 0.0) for k, v in a.items()))


@dataclass(frozen=True)
class SimilarDoc:
    doc_id: str
    score: float
    content: str
    metadata: dict[str, Any]


class SqliteVectorStore:
    def __init__(self, *, path: str | Path, dims: int = 256) -> None:
        self._path = str(path)
        self._dims = int(dims)

    @property
    def path(self) -> str:
        return self._path

    def init(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_docs (
                    doc_id TEXT PRIMARY KEY,
                    doc_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_docs_type ON knowledge_docs(doc_type)")
            conn.commit()

    def upsert(
        self,
        *,
        doc_id: str,
        doc_type: str,
        content: str,
        metadata: dict[str, Any],
        updated_at_ms: int,
    ) -> None:
        vec = embed_text(content, dims=self._dims)
        row = {
            "doc_id": doc_id,
            "doc_type": doc_type,
            "content": content,
            "metadata_json": json.dumps(metadata, ensure_ascii=False),
            "vector_json": json.dumps({str(k): v for k, v in vec.items()}, ensure_ascii=False),
            "updated_at_ms": int(updated_at_ms),
        }
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                INSERT INTO knowledge_docs(doc_id, doc_type, content, metadata_json, vector_json, updated_at_ms)
                VALUES(:doc_id, :doc_type, :content, :metadata_json, :vector_json, :updated_at_ms)
                ON CONFLICT(doc_id) DO UPDATE SET
                    doc_type=excluded.doc_type,
                    content=excluded.content,
                    metadata_json=excluded.metadata_json,
                    vector_json=excluded.vector_json,
                    updated_at_ms=excluded.updated_at_ms
                """,
                row,
            )
            conn.commit()

    def query(
        self,
        *,
        query_text: str,
        top_k: int = 5,
        doc_type: str | None = None,
    ) -> list[SimilarDoc]:
        top_k = max(1, int(top_k))
        qvec = embed_text(query_text, dims=self._dims)
        if not qvec:
            return []

        self.init()
        with sqlite3.connect(self._path) as conn:
            if doc_type:
                rows = conn.execute(
                    "SELECT doc_id, content, metadata_json, vector_json FROM knowledge_docs WHERE doc_type = ?",
                    (doc_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT doc_id, content, metadata_json, vector_json FROM knowledge_docs"
                ).fetchall()

        results: list[SimilarDoc] = []
        for doc_id, content, metadata_json, vector_json in rows:
            try:
                meta = json.loads(metadata_json) if metadata_json else {}
                raw = json.loads(vector_json) if vector_json else {}
                dvec = {int(k): float(v) for k, v in raw.items()}
            except Exception:
                continue
            score = cosine_sim(qvec, dvec)
            if score <= 0.0:
                continue
            results.append(SimilarDoc(doc_id=str(doc_id), score=float(score), content=str(content), metadata=meta))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def count(self, *, doc_type: str | None = None) -> int:
        self.init()
        with sqlite3.connect(self._path) as conn:
            if doc_type:
                row = conn.execute("SELECT COUNT(1) FROM knowledge_docs WHERE doc_type = ?", (doc_type,)).fetchone()
            else:
                row = conn.execute("SELECT COUNT(1) FROM knowledge_docs").fetchone()
        return int(row[0] if row else 0)


def stable_alert_text(parts: Iterable[str]) -> str:
    cleaned = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
    return " ".join(cleaned)

