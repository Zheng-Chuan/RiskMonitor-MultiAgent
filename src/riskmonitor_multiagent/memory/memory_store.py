"""
统一内存存储系统.

融合原 UnifiedMemory 和 ContextStore 功能,提供:
- 短期工作记忆 (Redis): Agent 独立记忆 + 共享记忆
- 长期运行记忆 (Redis Hash): 完整的运行状态快照
- 长期语义经验 (内置语义索引): 可检索的知识积累

架构:
    ┌─────────────────────────────────────────────┐
    │              MemoryStore                    │
    ├──────────────────┬──────────────────────────┤
    │  短期工作记忆     │    长期记忆             │
    │  (Redis List)    │    (Redis Hash)          │
    │                  │    + Semantic Index      │
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
_DEFAULT_PRIVATE_AGENT_IDS = (
    "orchestrator",
    "system_engineer",
    "risk_analyst",
    "critic",
)
_CANONICAL_AGENT_IDS = {
    "engineer": "system_engineer",
    "system_engineer": "system_engineer",
    "analyst": "risk_analyst",
    "risk_analyst": "risk_analyst",
    "orchestrator": "orchestrator",
    "critic": "critic",
    "intent": "intent",
}
_AGENT_PERSPECTIVES = {
    "system_engineer": "system_reliability",
    "risk_analyst": "business_risk",
    "orchestrator": "global_planning",
    "critic": "quality_gate",
    "intent": "intent_resolution",
}


@dataclass
class MemoryConfig:
    """内存存储配置."""
    redis_url: str
    default_ttl: int = 86400  # 24小时
    max_list_len: int = 2000
    enable_semantic_memory: bool = True


class MemoryStore:
    """
    统一内存存储.
    
    提供分层记忆管理:
    1. 短期记忆: Agent 独立 + 共享,支持 TTL
    2. 长期上下文: 完整运行状态,持久化
    3. 长期语义: 内置语义检索
    """

    def __init__(self, config: MemoryConfig | None = None) -> None:
        """初始化内存存储."""
        if config is None:
            config = self._default_config()
        
        self._config = config
        self._redis: redis.Redis | None = None
        self._semantic_index: dict[str, dict[str, Any]] = {}
        
        # 延迟初始化连接
        self._initialized = False
    
    def _default_config(self) -> MemoryConfig:
        """从环境变量加载默认配置."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        ttl = int(os.getenv("MEMORY_TTL_S", "86400"))
        max_len = int(os.getenv("MEMORY_MAX_LEN", "2000"))
        legacy_pageindex = os.getenv("PAGE_INDEX_ENABLED")
        semantic_enabled = os.getenv("SEMANTIC_MEMORY_ENABLED")
        if semantic_enabled is None:
            semantic_enabled = legacy_pageindex if legacy_pageindex is not None else "true"
        
        return MemoryConfig(
            redis_url=redis_url,
            default_ttl=ttl,
            max_list_len=max_len,
            enable_semantic_memory=str(semantic_enabled).lower() == "true",
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
            await self._index_to_semantic_memory(nd)
        
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
        if not content and isinstance(task.get("content"), str):
            content = task.get("content") or ""
        session_id = task.get("session_id") if isinstance(task.get("session_id"), str) else None
        run_id = task.get("run_id") if isinstance(task.get("run_id"), str) else None
        private_memory_enabled = task.get("private_memory_enabled", True) is not False
        intent_type = None
        if isinstance(intent, dict):
            intent_type = intent.get("primary_intent_type")

        shared_board = await self.get_shared_memory_board(
            session_id=session_id,
            run_id=run_id,
            limit=max(limit * 2, 6),
        )
        private_memory_state: dict[str, list[dict[str, Any]]] = {}
        if private_memory_enabled:
            private_memory_state = await self.get_private_memory_state(
                session_id=session_id,
                run_id=run_id,
                agent_ids=_DEFAULT_PRIVATE_AGENT_IDS,
                limit=3,
            )

        semantic_reserve = 1 if limit <= 2 else 2
        recent_limit = max(1, limit - semantic_reserve)
        recent_hits = await self.list_recent(
            agent_id="orchestrator",
            scope="shared",
            session_id=session_id,
            kinds=["plan", "final", "analysis", "intent_disambiguation", "lesson", "approval"],
            memory_types=["episodic", "procedural"],
            limit=recent_limit,
        )
        semantic_hits = await self.search_semantic(
            self._build_planning_query(content=content, intent_type=intent_type),
            agent_id="orchestrator",
            limit=max(1, limit - min(len(recent_hits), recent_limit)),
        )
        recent_semantic_cases = await self.list_recent(
            agent_id="orchestrator",
            scope="shared",
            session_id=session_id,
            kinds=["semantic_case"],
            memory_types=["semantic"],
            limit=semantic_reserve,
        )
        for entry in recent_semantic_cases:
            reusable_snippet = self._build_reusable_snippet(entry)
            if reusable_snippet:
                entry["reusable_snippet"] = reusable_snippet
        hits = self._dedupe_memory_hits(recent_hits + semantic_hits + recent_semantic_cases, limit=limit)
        summary = self._summarize_hits(hits)
        summary["shared_board"] = self._summarize_shared_board(shared_board)
        summary["private_memory"] = self._summarize_private_memory(private_memory_state)
        summary["few_shot_examples"] = self._extract_few_shot_examples(hits)
        summary["few_shot_example_count"] = len(summary["few_shot_examples"])
        summary["role_drift_rate"] = self._estimate_role_drift(
            shared_board=shared_board,
            private_memory_state=private_memory_state,
        )
        summary["memory_cross_talk_rate"] = self._estimate_memory_cross_talk(
            private_memory_state=private_memory_state,
        )
        return {
            "hits": hits,
            "summary": summary,
            "shared_board": shared_board,
            "private_memory_state": private_memory_state,
        }

    async def record_working_memory(
        self,
        *,
        run_id: str,
        task: dict[str, Any],
        trace_entry: dict[str, Any],
        node: dict[str, Any] | None = None,
        node_result: dict[str, Any] | None = None,
        private_memory_enabled: bool = True,
    ) -> dict[str, Any]:
        """记录 step 级 working memory."""
        step_id = str(trace_entry.get("step_id") or "unknown")
        kind = str(trace_entry.get("kind") or "unknown")
        status = str(trace_entry.get("status") or "unknown")
        tool_name = trace_entry.get("tool_name")
        target_agent = self._canonical_agent_id(
            trace_entry.get("target_agent") or (node or {}).get("target_agent"),
        )
        error = trace_entry.get("error")
        content = self._extract_content_text(task=task)
        task_phase = "execution"
        confidence = self._extract_confidence(node_result)

        text_parts = [f"step {step_id}", f"kind={kind}", f"status={status}"]
        if isinstance(target_agent, str) and target_agent:
            text_parts.append(f"agent={target_agent}")
        if isinstance(tool_name, str) and tool_name:
            text_parts.append(f"tool={tool_name}")
        if isinstance(error, str) and error:
            text_parts.append(f"error={error}")
        if content:
            text_parts.append(f"task={content[:80]}")

        shared_entry = await self.append(
            {
                "agent_id": target_agent or "orchestrator",
                "scope": "shared",
                "kind": "working_memory",
                "memory_type": "episodic",
                "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                "run_id": run_id,
                "source": "task_graph_execution",
                "created_by": target_agent or "task_graph_executor",
                "agent_role": target_agent or "orchestrator",
                "agent_perspective": self._agent_perspective(target_agent or "orchestrator"),
                "task_phase": task_phase,
                "confidence": confidence,
                "trace_ref": {
                    "run_id": run_id,
                    "step_id": step_id,
                    "command_id": trace_entry.get("command_id"),
                },
                "content": {
                    "text": " ".join(text_parts),
                    "task_id": task.get("task_id"),
                    "payload": self._make_json_safe(task.get("payload")),
                    "trace_entry": self._make_json_safe(trace_entry),
                    "node_result": self._make_json_safe(node_result if isinstance(node_result, dict) else {}),
                },
                "tags": [kind, status, task_phase],
            }
        )

        if private_memory_enabled and isinstance(target_agent, str) and target_agent in _DEFAULT_PRIVATE_AGENT_IDS:
            private_snapshot = self._build_private_task_snapshot(
                agent_id=target_agent,
                task=task,
                trace_entry=trace_entry,
                node_result=node_result or {},
            )
            await self.append(
                {
                    "agent_id": target_agent,
                    "scope": "private",
                    "kind": "private_task_state",
                    "memory_type": "episodic",
                    "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                    "run_id": run_id,
                    "source": "task_graph_execution",
                    "created_by": target_agent,
                    "agent_role": target_agent,
                    "agent_perspective": self._agent_perspective(target_agent),
                    "task_phase": task_phase,
                    "confidence": confidence,
                    "trace_ref": {
                        "run_id": run_id,
                        "step_id": step_id,
                        "command_id": trace_entry.get("command_id"),
                    },
                    "content": private_snapshot,
                    "tags": ["private_task_memory", status],
                },
                agent_id=target_agent,
                scope="private",
            )

        return shared_entry

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
        experience_entry = await self._persist_long_term_experience(
            run_id=run_id,
            task=task,
            final_output=final_output,
            critic_final=critic_final,
        )
        return {
            "run_summary": summary_payload,
            "summary_entry": summary_entry,
            "lesson_entry": lesson_entry,
            "long_term_experience": experience_entry.get("experience_entry"),
            "rejected_experience": experience_entry.get("rejected_entry"),
            "memory_policy": experience_entry.get("policy", {}),
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
        shared_memory_board = await self.get_shared_memory_board(run_id=run_id, limit=30)
        private_memory_state = await self.get_private_memory_state(
            run_id=run_id,
            agent_ids=_DEFAULT_PRIVATE_AGENT_IDS,
            limit=10,
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
            "shared_memory_board": shared_memory_board,
            "private_memory_state": private_memory_state,
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
    
    # ==================== 长期语义经验 ====================
    
    async def _index_to_semantic_memory(self, entry: dict[str, Any]) -> None:
        """
        索引到长期语义经验层.
        
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
        if not self._config.enable_semantic_memory:
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
            reusable_snippet = self._build_reusable_snippet(hit)
            if reusable_snippet:
                hit["reusable_snippet"] = reusable_snippet
            scored.append((score, hit))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [hit for _, hit in scored[: max(0, limit)]]

    async def get_private_memory_state(
        self,
        *,
        agent_ids: tuple[str, ...] | list[str] = _DEFAULT_PRIVATE_AGENT_IDS,
        session_id: str | None = None,
        run_id: str | None = None,
        limit: int = 5,
    ) -> dict[str, list[dict[str, Any]]]:
        """获取各角色的私有任务记忆快照."""
        snapshots: dict[str, list[dict[str, Any]]] = {}
        for agent_id in agent_ids:
            canonical_agent_id = self._canonical_agent_id(agent_id)
            if not canonical_agent_id:
                continue
            snapshots[canonical_agent_id] = await self.list_recent(
                agent_id=canonical_agent_id,
                scope="private",
                session_id=session_id,
                run_id=run_id,
                limit=limit,
            )
        return snapshots

    async def get_shared_memory_board(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """获取显式 shared memory board 视图."""
        entries = await self.list_recent(
            agent_id="orchestrator",
            scope="shared",
            session_id=session_id,
            run_id=run_id,
            limit=max(limit * 2, 20),
        )
        board: list[dict[str, Any]] = []
        for entry in entries:
            row = self._to_shared_board_row(entry)
            if row is None:
                continue
            board.append(row)
            if len(board) >= limit:
                break
        return board

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
                    "reusable_snippet": hit.get("reusable_snippet"),
                }
                for hit in hits
            ],
        }

    def _memory_text(self, entry: dict[str, Any]) -> str:
        content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
        snapshot_text = content.get("snapshot_text")
        if isinstance(snapshot_text, str) and snapshot_text.strip():
            return snapshot_text.strip()
        text = content.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        return json.dumps(self._make_json_safe(content), ensure_ascii=False, sort_keys=True)

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

    def _canonical_agent_id(self, agent_id: Any) -> str | None:
        if not isinstance(agent_id, str) or not agent_id.strip():
            return None
        return _CANONICAL_AGENT_IDS.get(agent_id.strip(), agent_id.strip())

    def _agent_perspective(self, agent_id: str) -> str:
        canonical_agent_id = self._canonical_agent_id(agent_id) or "orchestrator"
        return _AGENT_PERSPECTIVES.get(canonical_agent_id, canonical_agent_id)

    def _extract_content_text(self, task: dict[str, Any]) -> str:
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        content = payload.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        return str(task.get("task_id") or "").strip()

    def _extract_confidence(self, node_result: dict[str, Any] | None) -> float:
        if not isinstance(node_result, dict):
            return 1.0
        output = node_result.get("output") if isinstance(node_result.get("output"), dict) else {}
        value = output.get("confidence")
        if isinstance(value, (int, float)):
            return min(1.0, max(0.0, float(value)))
        return 1.0

    def _build_private_task_snapshot(
        self,
        *,
        agent_id: str,
        task: dict[str, Any],
        trace_entry: dict[str, Any],
        node_result: dict[str, Any],
    ) -> dict[str, Any]:
        output = node_result.get("output") if isinstance(node_result.get("output"), dict) else {}
        current_progress = str(trace_entry.get("status") or "unknown")
        observation = self._compact_output_text(output) or self._compact_output_text(node_result)
        error = trace_entry.get("error") if isinstance(trace_entry.get("error"), str) else ""
        open_questions = [error] if error else []
        next_action = "continue"
        if current_progress == "blocked":
            next_action = "wait_for_resume"
        elif current_progress == "failed":
            next_action = "replan_or_retry"
        elif current_progress == "completed":
            next_action = "handoff_to_next_step"
        role = self._canonical_agent_id(agent_id) or agent_id
        task_goal = self._extract_content_text(task)
        recent_observations = [item for item in [observation] if item]
        snapshot_text = (
            f"role={role} goal={task_goal[:80]} progress={current_progress} "
            f"observation={(observation or 'none')[:120]} next={next_action}"
        )
        return {
            "role": role,
            "task_goal": task_goal,
            "current_progress": current_progress,
            "open_questions": open_questions,
            "recent_observations": recent_observations,
            "next_intended_action": next_action,
            "snapshot_text": snapshot_text,
        }

    async def _persist_long_term_experience(
        self,
        *,
        run_id: str,
        task: dict[str, Any],
        final_output: dict[str, Any],
        critic_final: dict[str, Any],
    ) -> dict[str, Any]:
        policy = self._build_experience_policy(
            run_id=run_id,
            critic_final=critic_final,
            final_output=final_output,
        )
        if not policy["accepted"]:
            rejected_entry = await self.append(
                {
                    "agent_id": "critic",
                    "scope": "shared",
                    "kind": "experience_rejection",
                    "memory_type": "episodic",
                    "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                    "run_id": run_id,
                    "source": "critic_confidence_policy",
                    "created_by": "critic",
                    "agent_role": "critic",
                    "agent_perspective": self._agent_perspective("critic"),
                    "task_phase": "final_review",
                    "confidence": float(policy["confidence"]),
                    "trace_ref": {"run_id": run_id},
                    "content": {
                        "text": f"experience rejected because {policy['reasons'][0]}",
                        "policy": policy,
                    },
                    "tags": ["experience", "rejected"],
                }
            )
            return {
                "experience_entry": None,
                "rejected_entry": rejected_entry,
                "policy": policy,
            }

        content = self._build_long_term_experience_content(
            task=task,
            final_output=final_output,
            critic_final=critic_final,
            policy=policy,
        )
        experience_entry = await self.append(
            {
                "agent_id": "critic",
                "scope": "shared",
                "kind": "semantic_case",
                "memory_type": "semantic",
                "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                "run_id": run_id,
                "source": "critic_confidence_policy",
                "created_by": "critic",
                "agent_role": "critic",
                "agent_perspective": content.get("agent_perspective"),
                "task_phase": "final_review",
                "confidence": float(policy["confidence"]),
                "trace_ref": {"run_id": run_id},
                "content": content,
                "tags": ["experience", "few_shot", "critic"],
            }
        )
        return {
            "experience_entry": experience_entry,
            "rejected_entry": None,
            "policy": policy,
        }

    def _build_experience_policy(
        self,
        *,
        run_id: str,
        critic_final: dict[str, Any],
        final_output: dict[str, Any],
    ) -> dict[str, Any]:
        evidence = critic_final.get("evidence") if isinstance(critic_final.get("evidence"), dict) else {}
        receipt_command_ids = list(evidence.get("receipt_command_ids") or final_output.get("receipt_command_ids") or [])
        if not receipt_command_ids:
            explicit_refs = evidence.get("evidence_refs")
            if isinstance(explicit_refs, list):
                receipt_command_ids = [str(item) for item in explicit_refs if str(item).strip()]
        if not receipt_command_ids:
            receipt_command_ids = [f"run_trace:{run_id}", f"final_output:{run_id}"]
        confidence = critic_final.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = 0.9 if critic_final.get("ok") is True else 0.4
        reasons: list[str] = []
        if critic_final.get("ok") is not True:
            reasons.append("critic_not_ok")
        if float(confidence) < 0.85:
            reasons.append("low_confidence")
        return {
            "accepted": len(reasons) == 0,
            "confidence": min(1.0, max(0.0, float(confidence))),
            "threshold": 0.85,
            "reasons": reasons or ["accepted"],
            "evidence_refs": receipt_command_ids,
        }

    def _build_long_term_experience_content(
        self,
        *,
        task: dict[str, Any],
        final_output: dict[str, Any],
        critic_final: dict[str, Any],
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        summary = critic_final.get("run_summary") if isinstance(critic_final.get("run_summary"), dict) else {}
        key_points = summary.get("key_points") if isinstance(summary.get("key_points"), list) else []
        decision_pattern = " -> ".join(str(item) for item in key_points[:3]) or "use receipts to validate final answer"
        applicable_conditions = [
            self._extract_content_text(task)[:120] or "general_multi_agent_task",
        ]
        failure_boundary = critic_final.get("issues") if isinstance(critic_final.get("issues"), list) else []
        if not failure_boundary:
            failure_boundary = ["low_evidence_or_low_confidence_should_not_reuse"]
        snapshot_text = (
            f"decision_pattern={decision_pattern[:120]} "
            f"conditions={'; '.join(applicable_conditions)[:120]} "
            f"boundary={'; '.join(str(item) for item in failure_boundary[:2])[:120]}"
        )
        return {
            "text": summary.get("text") or self._derive_summary_text(final_output=final_output),
            "agent_perspective": self._agent_perspective("critic"),
            "decision_pattern": decision_pattern,
            "applicable_conditions": applicable_conditions,
            "failure_boundary": failure_boundary,
            "evidence_refs": list(policy.get("evidence_refs") or []),
            "snapshot_text": snapshot_text,
        }

    def _build_reusable_snippet(self, entry: dict[str, Any]) -> dict[str, Any] | None:
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

    def _extract_few_shot_examples(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        examples: list[dict[str, Any]] = []
        for hit in hits:
            snippet = hit.get("reusable_snippet")
            if not isinstance(snippet, dict):
                continue
            examples.append(
                {
                    "entry_id": hit.get("entry_id"),
                    "decision_pattern": snippet.get("decision_pattern"),
                    "failure_boundary": snippet.get("failure_boundary"),
                    "applicable_conditions": snippet.get("applicable_conditions"),
                }
            )
        return examples

    def _to_shared_board_row(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        if str(entry.get("scope") or "shared") != "shared":
            return None
        content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
        text = content.get("text")
        if not isinstance(text, str) or not text.strip():
            text = self._compact_output_text(content)
        agent_role = self._canonical_agent_id(entry.get("agent_role") or entry.get("agent_id"))
        if not agent_role:
            return None
        return {
            "entry_id": entry.get("entry_id"),
            "agent_role": agent_role,
            "agent_perspective": entry.get("agent_perspective") or self._agent_perspective(agent_role),
            "task_phase": entry.get("task_phase") or "execution",
            "confidence": float(entry.get("confidence") or 0.0),
            "trace_ref": entry.get("trace_ref") if isinstance(entry.get("trace_ref"), dict) else {},
            "summary_text": text[:160] if isinstance(text, str) else "",
            "kind": entry.get("kind"),
            "memory_type": entry.get("memory_type"),
        }

    def _summarize_shared_board(self, board: list[dict[str, Any]]) -> dict[str, Any]:
        by_role: dict[str, int] = {}
        for row in board:
            role = str(row.get("agent_role") or "unknown")
            by_role[role] = by_role.get(role, 0) + 1
        return {
            "item_count": len(board),
            "by_role": by_role,
            "latest": board[:5],
        }

    def _summarize_private_memory(
        self,
        private_memory_state: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        for agent_id, entries in private_memory_state.items():
            latest = entries[0] if entries else {}
            content = latest.get("content") if isinstance(latest.get("content"), dict) else {}
            summary[agent_id] = {
                "count": len(entries),
                "role": content.get("role") or agent_id,
                "current_progress": content.get("current_progress"),
                "next_intended_action": content.get("next_intended_action"),
            }
        return summary

    def _estimate_role_drift(
        self,
        *,
        shared_board: list[dict[str, Any]],
        private_memory_state: dict[str, list[dict[str, Any]]],
    ) -> float:
        total = 0
        drift = 0
        for row in shared_board:
            total += 1
            role = self._canonical_agent_id(row.get("agent_role"))
            perspective = row.get("agent_perspective")
            if role and perspective != self._agent_perspective(role):
                drift += 1
        for agent_id, entries in private_memory_state.items():
            for entry in entries:
                total += 1
                content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
                if self._canonical_agent_id(content.get("role")) != self._canonical_agent_id(agent_id):
                    drift += 1
        return round(drift / total, 4) if total else 0.0

    def _estimate_memory_cross_talk(
        self,
        *,
        private_memory_state: dict[str, list[dict[str, Any]]],
    ) -> float:
        total = 0
        cross_talk = 0
        for agent_id, entries in private_memory_state.items():
            for entry in entries:
                total += 1
                if self._canonical_agent_id(entry.get("agent_id")) != self._canonical_agent_id(agent_id):
                    cross_talk += 1
        return round(cross_talk / total, 4) if total else 0.0

    def _compact_output_text(self, payload: Any) -> str:
        if isinstance(payload, dict):
            for key in ("summary", "report", "text", "reason"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return json.dumps(self._make_json_safe(payload), ensure_ascii=False, sort_keys=True)[:200]
        if isinstance(payload, str):
            return payload[:200]
        return ""

    def _make_json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {
                str(key): self._make_json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [self._make_json_safe(item) for item in value]
        return str(value)
    
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
        os.getenv("SEMANTIC_MEMORY_ENABLED", ""),
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
