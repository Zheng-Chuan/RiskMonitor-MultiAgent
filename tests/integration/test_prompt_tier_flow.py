"""三层 prompt 分离集成测试.

测试场景:
1. 构建 prompt → 缓存 → 第二次构建命中缓存
2. 版本变更 → 缓存失效
3. 日内多次调用 → context_tier 共享缓存
4. volatile_tier 变化不影响 stable_tier 缓存
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.prompts.prompt_cache import PromptCacheManager
from riskmonitor_multiagent.prompts.tiered_prompt_builder import (
    PromptTier,
    TieredPromptBuilder,
)


# ---------------------------------------------------------------------------
# 辅助: 构建带缓存的 prompt
# ---------------------------------------------------------------------------


def build_and_cache(
    builder: TieredPromptBuilder,
    cache: PromptCacheManager,
    *,
    agent_role: str = "You are a risk analyst.",
    tools_index: list[dict] | None = None,
    behavior_rules: list[str] | None = None,
    skills: list[dict] | None = None,
    project_rules: list[str] | None = None,
    memory_summary: dict[str, Any] | None = None,
    current_event: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
    react_history: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """构建三层 prompt, 使用缓存加速 stable 和 context 层.

    Returns:
        assembled messages
    """
    tools_index = tools_index or [{"name": "check_alerts", "desc": "Check alerts"}]
    behavior_rules = behavior_rules or ["Always verify sources.", "Report immediately."]
    skills = skills or [{"name": "risk_analysis", "desc": "Analyze risks"}]
    project_rules = project_rules or ["Follow compliance rules."]
    task = task or {"task_id": "task_001"}

    # 1. 构建 stable_tier (先查缓存)
    stable = builder.build_stable_tier(
        agent_role=agent_role,
        tools_index=tools_index,
        behavior_rules=behavior_rules,
    )

    # 2. 构建 context_tier (先查缓存)
    context = builder.build_context_tier(
        skills=skills,
        project_rules=project_rules,
        memory_summary=memory_summary,
    )

    # 3. 构建 volatile_tier (不缓存)
    volatile = builder.build_volatile_tier(
        current_event=current_event,
        task=task,
        react_history=react_history,
    )

    # 缓存 stable + context
    cache_key = builder.get_cache_key(stable, context)
    cached = cache.get(cache_key)
    if cached is None:
        cache.set(cache_key, stable.content + "\n" + context.content, stable.version)

    return builder.assemble_messages(stable, context, volatile)


# ---------------------------------------------------------------------------
# 1. 构建 prompt → 缓存 → 第二次构建命中缓存
# ---------------------------------------------------------------------------


class TestCacheHitOnRebuild:
    """测试构建后缓存, 第二次构建命中."""

    def test_second_build_hits_cache(self):
        """第二次构建命中缓存."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")
        cache = PromptCacheManager()

        # 第一次构建 → miss
        build_and_cache(builder, cache)
        stats_after_first = cache.get_stats()
        assert stats_after_first["miss_count"] == 1
        assert stats_after_first["hit_count"] == 0

        # 第二次构建 → hit
        build_and_cache(builder, cache)
        stats_after_second = cache.get_stats()
        assert stats_after_second["hit_count"] == 1
        assert stats_after_second["miss_count"] == 1

    def test_cache_hit_rate_increases(self):
        """多次构建后命中率上升."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")
        cache = PromptCacheManager()

        # 3 次构建
        for _ in range(3):
            build_and_cache(builder, cache)

        stats = cache.get_stats()
        # 1 miss + 2 hits
        assert stats["miss_count"] == 1
        assert stats["hit_count"] == 2
        assert stats["hit_rate"] == 2 / 3


# ---------------------------------------------------------------------------
# 2. 版本变更 → 缓存失效
# ---------------------------------------------------------------------------


class TestVersionInvalidation:
    """测试版本变更后缓存失效."""

    def test_stable_version_change_creates_new_cache_key(self):
        """stable_version 变更后生成新的缓存键."""
        builder_v1 = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")
        builder_v2 = TieredPromptBuilder(stable_version="v2", context_date="2025-06-26")
        cache = PromptCacheManager()

        # v1 构建并缓存
        stable_v1 = builder_v1.build_stable_tier(
            agent_role="Agent", tools_index=[], behavior_rules=[],
        )
        context_v1 = builder_v1.build_context_tier(skills=[], project_rules=[])
        key_v1 = builder_v1.get_cache_key(stable_v1, context_v1)
        cache.set(key_v1, "content_v1", "v1")

        # v2 构建并缓存
        stable_v2 = builder_v2.build_stable_tier(
            agent_role="Agent", tools_index=[], behavior_rules=[],
        )
        context_v2 = builder_v2.build_context_tier(skills=[], project_rules=[])
        key_v2 = builder_v2.get_cache_key(stable_v2, context_v2)

        # 缓存键不同
        assert key_v1 != key_v2

        # v1 的缓存存在, v2 的不存在
        assert cache.get(key_v1) is not None
        assert cache.get(key_v2) is None

    def test_invalidate_by_version_removes_stale(self):
        """按 version 失效后, 旧缓存被清除."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")
        cache = PromptCacheManager()

        # 构建并缓存
        stable = builder.build_stable_tier(
            agent_role="Agent", tools_index=[], behavior_rules=[],
        )
        context = builder.build_context_tier(skills=[], project_rules=[])
        key = builder.get_cache_key(stable, context)
        cache.set(key, "content", "v1")

        # 验证缓存存在
        assert cache.get(key) is not None

        # 失效 v1 缓存
        count = cache.invalidate(version="v1")
        assert count == 1

        # 缓存已清除
        assert cache.get(key) is None

    def test_version_change_cache_miss(self):
        """版本变更后第二次构建是 cache miss."""
        builder_v1 = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")
        cache = PromptCacheManager()

        # v1 构建
        build_and_cache(builder_v1, cache)

        # 切换到 v2
        builder_v2 = TieredPromptBuilder(stable_version="v2", context_date="2025-06-26")
        build_and_cache(builder_v2, cache)

        stats = cache.get_stats()
        # 2 misses, 0 hits (不同版本不同 key)
        assert stats["miss_count"] == 2
        assert stats["hit_count"] == 0


