"""
统一内存存储系统.

融合原 UnifiedMemory 和 ContextStore 功能,提供:
- 短期工作记忆 (Redis): Agent 独立记忆 + 共享记忆
- 长期运行记忆 (Redis Hash): 完整的运行状态快照
- 长期语义记忆 (PageIndex): 可检索的知识积累

架构:
    ┌─────────────────────────────────────────────┐
    │              MemoryStore                    │
    ├──────────────────┬──────────────────────────┤
    │  短期工作记忆     │    长期记忆             │
    │  (Redis List)    │    (Redis Hash)          │
    │                  │    + PageIndex          │
    ├──────────────────┼──────────────────────────┤
    │  - agent:{id}    │  - context:{run_id}      │
    │  - shared        │  - summary:{run_id}      │
    │  - 带TTL自动过期  │  - 持久化存储            │
    └──────────────────┴──────────────────────────┘
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import redis.asyncio as redis

from riskmonitor_multiagent.contracts.approval import build_approval_summary_text
from riskmonitor_multiagent.contracts.memory_entry import normalize_memory_entry

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


@dataclass
class MemoryConfig:
    """内存存储配置."""
    redis_url: str
    default_ttl: int = 86400  # 24小时
    max_list_len: int = 2000
    enable_page_index: bool = False
    page_index_api_key: str | None = None


class MemoryStore:
    """
    统一内存存储.
    
    提供分层记忆管理:
    1. 短期记忆: Agent 独立 + 共享,支持 TTL
    2. 长期上下文: 完整运行状态,持久化
    3. 长期语义: PageIndex 向量检索
    """

    def __init__(self, config: MemoryConfig | None = None) -> None:
        """初始化内存存储."""
        if config is None:
            config = self._default_config()
        
        self._config = config
        self._redis: redis.Redis | None = None
        self._page_index = None
        self._semantic_index: dict[str, dict[str, Any]] = {}
        
        # 延迟初始化连接
        self._initialized = False
    
    def _default_config(self) -> MemoryConfig:
        """从环境变量加载默认配置."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        ttl = int(os.getenv("MEMORY_TTL_S", "86400"))
        max_len = int(os.getenv("MEMORY_MAX_LEN", "2000"))
        enable_pi = os.getenv("PAGE_INDEX_ENABLED", "false").lower() == "true"
        pi_key = os.getenv("PAGE_INDEX_API_KEY")
        
        return MemoryConfig(
            redis_url=redis_url,
            default_ttl=ttl,
            max_list_len=max_len,
            enable_page_index=enable_pi,
            page_index_api_key=pi_key,
        )
    
    async def _ensure_connected(self) -> redis.Redis:
        """确保 Redis 连接."""
        if self._redis is None:
            self._redis = await redis.from_url(
                self._config.redis_url,
                decode_responses=True,
            )
        return self._redis
    
    # ==================== 短期工作记忆 ====================
    
    async def append(
        self,
        entry: dict[str, Any],
        *,
        agent_id: str | None = None,
        scope: str = "shared",
        ttl: int | None = None,
    ) -> dict[str, Any]:
        """
        添加记忆条目.
        
        Args:
            entry: 记忆内容
            agent_id: Agent 标识(scope=private 时必填)
            scope: "private" 或 "shared"
            ttl: 过期时间(秒),默认使用配置值
        
        Returns:
            归一化后的条目
        """
        r = await self._ensure_connected()
        
        # 归一化条目
        nd = normalize_memory_entry(entry)
        nd["scope"] = scope
        if agent_id:
            nd["agent_id"] = agent_id
        
        # 确定存储 key
        if scope == "private":
            if not agent_id:
                raise ValueError("private scope requires agent_id")
            key = f"agent:{agent_id}:memory"
        else:
            key = "shared:memory"
        
        # 存储到 Redis List
        entry_json = json.dumps(nd, ensure_ascii=False)
        pipe = r.pipeline()
        pipe.lpush(key, entry_json)
        pipe.ltrim(key, 0, self._config.max_list_len - 1)
        
        # 设置 TTL
        effective_ttl = ttl or self._config.default_ttl
        pipe.expire(key, effective_ttl)
        
        await pipe.execute()
        
        # 异步索引到长期语义记忆
        if scope == "shared":
            await self._index_to_page_index(nd)
        
        return nd
    
    async def list_recent(
        self,
        *,
        agent_id: str,
        scope: str,
        session_id: str | None = None,
        run_id: str | None = None,
        kinds: list[str] | None = None,
        memory_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        查询近期记忆.
        
        Args:
            agent_id: Agent 标识
            scope: "private" 或 "shared"
            session_id: 可选的会话过滤
            run_id: 可选的运行过滤
            kinds: 可选的类型过滤
            limit: 返回条数上限
        
        Returns:
            记忆条目列表(按时间倒序)
        """
        r = await self._ensure_connected()
        
        # 确定查询 key
        if scope == "private":
            key = f"agent:{agent_id}:memory"
        else:
            key = "shared:memory"
        
        # 获取列表
        entries_json = await r.lrange(key, 0, limit * 2)  # 多取一些用于过滤
        
        # 解析并过滤
        results: list[dict[str, Any]] = []
        for entry_json in entries_json:
            try:
                entry = json.loads(entry_json)
            except json.JSONDecodeError:
                continue
            
            # 作用域检查
            if scope == "private" and entry.get("agent_id") != agent_id:
                continue
            
            # 会话过滤
            if session_id is not None and entry.get("session_id") != session_id:
                continue
            
            # 运行过滤
            if run_id is not None and entry.get("run_id") != run_id:
                continue
            
            # 类型过滤
            if kinds is not None and entry.get("kind") not in kinds:
                continue

            if memory_types is not None and entry.get("memory_type") not in memory_types:
                continue
            
            results.append(entry)
            if len(results) >= limit:
                break
        
        return results

    async def retrieve_for_planning(
        self,
        *,
        task: dict[str, Any],
        intent: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """在规划前统一检索近期记忆和语义记忆."""
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        content = payload.get("content") if isinstance(payload.get("content"), str) else ""
        session_id = task.get("session_id") if isinstance(task.get("session_id"), str) else None
        intent_type = None
        if isinstance(intent, dict):
            intent_type = intent.get("primary_intent_type")

        recent_hits = await self.list_recent(
            agent_id="orchestrator",
            scope="shared",
            session_id=session_id,
            kinds=["plan", "final", "analysis", "intent_disambiguation", "lesson", "approval"],
            memory_types=["episodic", "procedural"],
            limit=max(limit, 1),
        )
        semantic_hits = await self.search_semantic(
            self._build_planning_query(content=content, intent_type=intent_type),
            agent_id="orchestrator",
            limit=max(0, limit - len(recent_hits)),
        )
        hits = self._dedupe_memory_hits(recent_hits + semantic_hits, limit=limit)
        return {
            "hits": hits,
            "summary": self._summarize_hits(hits),
        }

    async def record_working_memory(
        self,
        *,
        run_id: str,
        task: dict[str, Any],
        trace_entry: dict[str, Any],
    ) -> dict[str, Any]:
        """记录 step 级 working memory."""
        step_id = str(trace_entry.get("step_id") or "unknown")
        kind = str(trace_entry.get("kind") or "unknown")
        status = str(trace_entry.get("status") or "unknown")
        tool_name = trace_entry.get("tool_name")
        target_agent = trace_entry.get("target_agent")
        error = trace_entry.get("error")

        text_parts = [f"step {step_id}", f"kind={kind}", f"status={status}"]
        if isinstance(target_agent, str) and target_agent:
            text_parts.append(f"agent={target_agent}")
        if isinstance(tool_name, str) and tool_name:
            text_parts.append(f"tool={tool_name}")
        if isinstance(error, str) and error:
            text_parts.append(f"error={error}")

        return await self.append(
            {
                "agent_id": "orchestrator",
                "scope": "shared",
                "kind": "working_memory",
                "memory_type": "episodic",
                "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                "run_id": run_id,
                "source": "task_graph_execution",
                "created_by": "task_graph_executor",
                "trace_ref": {
                    "run_id": run_id,
                    "step_id": step_id,
                    "command_id": trace_entry.get("command_id"),
                },
                "content": {
                    "text": " ".join(text_parts),
                    "task_id": task.get("task_id"),
                    "payload": task.get("payload"),
                    "trace_entry": trace_entry,
                },
                "tags": [kind, status],
            }
        )

    async def persist_run_artifacts(
        self,
        *,
        run_id: str,
        task: dict[str, Any],
        final_output: dict[str, Any],
        critic_final: dict[str, Any],
    ) -> dict[str, Any]:
        """保存 run summary 和 procedural lesson."""
        run_summary = critic_final.get("run_summary") if isinstance(critic_final, dict) else {}
        if not isinstance(run_summary, dict):
            run_summary = {}
        summary_text = run_summary.get("text")
        if not isinstance(summary_text, str) or not summary_text.strip():
            summary_text = self._derive_summary_text(final_output=final_output)
        key_points = run_summary.get("key_points")
        if not isinstance(key_points, list):
            key_points = []

        summary_payload = {
            "text": summary_text,
            "key_points": key_points,
            "receipt_command_ids": list(final_output.get("receipt_command_ids") or []),
            "task_id": task.get("task_id"),
            "session_id": task.get("session_id"),
        }
        await self.upsert_run_summary(run_id=run_id, summary=summary_payload)
        summary_entry = await self.append(
            {
                "agent_id": "critic",
                "scope": "shared",
                "kind": "final",
                "memory_type": "episodic",
                "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                "run_id": run_id,
                "source": "critic_final_review",
                "created_by": "critic",
                "trace_ref": {"run_id": run_id},
                "content": summary_payload,
                "tags": ["summary"],
            }
        )

        lesson_text = self._derive_lesson_text(final_output=final_output, run_summary=summary_payload)
        lesson_entry = await self.append(
            {
                "agent_id": "critic",
                "scope": "shared",
                "kind": "lesson",
                "memory_type": "procedural",
                "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                "run_id": run_id,
                "source": "critic_final_review",
                "created_by": "critic",
                "trace_ref": {"run_id": run_id},
                "content": {
                    "text": lesson_text,
                    "task_id": task.get("task_id"),
                    "key_points": key_points,
                    "receipt_command_ids": summary_payload["receipt_command_ids"],
                },
                "tags": ["lesson", "procedure"],
            }
        )
        return {
            "run_summary": summary_payload,
            "summary_entry": summary_entry,
            "lesson_entry": lesson_entry,
        }

    async def persist_approval_memory(
        self,
        *,
        run_id: str,
        task: dict[str, Any],
        approval_records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """保存审批摘要."""
        saved_entries: list[dict[str, Any]] = []
        for record in approval_records:
            if not isinstance(record, dict):
                continue
            saved_entries.append(
                await self.append(
                    {
                        "agent_id": "orchestrator",
                        "scope": "shared",
                        "kind": "approval",
                        "memory_type": "episodic",
                        "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                        "run_id": run_id,
                        "source": "approval_trace",
                        "created_by": "workflow",
                        "trace_ref": {
                            "run_id": run_id,
                            "step_id": record.get("step_id"),
                            "command_id": record.get("command_id"),
                            "approval_id": record.get("approval_id"),
                        },
                        "content": {
                            "text": build_approval_summary_text(record),
                            "task_id": task.get("task_id"),
                            "approval_record": record,
                        },
                        "tags": ["approval", str(record.get("state") or "pending")],
                    }
                )
            )
        return saved_entries

    async def build_resume_payload(
        self,
        *,
        run_id: str,
        resume_from_step_id: str | None = None,
    ) -> dict[str, Any] | None:
        """根据 run_id 构造 resume payload."""
        context = await self.get_run_context(run_id)
        if not isinstance(context, dict):
            return None
        data = context.get("data") if isinstance(context.get("data"), dict) else {}
        task_graph = data.get("task_graph")
        execution_state = data.get("task_graph_execution")
        if not isinstance(task_graph, dict) or not isinstance(execution_state, dict):
            return None
        memory_state = await self.list_recent(
            agent_id="orchestrator",
            scope="shared",
            run_id=run_id,
            limit=50,
        )
        return {
            "run_id": run_id,
            "task_graph": task_graph,
            "execution_state": execution_state,
            "resume_from_step_id": (
                resume_from_step_id
                or execution_state.get("blocked_step_id")
                or execution_state.get("failed_step_id")
            ),
            "memory_state": memory_state,
            "run_summary": await self.get_run_summary(run_id),
        }
    
    # ==================== 长期运行上下文 ====================
    
    async def save_run_context(
        self,
        run_id: str,
        event_id: str,
        data: dict[str, Any],
    ) -> None:
        """
        保存运行上下文(原 ContextStore 功能).
        
        存储完整的运行状态到 Redis Hash,支持:
        - 运行恢复
        - 审计追踪
        - 调试排查
        
        Args:
            run_id: 运行标识
            event_id: 事件/任务标识
            data: 完整运行数据
        """
        r = await self._ensure_connected()
        
        key = f"context:{run_id}"
        payload = {
            "run_id": run_id,
            "event_id": event_id,
            "created_at_ms": int(time.time() * 1000),
            "data": data,
        }
        
        # 存储到 Hash
        await r.hset(key, mapping={
            "payload": json.dumps(payload, ensure_ascii=False),
        })
        
        # 创建事件索引
        await r.hset(f"event_index:{event_id}", run_id, key)
    
    async def get_run_context(self, run_id: str) -> dict[str, Any] | None:
        """获取运行上下文."""
        r = await self._ensure_connected()
        
        key = f"context:{run_id}"
        result = await r.hget(key, "payload")
        
        if not result:
            return None
        
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return None
    
    async def get_context_by_event(
        self,
        event_id: str,
        latest: bool = True,
    ) -> dict[str, Any] | None:
        """
        通过事件 ID 查找运行上下文.
        
        Args:
            event_id: 事件标识
            latest: 是否返回最新的(默认)或最早的
        
        Returns:
            运行上下文或 None
        """
        r = await self._ensure_connected()
        
        # 获取该事件的所有运行记录
        index_key = f"event_index:{event_id}"
        run_ids = await r.hkeys(index_key)
        
        if not run_ids:
            return None
        
        # 按 run_id 时间戳排序
        sorted_runs = sorted(run_ids, reverse=latest)
        
        for run_id in sorted_runs:
            context = await self.get_run_context(run_id)
            if context:
                return context
        
        return None
    
    async def update_run_context(
        self,
        run_id: str,
        patch: dict[str, Any],
    ) -> None:
        """
        增量更新运行上下文.
        
        Args:
            run_id: 运行标识
            patch: 增量更新内容
        """
        r = await self._ensure_connected()
        
        key = f"context:{run_id}"
        
        # 获取现有数据
        existing = await self.get_run_context(run_id)
        if not existing:
            raise ValueError(f"Run context not found: {run_id}")
        
        # 合并更新
        existing_data = existing.get("data", {})
        existing_data.update(patch)
        existing["data"] = existing_data
        
        # 保存
        await r.hset(key, mapping={
            "payload": json.dumps(existing, ensure_ascii=False),
        })
    
    # ==================== 运行总结 ====================
    
    async def upsert_run_summary(
        self,
        *,
        run_id: str,
        summary: dict[str, Any],
    ) -> None:
        """保存运行总结."""
        r = await self._ensure_connected()
        
        key = f"summary:{run_id}"
        await r.hset(key, mapping={
            "payload": json.dumps(summary, ensure_ascii=False),
            "updated_at": int(time.time()),
        })
    
    async def get_run_summary(self, run_id: str) -> dict[str, Any] | None:
        """获取运行总结."""
        r = await self._ensure_connected()
        
        key = f"summary:{run_id}"
        result = await r.hget(key, "payload")
        
        if not result:
            return None
        
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return None
    
    # ==================== PageIndex 语义记忆 ====================
    
    async def _index_to_page_index(self, entry: dict[str, Any]) -> None:
        """
        索引到 PageIndex(长期语义记忆).
        
        仅索引重要类型的条目(plan, final).
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
        self._semantic_index[entry_id] = indexed_entry
        if self._page_index is None:
            self._page_index = {}
        self._page_index[entry_id] = {
            "text": text,
            "memory_type": entry.get("memory_type"),
            "kind": entry.get("kind"),
        }
    
    async def search_semantic(
        self,
        query: str,
        *,
        agent_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        语义搜索长期记忆.
        
        Args:
            query: 搜索查询
            agent_id: 可选的 Agent 过滤
            limit: 返回数量
        
        Returns:
            相关记忆条目
        """
        if not self._config.enable_page_index:
            return []

        query_text = (query or "").strip()
        if not query_text:
            return []

        query_vec = self._embed_text(query_text)
        query_tokens = self._tokenize(query_text)
        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in self._semantic_index.values():
            if agent_id and entry.get("scope") == "private" and entry.get("agent_id") != agent_id:
                continue
            score = self._semantic_score(query_vec=query_vec, query_tokens=query_tokens, entry=entry)
            if score <= 0.0:
                continue
            hit = dict(entry)
            hit["semantic_score"] = round(score, 4)
            scored.append((score, hit))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [hit for _, hit in scored[: max(0, limit)]]

    def _build_planning_query(self, *, content: str, intent_type: str | None) -> str:
        parts = [content.strip()]
        if isinstance(intent_type, str) and intent_type.strip():
            parts.append(intent_type.strip())
        return " ".join(part for part in parts if part)

    def _dedupe_memory_hits(self, hits: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for hit in hits:
            entry_id = hit.get("entry_id")
            if not isinstance(entry_id, str) or not entry_id:
                continue
            if entry_id in seen:
                continue
            seen.add(entry_id)
            results.append(hit)
            if len(results) >= limit:
                break
        return results

    def _summarize_hits(self, hits: list[dict[str, Any]]) -> dict[str, Any]:
        lines: list[str] = []
        for hit in hits:
            kind = hit.get("kind", "unknown")
            memory_type = hit.get("memory_type", "episodic")
            content = hit.get("content") if isinstance(hit.get("content"), dict) else {}
            text = content.get("text")
            if not isinstance(text, str) or not text.strip():
                text = str(content)[:120]
            lines.append(f"[{memory_type}/{kind}] {text[:120]}")
        return {
            "hit_count": len(hits),
            "texts": lines,
            "memory_hits": [
                {
                    "entry_id": hit.get("entry_id"),
                    "memory_type": hit.get("memory_type"),
                    "kind": hit.get("kind"),
                    "trace_ref": hit.get("trace_ref"),
                    "semantic_score": hit.get("semantic_score"),
                }
                for hit in hits
            ],
        }

    def _memory_text(self, entry: dict[str, Any]) -> str:
        content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
        text = content.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        return json.dumps(content, ensure_ascii=False, sort_keys=True)

    def _derive_summary_text(self, *, final_output: dict[str, Any]) -> str:
        summary = final_output.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        return json.dumps(final_output, ensure_ascii=False, sort_keys=True)[:200]

    def _derive_lesson_text(self, *, final_output: dict[str, Any], run_summary: dict[str, Any]) -> str:
        key_points = run_summary.get("key_points") if isinstance(run_summary.get("key_points"), list) else []
        if key_points:
            return "lesson " + " ; ".join(str(item) for item in key_points[:3])
        summary_text = run_summary.get("text")
        if isinstance(summary_text, str) and summary_text.strip():
            return f"lesson based on summary {summary_text[:160]}"
        return f"lesson based on output {self._derive_summary_text(final_output=final_output)[:160]}"

    def _tokenize(self, text: str) -> list[str]:
        if not text:
            return []
        return [token.lower() for token in _TOKEN_RE.findall(text)]

    def _embed_text(self, text: str, *, dims: int = 128) -> list[float]:
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
        entry_vec = entry.get("semantic_vector")
        if not isinstance(entry_vec, list) or len(entry_vec) != len(query_vec):
            return 0.0
        cosine = sum(float(a) * float(b) for a, b in zip(query_vec, entry_vec))
        entry_tokens = set(self._tokenize(str(entry.get("semantic_text") or "")))
        overlap = 0.0
        if query_tokens and entry_tokens:
            overlap = len(set(query_tokens) & entry_tokens) / len(set(query_tokens))
        return (cosine * 0.7) + (overlap * 0.3)
    
    # ==================== 工具方法 ====================
    
    async def close(self) -> None:
        """关闭连接."""
        if self._redis:
            await self._redis.close()
            self._redis = None
    
    async def health_check(self) -> bool:
        """健康检查."""
        try:
            r = await self._ensure_connected()
            await r.ping()
            return True
        except Exception:
            return False


# ==================== 全局实例管理 ====================

_MEMORY_STORE: MemoryStore | None = None
_MEMORY_CONFIG_SIG: tuple = ()


def get_memory_store() -> MemoryStore:
    """
    获取全局 MemoryStore 实例.
    
    根据环境变量变化自动重建.
    """
    global _MEMORY_STORE, _MEMORY_CONFIG_SIG
    
    try:
        loop_sig = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_sig = 0

    sig = (
        os.getenv("REDIS_URL", ""),
        os.getenv("MEMORY_TTL_S", ""),
        os.getenv("PAGE_INDEX_ENABLED", ""),
        loop_sig,
    )
    
    if _MEMORY_STORE is None or _MEMORY_CONFIG_SIG != sig:
        _MEMORY_STORE = MemoryStore()
        _MEMORY_CONFIG_SIG = sig
    
    return _MEMORY_STORE


def new_run_id(*, event_id: str) -> str:
    """生成新的运行 ID."""
    now_ms = int(time.time() * 1000)
    safe_event_id = event_id.replace("/", "_").replace(":", "_")
    uid = uuid.uuid4().hex[:8]
    return f"run_{safe_event_id}_{now_ms}_{uid}"
