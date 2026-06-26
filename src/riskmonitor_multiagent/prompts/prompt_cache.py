"""Prompt 缓存管理器.

为三层 prompt 分离策略提供内存态缓存, 减少 stable_tier 和 context_tier 的重复构建开销.

设计约束:
1. 缓存是内存态 (不需要 Redis)
2. volatile_tier 不参与缓存
3. 缓存键 = stable_version + context_date
4. 支持按版本号或日期失效缓存
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class PromptCacheManager:
    """prompt 缓存管理器.

    缓存 cacheable 层级 (stable, context) 的构建结果, 减少重复构建开销.
    内部使用 dict 存储, 支持按版本号或日期失效.
    """

    def __init__(self) -> None:
        """初始化缓存管理器."""
        # cache_key → {content, version, created_at}
        self._cache: dict[str, dict[str, Any]] = {}
        self._hit_count: int = 0
        self._miss_count: int = 0

    def get(self, cache_key: str) -> dict[str, Any] | None:
        """获取缓存.

        命中时 hit_count += 1, 未命中 miss_count += 1.

        Args:
            cache_key: 缓存键

        Returns:
            缓存内容 dict, 未命中返回 None
        """
        entry = self._cache.get(cache_key)
        if entry is not None:
            self._hit_count += 1
            logger.debug("Prompt cache hit: %s", cache_key)
            return dict(entry)  # 返回副本, 避免外部修改
        else:
            self._miss_count += 1
            logger.debug("Prompt cache miss: %s", cache_key)
            return None

    def set(self, cache_key: str, content: str, version: str) -> None:
        """设置缓存.

        Args:
            cache_key: 缓存键
            content: 缓存的 prompt 内容
            version: 版本标识
        """
        self._cache[cache_key] = {
            "content": content,
            "version": version,
            "created_at": time.time(),
        }
        logger.debug("Prompt cache set: %s (version=%s)", cache_key, version)

    def invalidate(
        self,
        *,
        version: str | None = None,
        date: str | None = None,
    ) -> int:
        """失效缓存.

        - version: 失效指定 stable_version 的缓存
        - date: 失效指定日期的缓存
        - 都不提供: 失效所有缓存

        Args:
            version: 失效匹配此 stable_version 的缓存
            date: 失效匹配此 context_date 的缓存

        Returns:
            失效的缓存数量
        """
        if version is None and date is None:
            # 失效所有缓存
            count = len(self._cache)
            self._cache.clear()
            logger.info("Prompt cache invalidated all (%d entries)", count)
            return count

        # 收集需要删除的 key
        keys_to_remove: list[str] = []
        for cache_key, entry in self._cache.items():
            # cache_key 格式: "stable_version:context_date"
            # entry.version 存储的是设置的版本号
            should_remove = False

            if version is not None and date is not None:
                # 同时匹配 version 和 date
                # cache_key 格式: "stable_version:context_date"
                parts = cache_key.split(":", 1)
                if len(parts) == 2:
                    cache_version, cache_date = parts
                    if cache_version == version and cache_date == date:
                        should_remove = True
            elif version is not None:
                # 匹配 version (stable_version 部分或 entry.version)
                parts = cache_key.split(":", 1)
                if len(parts) >= 1 and parts[0] == version:
                    should_remove = True
                elif entry.get("version") == version:
                    should_remove = True
            elif date is not None:
                # 匹配 date (context_date 部分)
                parts = cache_key.split(":", 1)
                if len(parts) == 2 and parts[1] == date:
                    should_remove = True

            if should_remove:
                keys_to_remove.append(cache_key)

        for key in keys_to_remove:
            del self._cache[key]

        logger.info(
            "Prompt cache invalidated: %d entries (version=%s, date=%s)",
            len(keys_to_remove),
            version,
            date,
        )
        return len(keys_to_remove)

    def get_stats(self) -> dict[str, Any]:
        """获取缓存统计.

        Returns:
            统计 dict: hit_count, miss_count, hit_rate, cache_size
        """
        total = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total if total > 0 else 0.0
        return {
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate": hit_rate,
            "cache_size": len(self._cache),
        }

    def clear(self) -> None:
        """清空所有缓存."""
        self._cache.clear()
        self._hit_count = 0
        self._miss_count = 0
        logger.info("Prompt cache cleared")


__all__ = [
    "PromptCacheManager",
]