# ---------------------------------------------------------------------------
# 3. 日内多次调用 → context_tier 共享缓存
# ---------------------------------------------------------------------------


class TestContextTierDailyCacheSharing:
    """测试日内多次调用共享 context_tier 缓存."""

    def test_same_day_shares_cache(self):
        """同一天多次调用共享缓存."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")
        cache = PromptCacheManager()

        # 第一次调用
        build_and_cache(builder, cache)

        # 第二次调用 (同一天, 不同 volatile 内容)
        build_and_cache(
            builder,
            cache,
            current_event={"type": "new_event"},
            task={"task_id": "different_task"},
        )

        # 第三次调用 (同一天)
        build_and_cache(
            builder,
            cache,
            current_event={"type": "another_event"},
            task={"task_id": "yet_another"},
        )

        stats = cache.get_stats()
        # 1 miss + 2 hits (stable+context 版本不变, 缓存键不变)
        assert stats["miss_count"] == 1
        assert stats["hit_count"] == 2

    def test_context_tier_version_same_within_day(self):
        """同一天 context_tier 版本一致."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")

        context1 = builder.build_context_tier(
            skills=[{"name": "skill_a"}], project_rules=["rule_a"],
        )
        context2 = builder.build_context_tier(
            skills=[{"name": "skill_b"}], project_rules=["rule_b"],
        )

        # 版本一致 (日期戳)
        assert context1.version == context2.version
        assert context1.version == "2025-06-26"

    def test_different_days_different_cache_keys(self):
        """不同日期生成不同缓存键."""
        builder_day1 = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")
        builder_day2 = TieredPromptBuilder(stable_version="v1", context_date="2025-06-27")

        stable1 = builder_day1.build_stable_tier(
            agent_role="Agent", tools_index=[], behavior_rules=[],
        )
        context1 = builder_day1.build_context_tier(skills=[], project_rules=[])
        key1 = builder_day1.get_cache_key(stable1, context1)

        stable2 = builder_day2.build_stable_tier(
            agent_role="Agent", tools_index=[], behavior_rules=[],
        )
        context2 = builder_day2.build_context_tier(skills=[], project_rules=[])
        key2 = builder_day2.get_cache_key(stable2, context2)

        assert key1 != key2


# ---------------------------------------------------------------------------
# 4. volatile_tier 变化不影响 stable_tier 缓存
# ---------------------------------------------------------------------------


