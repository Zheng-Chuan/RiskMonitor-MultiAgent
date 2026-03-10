"""
统一内存存储系统.

融合原 UnifiedMemory 和 ContextStore 功能，提供:
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

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import redis.asyncio as redis

from riskmonitor_multiagent.contracts.memory_entry import normalize_memory_entry


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
    1. 短期记忆: Agent 独立 + 共享，支持 TTL
    2. 长期上下文: 完整运行状态，持久化
    3. 长期语义: PageIndex 向量检索
    """

    def __init__(self, config: MemoryConfig | None = None) -> None:
        """初始化内存存储."""
        if config is None:
            config = self._default_config()
        
        self._config = config
        self._redis: redis.Redis | None = None
        self._page_index = None
        
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
            agent_id: Agent 标识（scope=private 时必填）
            scope: "private" 或 "shared"
            ttl: 过期时间（秒），默认使用配置值
        
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
        
        # 异步索引到 PageIndex（如果有启用）
        if self._config.enable_page_index and scope == "shared":
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
            记忆条目列表（按时间倒序）
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
            
            results.append(entry)
            if len(results) >= limit:
                break
        
        return results
    
    # ==================== 长期运行上下文 ====================
    
    async def save_run_context(
        self,
        run_id: str,
        event_id: str,
        data: dict[str, Any],
    ) -> None:
        """
        保存运行上下文（原 ContextStore 功能）.
        
        存储完整的运行状态到 Redis Hash，支持:
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
            latest: 是否返回最新的（默认）或最早的
        
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
        索引到 PageIndex（长期语义记忆）.
        
        仅索引重要类型的条目（plan, final）。
        """
        if not self._config.enable_page_index:
            return
        
        kind = entry.get("kind")
        if kind not in {"plan", "final", "analysis"}:
            return
        
        content = entry.get("content", {})
        text = content.get("text") if isinstance(content, dict) else None
        
        if not text:
            return
        
        # TODO: 实现 PageIndex 客户端调用
        # 这里预留接口，实际实现需要 PageIndex SDK
        pass
    
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
        
        # TODO: 实现 PageIndex 搜索
        # 预留接口
        return []
    
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
    
    根据环境变量变化自动重建。
    """
    global _MEMORY_STORE, _MEMORY_CONFIG_SIG
    
    sig = (
        os.getenv("REDIS_URL", ""),
        os.getenv("MEMORY_TTL_S", ""),
        os.getenv("PAGE_INDEX_ENABLED", ""),
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
