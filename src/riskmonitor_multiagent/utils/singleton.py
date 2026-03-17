"""
全局单例管理器.

统一管理全局实例，避免重复的单例管理代码.
"""

from __future__ import annotations

from typing import Any, Callable, Optional


class SingletonManager:
    """
    全局单例管理器.

    统一管理全局实例，提供：
    - 获取单例实例
    - 重置单例实例
    - 批量重置所有单例
    """

    _instances: dict[str, Any] = {}

    @classmethod
    def get(cls, key: str, factory: Callable[[], Any]) -> Any:
        """
        获取单例实例.

        Args:
            key: 实例的唯一标识
            factory: 创建实例的工厂函数

        Returns:
            单例实例
        """
        if key not in cls._instances:
            cls._instances[key] = factory()
        return cls._instances[key]

    @classmethod
    def reset(cls, key: Optional[str] = None) -> None:
        """
        重置单例实例.

        Args:
            key: 可选的实例标识，如果为 None 则重置所有实例
        """
        if key:
            cls._instances.pop(key, None)
        else:
            cls._instances.clear()

    @classmethod
    def has(cls, key: str) -> bool:
        """
        检查是否存在指定的单例实例.

        Args:
            key: 实例的唯一标识

        Returns:
            是否存在该实例
        """
        return key in cls._instances