class TestVolatileTierIsolation:
    """测试 volatile_tier 变化不影响 stable_tier 缓存."""

    def test_volatile_change_preserves_stable_cache(self):
        """volatile_tier 变化, stable_tier 缓存仍然命中."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")
        cache = PromptCacheManager()

        # 第一次构建
        stable1 = builder.build_stable_tier(
            agent_role="Agent", tools_index=[], behavior_rules=[],
        )
        context1 = builder.build_context_tier(skills=[], project_rules=[])
        volatile1 = builder.build_volatile_tier(
            current_event=None, task={"id": "task_1"},
        )
        key = builder.get_cache_key(stable1, context1)
        cache.set(key, stable1.content, stable1.version)
        cache.get(key)  # hit

        # volatile 变化 (确保时间戳不同)
        time.sleep(0.002)
        volatile2 = builder.build_volatile_tier(
            current_event={"type": "alert"}, task={"id": "task_2"},
        )

        # stable_tier 缓存仍然命中
        result = cache.get(key)
        assert result is not None
        assert result["content"] == stable1.content

        # volatile_tier 版本不同
        assert volatile1.version != volatile2.version

    def test_volatile_does_not_affect_cache_key(self):
        """volatile_tier 不影响缓存键."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")

        stable = builder.build_stable_tier(
            agent_role="Agent", tools_index=[], behavior_rules=[],
        )
        context = builder.build_context_tier(skills=[], project_rules=[])

        # 构建不同的 volatile_tier
        volatile1 = builder.build_volatile_tier(
            current_event=None, task={"id": "1"},
        )
        time.sleep(0.002)
        volatile2 = builder.build_volatile_tier(
            current_event={"type": "alert"}, task={"id": "2"},
        )

        # 缓存键相同 (不包含 volatile 信息)
        key1 = builder.get_cache_key(stable, context)
        key2 = builder.get_cache_key(stable, context)
        assert key1 == key2

    def test_volatile_not_cached(self):
        """volatile_tier 不被缓存 (cacheable=False)."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")

        volatile = builder.build_volatile_tier(
            current_event=None, task={"id": "1"},
        )
        assert volatile.cacheable is False


# ---------------------------------------------------------------------------
# 5. 端到端流程测试
# ---------------------------------------------------------------------------


class TestEndToEndFlow:
    """端到端流程测试."""

    def test_full_workflow_with_caching(self):
        """完整工作流: 构建 → 缓存 → 重建 → 命中."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")
        cache = PromptCacheManager()

        # 1. 第一次构建 (miss)
        msgs1 = build_and_cache(builder, cache, current_event={"type": "alert_1"})
        assert len(msgs1) == 3

        # 2. 第二次构建 (hit) - volatile 变化
        msgs2 = build_and_cache(builder, cache, current_event={"type": "alert_2"})
        assert len(msgs2) == 3

        # 3. 验证缓存统计
        stats = cache.get_stats()
        assert stats["miss_count"] == 1
        assert stats["hit_count"] == 1
        assert stats["cache_size"] == 1

    def test_stable_tier_consistent_across_rebuilds(self):
        """多次重建后 stable_tier 内容一致."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")

        # 相同输入, 多次构建
        tier1 = builder.build_stable_tier(
            agent_role="You are a risk analyst.",
            tools_index=[{"name": "tool_a", "desc": "Tool A"}],
            behavior_rules=["Rule 1", "Rule 2"],
        )
        tier2 = builder.build_stable_tier(
            agent_role="You are a risk analyst.",
            tools_index=[{"name": "tool_a", "desc": "Tool A"}],
            behavior_rules=["Rule 1", "Rule 2"],
        )
        tier3 = builder.build_stable_tier(
            agent_role="You are a risk analyst.",
            tools_index=[{"name": "tool_a", "desc": "Tool A"}],
            behavior_rules=["Rule 1", "Rule 2"],
        )

        # 内容完全一致
        assert tier1.content == tier2.content == tier3.content
        assert tier1.version == tier2.version == tier3.version

    def test_token_estimates_accumulate(self):
        """三层 token 估算可以正确累加."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")

        stable = builder.build_stable_tier(
            agent_role="You are a risk analyst with expertise in derivatives.",
            tools_index=[{"name": "check_greeks", "desc": "Check Greeks"}],
            behavior_rules=["Always verify delta limits.", "Report breaches immediately."],
        )
        context = builder.build_context_tier(
            skills=[{"name": "risk_analysis", "desc": "Perform risk analysis"}],
            project_rules=["Compliance first.", "Data integrity required."],
            memory_summary={"recent_alerts": ["alert_1", "alert_2"]},
        )
        volatile = builder.build_volatile_tier(
            current_event={"type": "breach", "severity": "high"},
            task={"task_id": "analyze_breach"},
            react_history=[{"step": 1, "action": "check_data"}],
        )

        total_tokens = (
            builder.estimate_tier_tokens(stable)
            + builder.estimate_tier_tokens(context)
            + builder.estimate_tier_tokens(volatile)
        )
        assert total_tokens > 0
        # 每层都有 token
        assert stable.token_estimate > 0
        assert context.token_estimate > 0
        assert volatile.token_estimate > 0
        # 总和等于各层之和
        assert total_tokens == stable.token_estimate + context.token_estimate + volatile.token_estimate
