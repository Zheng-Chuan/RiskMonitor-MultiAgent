"""记忆分级 TTL 策略引擎.

Phase 6 Checkpoint 14.4.2: 记忆分级 TTL 策略.

根据记忆条目的 kind 和 memory_type 自动分配 TTL 层级:
- ephemeral: 工作态记忆, 24h 过期
- short_term: 任务记忆, 7d 过期
- long_term: 经验, 永不过期
- permanent: Skill 和配置, 永不过期

设计约束:
- 永久记忆 (long_term, permanent) 永不被 TTL 清理.
- 过期清理不影响运行中任务: 只删除已过期条目.
- 支持自定义覆盖: custom_overrides 可覆盖默认 kind -> tier 映射.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any


class TTLTier(str, Enum):
    """TTL 层级枚举."""

    EPHEMERAL = "ephemeral"       # 工作态, 24h
    SHORT_TERM = "short_term"     # 任务记忆, 7d
    LONG_TERM = "long_term"       # 经验, 永久（不过期）
    PERMANENT = "permanent"       # Skill, 配置, 永久（不过期）


# TTL 秒数（None 表示永不过期）
TTL_SECONDS: dict[TTLTier, int | None] = {
    TTLTier.EPHEMERAL: 86400,       # 24 hours
    TTLTier.SHORT_TERM: 604800,    # 7 days
    TTLTier.LONG_TERM: None,        # Never expire
    TTLTier.PERMANENT: None,       # Never expire
}

# kind 到 TTL 层级的映射规则
KIND_TO_TTL_TIER: dict[str, TTLTier] = {
    # ephemeral: 工作态记忆
    "working": TTLTier.EPHEMERAL,
    "working_memory": TTLTier.EPHEMERAL,
    "private_task_state": TTLTier.EPHEMERAL,
    "plan": TTLTier.EPHEMERAL,
    "step": TTLTier.EPHEMERAL,
    "command": TTLTier.EPHEMERAL,
    "receipt": TTLTier.EPHEMERAL,
    "approval": TTLTier.EPHEMERAL,
    "message": TTLTier.EPHEMERAL,

    # short_term: 任务记忆
    "final": TTLTier.SHORT_TERM,
    "analysis": TTLTier.SHORT_TERM,
    "task": TTLTier.SHORT_TERM,
    "experience_rejection": TTLTier.SHORT_TERM,
    "intent_disambiguation": TTLTier.SHORT_TERM,

    # long_term: 经验（永久保存）
    "lesson": TTLTier.LONG_TERM,
    "semantic_case": TTLTier.LONG_TERM,
    "few_shot": TTLTier.LONG_TERM,
    "knowledge": TTLTier.LONG_TERM,
    "fact": TTLTier.LONG_TERM,
    "example": TTLTier.LONG_TERM,

    # permanent: Skill 和配置（永久保存）
    "skill": TTLTier.PERMANENT,
    "policy": TTLTier.PERMANENT,
    "config": TTLTier.PERMANENT,
    "procedure": TTLTier.PERMANENT,
    "playbook": TTLTier.PERMANENT,
}

# memory_type 到默认 TTL 层级的兜底映射
_MEMORY_TYPE_DEFAULT_TIER: dict[str, TTLTier] = {
    "procedural": TTLTier.LONG_TERM,
    "semantic": TTLTier.LONG_TERM,
    "episodic": TTLTier.SHORT_TERM,
}

# 永不过期的层级集合
_NON_EXPIRING_TIERS: frozenset[TTLTier] = frozenset({TTLTier.LONG_TERM, TTLTier.PERMANENT})

# 需要落盘的层级集合
_PERSIST_TIERS: frozenset[TTLTier] = frozenset({TTLTier.LONG_TERM, TTLTier.PERMANENT})


class TTLPolicyEngine:
    """记忆分级 TTL 策略引擎."""

    def __init__(self, *, custom_overrides: dict[str, TTLTier] | None = None) -> None:
        """初始化 TTL 策略引擎.

        Args:
            custom_overrides: 允许覆盖默认的 kind -> tier 映射.
        """
        self._overrides: dict[str, TTLTier] = dict(custom_overrides) if custom_overrides else {}

    def classify(self, entry: dict[str, Any]) -> TTLTier:
        """根据 memory entry 的 kind 和 memory_type 自动分配 TTL 层级.

        优先级:
        1. 如果 entry 中已有 ttl_tier 字段, 直接使用
        2. custom_overrides 覆盖
        3. KIND_TO_TTL_TIER 默认映射
        4. 兜底: 根据 memory_type 推断
           - procedural -> long_term
           - semantic -> long_term
           - episodic -> short_term
        5. 最终兜底: ephemeral

        Args:
            entry: 记忆条目 dict

        Returns:
            TTLTier 枚举值
        """
        # 1. 如果 entry 中已有 ttl_tier 字段, 直接使用
        raw_tier = entry.get("ttl_tier")
        if raw_tier is not None:
            tier = self._parse_tier(raw_tier)
            if tier is not None:
                return tier

        kind = str(entry.get("kind") or "")

        # 2. custom_overrides 覆盖
        if kind in self._overrides:
            return self._overrides[kind]

        # 3. KIND_TO_TTL_TIER 默认映射
        if kind in KIND_TO_TTL_TIER:
            return KIND_TO_TTL_TIER[kind]

        # 4. 兜底: 根据 memory_type 推断
        memory_type = str(entry.get("memory_type") or "")
        if memory_type in _MEMORY_TYPE_DEFAULT_TIER:
            return _MEMORY_TYPE_DEFAULT_TIER[memory_type]

        # 5. 最终兜底: ephemeral
        return TTLTier.EPHEMERAL

    def get_ttl_seconds(self, entry: dict[str, Any]) -> int | None:
        """获取 entry 对应的 TTL 秒数. None 表示永不过期.

        Args:
            entry: 记忆条目 dict

        Returns:
            TTL 秒数, None 表示永不过期
        """
        tier = self.classify(entry)
        return TTL_SECONDS.get(tier)

    def should_persist(self, entry: dict[str, Any]) -> bool:
        """判断 entry 是否需要落盘到 MySQL.

        long_term 和 permanent 级别的记忆需要落盘.
        ephemeral 和 short_term 不落盘（仅 Redis）.

        Args:
            entry: 记忆条目 dict

        Returns:
            True 表示需要落盘
        """
        tier = self.classify(entry)
        return tier in _PERSIST_TIERS

    def is_expired(self, entry: dict[str, Any], *, now_ms: int | None = None) -> bool:
        """判断 entry 是否已过期.

        永久级别（long_term, permanent）永不过期.
        其他级别根据 ts_ms + ttl_seconds 判断.

        Args:
            entry: 记忆条目 dict
            now_ms: 当前时间戳（毫秒）, 默认使用 time.time()

        Returns:
            True 表示已过期
        """
        tier = self.classify(entry)
        if tier in _NON_EXPIRING_TIERS:
            return False

        ttl_seconds = TTL_SECONDS.get(tier)
        if ttl_seconds is None:
            return False

        ts_ms = entry.get("ts_ms")
        if not isinstance(ts_ms, int) or ts_ms <= 0:
            # 无有效时间戳, 无法判断过期, 返回 False
            return False

        current_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        expiry_ms = ts_ms + ttl_seconds * 1000
        return current_ms >= expiry_ms

    def get_cleanup_candidates(
        self,
        entries: list[dict[str, Any]],
        *,
        now_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        """从给定列表中筛选出已过期的 entry, 供清理使用.

        不影响运行中任务: 只返回过期的, 调用方决定是否清理.

        Args:
            entries: 记忆条目列表
            now_ms: 当前时间戳（毫秒）

        Returns:
            已过期的 entry 列表
        """
        current_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        return [e for e in entries if self.is_expired(e, now_ms=current_ms)]

    @staticmethod
    def _parse_tier(value: Any) -> TTLTier | None:
        """将各种形式的 tier 值解析为 TTLTier 枚举.

        Args:
            value: 字符串或 TTLTier 枚举

        Returns:
            TTLTier 枚举值, None 表示无法解析
        """
        if isinstance(value, TTLTier):
            return value
        if isinstance(value, str):
            try:
                return TTLTier(value)
            except ValueError:
                return None
        return None
