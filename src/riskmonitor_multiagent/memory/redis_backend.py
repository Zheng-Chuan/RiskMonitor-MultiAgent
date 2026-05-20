"""
Redis 后端操作模块.

封装所有 Redis 底层操作,包括连接管理、读写和数据序列化.
"""

from __future__ import annotations

import json
import time
from typing import Any

import redis.asyncio as redis

from riskmonitor_multiagent.memory.semantic_indexer import _make_json_safe


class RedisBackend:
    """Redis 底层操作封装."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis: redis.Redis | None = None

    async def ensure_connected(self) -> redis.Redis:
        """确保 Redis 连接."""
        if self._redis is None:
            self._redis = await redis.from_url(
                self._redis_url,
                decode_responses=True,
            )
        return self._redis

    async def append_to_list(
        self,
        key: str,
        entry_json: str,
        *,
        max_len: int,
        ttl: int,
    ) -> None:
        """向 Redis List 追加条目并维护长度和 TTL."""
        r = await self.ensure_connected()
        pipe = r.pipeline()
        pipe.lpush(key, entry_json)
        pipe.ltrim(key, 0, max_len - 1)
        pipe.expire(key, ttl)
        await pipe.execute()

    async def list_from_key(self, key: str, *, limit: int) -> list[str]:
        """从 Redis List 获取条目."""
        r = await self.ensure_connected()
        return await r.lrange(key, 0, limit - 1)

    # ==================== 运行上下文 ====================

    async def save_run_context(
        self,
        run_id: str,
        event_id: str,
        data: dict[str, Any],
    ) -> None:
        """
        保存运行上下文.

        存储完整的运行状态到 Redis Hash.

        Args:
            run_id: 运行标识
            event_id: 事件/任务标识
            data: 完整运行数据
        """
        r = await self.ensure_connected()

        key = f"context:{run_id}"
        payload = {
            "run_id": run_id,
            "event_id": event_id,
            "created_at_ms": int(time.time() * 1000),
            "data": data,
        }

        await r.hset(key, mapping={
            "payload": json.dumps(payload, ensure_ascii=False),
        })

        # 创建事件索引
        await r.hset(f"event_index:{event_id}", run_id, key)

    async def get_run_context(self, run_id: str) -> dict[str, Any] | None:
        """获取运行上下文."""
        r = await self.ensure_connected()

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
        r = await self.ensure_connected()

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
        r = await self.ensure_connected()

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
        r = await self.ensure_connected()

        key = f"summary:{run_id}"
        await r.hset(key, mapping={
            "payload": json.dumps(summary, ensure_ascii=False),
            "updated_at": int(time.time()),
        })

    async def get_run_summary(self, run_id: str) -> dict[str, Any] | None:
        """获取运行总结."""
        r = await self.ensure_connected()

        key = f"summary:{run_id}"
        result = await r.hget(key, "payload")

        if not result:
            return None

        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return None

    # ==================== 生命周期 ====================

    async def close(self) -> None:
        """关闭连接."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def health_check(self) -> bool:
        """健康检查."""
        try:
            r = await self.ensure_connected()
            await r.ping()
            return True
        except Exception:
            return False
