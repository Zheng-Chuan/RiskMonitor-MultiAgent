"""
统一内存存储系统.

融合短期工作记忆(Redis)、长期运行上下文(Redis Hash)和长期语义经验(内置索引).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

from riskmonitor_multiagent.contracts.memory_entry import normalize_memory_entry
from riskmonitor_multiagent.memory.memory_helpers import (
    _DEFAULT_PRIVATE_AGENT_IDS,
    build_planning_query,
    canonical_agent_id,
    dedupe_memory_hits,
    estimate_memory_cross_talk,
    estimate_role_drift,
    extract_few_shot_examples,
    summarize_hits,
    summarize_private_memory,
    summarize_shared_board,
    to_shared_board_row,
)
from riskmonitor_multiagent.memory.memory_operations import MemoryWriteOperationsMixin
from riskmonitor_multiagent.memory.redis_backend import RedisBackend
from riskmonitor_multiagent.memory.semantic_indexer import SemanticIndexer


@dataclass
class MemoryConfig:
    """内存存储配置."""
    redis_url: str
    default_ttl: int = 86400  # 24小时
    max_list_len: int = 2000
    enable_semantic_memory: bool = True


class MemoryStore(MemoryWriteOperationsMixin):
    """统一内存存储.

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
        self._backend = RedisBackend(config.redis_url)
        self._semantic = SemanticIndexer()

        # 向后兼容: 暴露内部 Redis 连接和语义索引
        self._redis = None
        self._semantic_index = self._semantic.index
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

    async def _ensure_connected(self):
        """确保 Redis 连接(向后兼容)."""
        # 支持测试直接设置 store._redis = mock_redis
        if self._redis is not None and self._backend._redis is None:
            self._backend._redis = self._redis
            return self._redis
        r = await self._backend.ensure_connected()
        self._redis = r
        return r

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
        await self._ensure_connected()

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
        effective_ttl = ttl or self._config.default_ttl
        await self._backend.append_to_list(
            key, entry_json, max_len=self._config.max_list_len, ttl=effective_ttl,
        )

        # 异步索引到长期语义记忆
        if scope == "shared":
            await self._semantic.index_entry(nd)

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
        await self._ensure_connected()

        # 确定查询 key
        if scope == "private":
            key = f"agent:{agent_id}:memory"
        else:
            key = "shared:memory"

        # 获取列表
        entries_json = await self._backend.list_from_key(key, limit=limit * 2)

        # 解析并过滤
        results: list[dict[str, Any]] = []
        for entry_json in entries_json:
            try:
                parsed = json.loads(entry_json)
            except json.JSONDecodeError:
                continue

            if scope == "private" and parsed.get("agent_id") != agent_id:
                continue
            if session_id is not None and parsed.get("session_id") != session_id:
                continue
            if run_id is not None and parsed.get("run_id") != run_id:
                continue
            if kinds is not None and parsed.get("kind") not in kinds:
                continue
            if memory_types is not None and parsed.get("memory_type") not in memory_types:
                continue

            results.append(parsed)
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
            session_id=session_id, run_id=run_id, limit=max(limit * 2, 6),
        )
        private_memory_state: dict[str, list[dict[str, Any]]] = {}
        if private_memory_enabled:
            private_memory_state = await self.get_private_memory_state(
                session_id=session_id, run_id=run_id,
                agent_ids=_DEFAULT_PRIVATE_AGENT_IDS, limit=3,
            )

        semantic_reserve = 1 if limit <= 2 else 2
        recent_limit = max(1, limit - semantic_reserve)
        recent_hits = await self.list_recent(
            agent_id="orchestrator", scope="shared", session_id=session_id,
            kinds=["plan", "final", "analysis", "intent_disambiguation", "lesson", "approval"],
            memory_types=["episodic", "procedural"], limit=recent_limit,
        )
        semantic_hits = await self.search_semantic(
            build_planning_query(content=content, intent_type=intent_type),
            agent_id="orchestrator",
            limit=max(1, limit - min(len(recent_hits), recent_limit)),
        )
        recent_semantic_cases = await self.list_recent(
            agent_id="orchestrator", scope="shared", session_id=session_id,
            kinds=["semantic_case"], memory_types=["semantic"], limit=semantic_reserve,
        )
        for entry in recent_semantic_cases:
            reusable_snippet = self._semantic.build_reusable_snippet(entry)
            if reusable_snippet:
                entry["reusable_snippet"] = reusable_snippet

        hits = dedupe_memory_hits(recent_hits + semantic_hits + recent_semantic_cases, limit=limit)
        summary = summarize_hits(hits)
        summary["shared_board"] = summarize_shared_board(shared_board)
        summary["private_memory"] = summarize_private_memory(private_memory_state)
        summary["few_shot_examples"] = extract_few_shot_examples(hits)
        summary["few_shot_example_count"] = len(summary["few_shot_examples"])
        summary["role_drift_rate"] = estimate_role_drift(
            shared_board=shared_board, private_memory_state=private_memory_state,
        )
        summary["memory_cross_talk_rate"] = estimate_memory_cross_talk(
            private_memory_state=private_memory_state,
        )
        return {
            "hits": hits,
            "summary": summary,
            "shared_board": shared_board,
            "private_memory_state": private_memory_state,
        }

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
            agent_id="orchestrator", scope="shared", run_id=run_id, limit=50,
        )
        shared_memory_board = await self.get_shared_memory_board(run_id=run_id, limit=30)
        private_memory_state = await self.get_private_memory_state(
            run_id=run_id, agent_ids=_DEFAULT_PRIVATE_AGENT_IDS, limit=10,
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

    async def save_run_context(self, run_id: str, event_id: str, data: dict[str, Any]) -> None:
        """保存运行上下文(原 ContextStore 功能)."""
        await self._ensure_connected()
        await self._backend.save_run_context(run_id, event_id, data)

    async def get_run_context(self, run_id: str) -> dict[str, Any] | None:
        """获取运行上下文."""
        await self._ensure_connected()
        return await self._backend.get_run_context(run_id)

    async def get_context_by_event(self, event_id: str, latest: bool = True) -> dict[str, Any] | None:
        """通过事件 ID 查找运行上下文."""
        await self._ensure_connected()
        return await self._backend.get_context_by_event(event_id, latest)

    async def update_run_context(self, run_id: str, patch: dict[str, Any]) -> None:
        """增量更新运行上下文."""
        await self._ensure_connected()
        await self._backend.update_run_context(run_id, patch)

    # ==================== 运行总结 ====================

    async def upsert_run_summary(self, *, run_id: str, summary: dict[str, Any]) -> None:
        """保存运行总结."""
        await self._ensure_connected()
        await self._backend.upsert_run_summary(run_id=run_id, summary=summary)

    async def get_run_summary(self, run_id: str) -> dict[str, Any] | None:
        """获取运行总结."""
        await self._ensure_connected()
        return await self._backend.get_run_summary(run_id)

    # ==================== 长期语义经验 ====================

    async def search_semantic(
        self,
        query: str,
        *,
        agent_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """语义搜索长期记忆."""
        return await self._semantic.search(
            query, enabled=self._config.enable_semantic_memory, agent_id=agent_id, limit=limit,
        )

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
        for aid in agent_ids:
            cid = canonical_agent_id(aid)
            if not cid:
                continue
            snapshots[cid] = await self.list_recent(
                agent_id=cid, scope="private", session_id=session_id, run_id=run_id, limit=limit,
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
            agent_id="orchestrator", scope="shared",
            session_id=session_id, run_id=run_id, limit=max(limit * 2, 20),
        )
        board: list[dict[str, Any]] = []
        for entry in entries:
            row = to_shared_board_row(entry)
            if row is None:
                continue
            board.append(row)
            if len(board) >= limit:
                break
        return board

    # ==================== 生命周期 ====================

    async def close(self) -> None:
        """关闭连接."""
        await self._backend.close()
        self._redis = None

    async def health_check(self) -> bool:
        """健康检查."""
        return await self._backend.health_check()


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
