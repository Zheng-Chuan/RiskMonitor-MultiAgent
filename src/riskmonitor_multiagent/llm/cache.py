"""LLM 调用缓存模块.

提供 LLM 调用缓存功能,避免重复请求相同的 prompt,提升性能.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """缓存条目."""
    key: str
    response: dict[str, Any]
    timestamp: float
    ttl: Optional[float] = None  # None 表示永久缓存


class LLMCache:
    """LLM 调用缓存(纯内存实现)."""

    def __init__(self, max_size: int = 1000) -> None:
        """
        初始化缓存.

        Args:
            max_size: 最大缓存条目数量,超过会淘汰最旧的
        """
        self._cache: dict[str, CacheEntry] = {}
        self._max_size = max_size

    def _compute_key(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """
        计算缓存 key.

        根据 messages、model、temperature 等参数计算唯一的 hash key.
        """
        key_data = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **{k: v for k, v in kwargs.items() if k not in {"stream", "logprobs", "n"}},
        }
        key_json = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(key_json.encode()).hexdigest()

    def get(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Optional[dict[str, Any]]:
        """
        从缓存获取响应.

        Returns:
            缓存的响应,如果没有命中返回 None
        """
        key = self._compute_key(messages, model, temperature, max_tokens, **kwargs)
        entry = self._cache.get(key)
        if entry:
            logger.debug(f"Cache hit for key: {key[:16]}...")
            return entry.response
        logger.debug(f"Cache miss for key: {key[:16]}...")
        return None

    def set(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int] = None,
        response: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """
        写入缓存.

        Args:
            response: LLM 返回的响应
        """
        if response is None:
            return

        key = self._compute_key(messages, model, temperature, max_tokens, **kwargs)

        # 淘汰策略:如果超过 max_size,删除最旧的
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].timestamp)
            del self._cache[oldest_key]
            logger.debug(f"Cache evicted: {oldest_key[:16]}...")

        import time
        self._cache[key] = CacheEntry(
            key=key,
            response=response,
            timestamp=time.time(),
        )
        logger.debug(f"Cache set for key: {key[:16]}...")

    def clear(self) -> None:
        """清空缓存."""
        self._cache.clear()
        logger.debug("Cache cleared")

    def size(self) -> int:
        """获取当前缓存大小."""
        return len(self._cache)


# 全局缓存实例
_llm_cache: Optional[LLMCache] = None


def get_llm_cache(max_size: int = 1000) -> LLMCache:
    """
    获取全局 LLM 缓存实例.

    Args:
        max_size: 首次初始化时的最大缓存大小

    Returns:
        LLMCache 实例
    """
    global _llm_cache
    if _llm_cache is None:
        _llm_cache = LLMCache(max_size=max_size)
    return _llm_cache


def reset_llm_cache() -> None:
    """重置缓存(用于测试)."""
    global _llm_cache
    _llm_cache = None
