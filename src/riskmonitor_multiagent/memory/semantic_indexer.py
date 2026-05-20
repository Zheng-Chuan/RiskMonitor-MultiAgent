"""
语义索引与搜索模块.

提供基于向量的轻量语义检索能力,用于长期经验记忆.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from typing import Any

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


class SemanticIndexer:
    """内置轻量语义索引器."""

    def __init__(self) -> None:
        self._index: dict[str, dict[str, Any]] = {}

    @property
    def index(self) -> dict[str, dict[str, Any]]:
        """暴露内部索引(向后兼容)."""
        return self._index

    async def index_entry(self, entry: dict[str, Any]) -> None:
        """
        索引到长期语义经验层.

        仅索引重要类型的条目(plan, final, semantic_case 等).
        """
        kind = entry.get("kind")
        memory_type = entry.get("memory_type")
        if kind not in {"plan", "final", "analysis", "lesson", "semantic_case"} and memory_type not in {"semantic", "procedural"}:
            return

        text = self._memory_text(entry)
        if not text:
            return

        entry_id = str(entry.get("entry_id") or uuid.uuid4().hex)
        indexed_entry = dict(entry)
        indexed_entry["semantic_text"] = text
        indexed_entry["semantic_vector"] = self._embed_text(text)
        self._index[entry_id] = indexed_entry

    async def search(
        self,
        query: str,
        *,
        enabled: bool = True,
        agent_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        语义搜索长期记忆.

        Args:
            query: 搜索查询
            enabled: 是否启用语义搜索
            agent_id: 可选的 Agent 过滤
            limit: 返回数量

        Returns:
            相关记忆条目
        """
        if not enabled:
            return []

        query_text = (query or "").strip()
        if not query_text:
            return []

        query_vec = self._embed_text(query_text)
        query_tokens = self._tokenize(query_text)
        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in self._index.values():
            if agent_id and entry.get("scope") == "private" and entry.get("agent_id") != agent_id:
                continue
            score = self._semantic_score(query_vec=query_vec, query_tokens=query_tokens, entry=entry)
            if score <= 0.0:
                continue
            hit = dict(entry)
            hit["semantic_score"] = round(score, 4)
            reusable_snippet = self.build_reusable_snippet(hit)
            if reusable_snippet:
                hit["reusable_snippet"] = reusable_snippet
            scored.append((score, hit))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [hit for _, hit in scored[: max(0, limit)]]

    def build_reusable_snippet(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """构建可复用片段."""
        content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
        decision_pattern = content.get("decision_pattern")
        failure_boundary = content.get("failure_boundary")
        if not isinstance(decision_pattern, str) and not isinstance(failure_boundary, list):
            return None
        return {
            "decision_pattern": decision_pattern,
            "failure_boundary": failure_boundary if isinstance(failure_boundary, list) else [],
            "applicable_conditions": content.get("applicable_conditions") if isinstance(content.get("applicable_conditions"), list) else [],
            "evidence_refs": content.get("evidence_refs") if isinstance(content.get("evidence_refs"), list) else [],
        }

    def _memory_text(self, entry: dict[str, Any]) -> str:
        """提取条目的语义文本."""
        content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
        snapshot_text = content.get("snapshot_text")
        if isinstance(snapshot_text, str) and snapshot_text.strip():
            return snapshot_text.strip()
        text = content.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        return json.dumps(_make_json_safe(content), ensure_ascii=False, sort_keys=True)

    def _tokenize(self, text: str) -> list[str]:
        """分词."""
        if not text:
            return []
        return [token.lower() for token in _TOKEN_RE.findall(text)]

    def _embed_text(self, text: str, *, dims: int = 128) -> list[float]:
        """轻量词袋向量化."""
        tokens = self._tokenize(text)
        vec = [0.0] * int(dims)
        if not tokens:
            return vec
        for token in tokens:
            vec[hash(token) % dims] += 1.0
        norm = math.sqrt(sum(value * value for value in vec))
        if norm <= 0.0:
            return vec
        return [value / norm for value in vec]

    def _semantic_score(
        self,
        *,
        query_vec: list[float],
        query_tokens: list[str],
        entry: dict[str, Any],
    ) -> float:
        """计算语义相似度得分."""
        entry_vec = entry.get("semantic_vector")
        if not isinstance(entry_vec, list) or len(entry_vec) != len(query_vec):
            return 0.0
        cosine = sum(float(a) * float(b) for a, b in zip(query_vec, entry_vec))
        entry_tokens = set(self._tokenize(str(entry.get("semantic_text") or "")))
        overlap = 0.0
        if query_tokens and entry_tokens:
            overlap = len(set(query_tokens) & entry_tokens) / len(set(query_tokens))
        return (cosine * 0.7) + (overlap * 0.3)


def _make_json_safe(value: Any) -> Any:
    """确保值可以安全 JSON 序列化."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _make_json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_make_json_safe(item) for item in value]
    return str(value)
