"""Cache 抽象预留点.

说明:
- Week2 先提供接口与 Noop 实现
- 后续可替换为 redis 或本地 cache, 不影响上层调用方
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Optional, Protocol, TypeVar


T = TypeVar("T")


class Cache(Protocol, Generic[T]):
    # 读取 key
    def get(self, key: str) -> Optional[T]:
        ...

    # 写入 key
    def set(self, key: str, value: T, ttl_s: Optional[int] = None) -> None:
        ...


@dataclass(frozen=True)
class NoopCache(Generic[T]):
    # 不做任何缓存, 用于默认实现
    def get(self, key: str) -> Optional[T]:
        del key

    def set(self, key: str, value: T, ttl_s: Optional[int] = None) -> None:
        del key
        del value
        del ttl_s
