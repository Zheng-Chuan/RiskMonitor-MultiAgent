"""TieredPromptBuilder 单元测试.

测试场景:
1. build_stable_tier → 内容正确, cacheable=True
2. build_context_tier → 内容正确, 版本为日期戳
3. build_volatile_tier → 内容正确, cacheable=False
4. assemble_messages → 三层合并为 messages 列表
5. get_cache_key → stable_version + context_date
6. stable_tier 在连续调用中保持一致
7. context_tier 日内多次调用共享同一版本
8. volatile_tier 每次调用版本不同
9. token 估算合理
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.prompts.tiered_prompt_builder import (
    PromptTier,
    TieredPromptBuilder,
)


# ---------------------------------------------------------------------------
# 1. build_stable_tier 测试
# ---------------------------------------------------------------------------


class TestBuildStableTier:
    """测试 stable_tier 构建."""

    def test_content_contains_agent_role(self):
        """stable_tier 内容包含 Agent 角色定义."""
        builder = TieredPromptBuilder(stable_version="v1")
        tier = builder.build_stable_tier(
            agent_role="You are a risk analyst.",
            tools_index=[{"name": "check_alerts", "desc": "Check alerts"}],
            behavior_rules=["Always verify data sources.", "Report immediately."],
        )
        assert "risk analyst" in tier.content
        assert "Agent Role" in tier.content

    def test_content_contains_tools_index(self):
        """stable_tier 内容包含工具索引."""
        builder = TieredPromptBuilder(stable_version="v1")
        tools = [{"name": "tool_a", "desc": "Does A"}, {"name": "tool_b", "desc": "Does B"}]
        tier = builder.build_stable_tier(
            agent_role="Agent",
            tools_index=tools,
            behavior_rules=[],
        )
        assert "tool_a" in tier.content
        assert "tool_b" in tier.content
        assert "Tools Index" in tier.content

    def test_content_contains_behavior_rules(self):
        """stable_tier 内容包含行为规则."""
        builder = TieredPromptBuilder(stable_version="v1")
        tier = builder.build_stable_tier(
            agent_role="Agent",
            tools_index=[],
            behavior_rules=["Rule 1", "Rule 2"],
        )
        assert "Rule 1" in tier.content
        assert "Rule 2" in tier.content
        assert "Behavior Rules" in tier.content

    def test_cacheable_is_true(self):
        """stable_tier cacheable=True."""
        builder = TieredPromptBuilder(stable_version="v1")
        tier = builder.build_stable_tier(
            agent_role="Agent",
            tools_index=[],
            behavior_rules=[],
        )
        assert tier.cacheable is True

    def test_version_matches_stable_version(self):
        """stable_tier 版本号匹配 stable_version."""
        builder = TieredPromptBuilder(stable_version="v2.1")
        tier = builder.build_stable_tier(
            agent_role="Agent",
            tools_index=[],
            behavior_rules=[],
        )
        assert tier.version == "v2.1"

    def test_tier_name_is_stable(self):
        """stable_tier tier_name='stable'."""
        builder = TieredPromptBuilder(stable_version="v1")
        tier = builder.build_stable_tier(
            agent_role="Agent",
            tools_index=[],
            behavior_rules=[],
        )
        assert tier.tier_name == "stable"

    def test_token_estimate_positive(self):
        """stable_tier token_estimate > 0."""
        builder = TieredPromptBuilder(stable_version="v1")
        tier = builder.build_stable_tier(
            agent_role="You are a helpful assistant with many capabilities.",
            tools_index=[{"name": "search", "desc": "Search the web"}],
            behavior_rules=["Be polite.", "Be accurate."],
        )
        assert tier.token_estimate > 0


# ---------------------------------------------------------------------------
# 2. build_context_tier 测试
# ---------------------------------------------------------------------------


class TestBuildContextTier:
    """测试 context_tier 构建."""

    def test_content_contains_skills(self):
        """context_tier 内容包含 Skills."""
        builder = TieredPromptBuilder(context_date="2025-01-15")
        tier = builder.build_context_tier(
            skills=[{"name": "skill_a", "desc": "Skill A"}],
            project_rules=[],
        )
        assert "skill_a" in tier.content
        assert "Skills" in tier.content

    def test_content_contains_project_rules(self):
        """context_tier 内容包含项目规则."""
        builder = TieredPromptBuilder(context_date="2025-01-15")
        tier = builder.build_context_tier(
            skills=[],
            project_rules=["Rule A", "Rule B"],
        )
        assert "Rule A" in tier.content
        assert "Rule B" in tier.content
        assert "Project Rules" in tier.content

    def test_content_contains_memory_summary(self):
        """context_tier 内容包含记忆摘要."""
        builder = TieredPromptBuilder(context_date="2025-01-15")
        tier = builder.build_context_tier(
            skills=[],
            project_rules=[],
            memory_summary={"key_facts": ["fact1", "fact2"]},
        )
        assert "Memory Summary" in tier.content
        assert "fact1" in tier.content

    def test_content_without_memory_summary(self):
        """memory_summary 为 None 时不包含 Memory Summary 段."""
        builder = TieredPromptBuilder(context_date="2025-01-15")
        tier = builder.build_context_tier(
            skills=[],
            project_rules=[],
            memory_summary=None,
        )
        assert "Memory Summary" not in tier.content

    def test_version_is_context_date(self):
        """context_tier 版本号为 context_date."""
        builder = TieredPromptBuilder(context_date="2025-06-26")
        tier = builder.build_context_tier(
            skills=[],
            project_rules=[],
        )
        assert tier.version == "2025-06-26"

    def test_cacheable_is_true(self):
        """context_tier cacheable=True."""
        builder = TieredPromptBuilder(context_date="2025-01-15")
        tier = builder.build_context_tier(
            skills=[],
            project_rules=[],
        )
        assert tier.cacheable is True

    def test_tier_name_is_context(self):
        """context_tier tier_name='context'."""
        builder = TieredPromptBuilder(context_date="2025-01-15")
        tier = builder.build_context_tier(
            skills=[],
            project_rules=[],
        )
        assert tier.tier_name == "context"


# ---------------------------------------------------------------------------
# 3. build_volatile_tier 测试
# ---------------------------------------------------------------------------


class TestBuildVolatileTier:
    """测试 volatile_tier 构建."""

    def test_content_contains_current_event(self):
        """volatile_tier 内容包含当前事件."""
        builder = TieredPromptBuilder()
        tier = builder.build_volatile_tier(
            current_event={"type": "alert", "severity": "high"},
            task={"task_id": "t1"},
        )
        assert "alert" in tier.content
        assert "Current Event" in tier.content

    def test_content_contains_task(self):
        """volatile_tier 内容包含当前任务."""
        builder = TieredPromptBuilder()
        tier = builder.build_volatile_tier(
            current_event=None,
            task={"task_id": "t123", "action": "analyze"},
        )
        assert "t123" in tier.content
        assert "Task" in tier.content

    def test_content_contains_react_history(self):
        """volatile_tier 内容包含 ReAct 历史."""
        builder = TieredPromptBuilder()
        tier = builder.build_volatile_tier(
            current_event=None,
            task={"task_id": "t1"},
            react_history=[{"step": 1, "thought": "thinking"}],
        )
        assert "ReAct History" in tier.content
        assert "thinking" in tier.content

    def test_content_without_react_history(self):
        """react_history 为 None 时显示空列表."""
        builder = TieredPromptBuilder()
        tier = builder.build_volatile_tier(
            current_event=None,
            task={"task_id": "t1"},
            react_history=None,
        )
        assert "ReAct History" in tier.content

    def test_current_event_none(self):
        """current_event 为 None 时显示 None."""
        builder = TieredPromptBuilder()
        tier = builder.build_volatile_tier(
            current_event=None,
            task={"task_id": "t1"},
        )
        assert "Current Event" in tier.content
        assert "None" in tier.content

    def test_cacheable_is_false(self):
        """volatile_tier cacheable=False."""
        builder = TieredPromptBuilder()
        tier = builder.build_volatile_tier(
            current_event=None,
            task={"task_id": "t1"},
        )
        assert tier.cacheable is False

    def test_tier_name_is_volatile(self):
        """volatile_tier tier_name='volatile'."""
        builder = TieredPromptBuilder()
        tier = builder.build_volatile_tier(
            current_event=None,
            task={"task_id": "t1"},
        )
        assert tier.tier_name == "volatile"


# ---------------------------------------------------------------------------
# 4. assemble_messages 测试
# ---------------------------------------------------------------------------


class TestAssembleMessages:
    """测试 assemble_messages."""

    def test_returns_three_messages(self):
        """组装后返回 3 条 messages."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-01-15")
        stable = builder.build_stable_tier(
            agent_role="Agent", tools_index=[], behavior_rules=[],
        )
        context = builder.build_context_tier(
            skills=[], project_rules=[],
        )
        volatile = builder.build_volatile_tier(
            current_event=None, task={"id": "1"},
        )
        messages = builder.assemble_messages(stable, context, volatile)
        assert len(messages) == 3

    def test_all_messages_are_system_role(self):
        """所有 messages 的 role 都是 system."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-01-15")
        stable = builder.build_stable_tier(
            agent_role="Agent", tools_index=[], behavior_rules=[],
        )
        context = builder.build_context_tier(
            skills=[], project_rules=[],
        )
        volatile = builder.build_volatile_tier(
            current_event=None, task={"id": "1"},
        )
        messages = builder.assemble_messages(stable, context, volatile)
        for msg in messages:
            assert msg["role"] == "system"

    def test_order_stable_context_volatile(self):
        """messages 顺序: stable → context → volatile."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-01-15")
        stable = builder.build_stable_tier(
            agent_role="STABLE_ROLE_MARKER", tools_index=[], behavior_rules=[],
        )
        context = builder.build_context_tier(
            skills=[], project_rules=["CONTEXT_RULE_MARKER"],
        )
        volatile = builder.build_volatile_tier(
            current_event=None, task={"volatile_marker": True},
        )
        messages = builder.assemble_messages(stable, context, volatile)
        assert "STABLE_ROLE_MARKER" in messages[0]["content"]
        assert "CONTEXT_RULE_MARKER" in messages[1]["content"]
        assert "volatile_marker" in messages[2]["content"]

    def test_messages_contain_tier_content(self):
        """messages 的 content 包含对应层级的完整内容."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-01-15")
        stable = builder.build_stable_tier(
            agent_role="Agent", tools_index=[], behavior_rules=[],
        )
        context = builder.build_context_tier(
            skills=[], project_rules=[],
        )
        volatile = builder.build_volatile_tier(
            current_event=None, task={"id": "1"},
        )
        messages = builder.assemble_messages(stable, context, volatile)
        assert messages[0]["content"] == stable.content
        assert messages[1]["content"] == context.content
        assert messages[2]["content"] == volatile.content


# ---------------------------------------------------------------------------
# 5. get_cache_key 测试
# ---------------------------------------------------------------------------


class TestGetCacheKey:
    """测试 get_cache_key."""

    def test_cache_key_format(self):
        """缓存键格式 = stable_version + context_date."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")
        stable = builder.build_stable_tier(
            agent_role="Agent", tools_index=[], behavior_rules=[],
        )
        context = builder.build_context_tier(
            skills=[], project_rules=[],
        )
        key = builder.get_cache_key(stable, context)
        assert key == "v1:2025-06-26"

    def test_cache_key_uses_tier_versions(self):
        """缓存键使用 tier 的 version 属性, 而非 builder 属性."""
        builder = TieredPromptBuilder(stable_version="v3", context_date="2025-03-01")
        # 手动构造 tier, 使用不同的 version
        stable = PromptTier(
            tier_name="stable", content="c", version="v99", token_estimate=1, cacheable=True,
        )
        context = PromptTier(
            tier_name="context", content="c", version="2025-12-31", token_estimate=1, cacheable=True,
        )
        key = builder.get_cache_key(stable, context)
        assert key == "v99:2025-12-31"

    def test_volatile_not_in_cache_key(self):
        """volatile_tier 不参与缓存键."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-01-15")
        stable = builder.build_stable_tier(
            agent_role="Agent", tools_index=[], behavior_rules=[],
        )
        context = builder.build_context_tier(
            skills=[], project_rules=[],
        )
        volatile1 = builder.build_volatile_tier(
            current_event=None, task={"id": "1"},
        )
        volatile2 = builder.build_volatile_tier(
            current_event=None, task={"id": "2"},
        )
        key1 = builder.get_cache_key(stable, context)
        key2 = builder.get_cache_key(stable, context)
        # 缓存键不包含 volatile 信息, 两次调用结果一致
        assert key1 == key2


# ---------------------------------------------------------------------------
# 6. stable_tier 连续调用一致性
# ---------------------------------------------------------------------------


class TestStableTierConsistency:
    """测试 stable_tier 在连续调用中保持一致."""

    def test_consecutive_calls_same_content(self):
        """相同输入, stable_tier 内容完全一致."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-01-15")
        tier1 = builder.build_stable_tier(
            agent_role="You are a risk analyst.",
            tools_index=[{"name": "tool1", "desc": "Tool 1"}],
            behavior_rules=["Rule A", "Rule B"],
        )
        tier2 = builder.build_stable_tier(
            agent_role="You are a risk analyst.",
            tools_index=[{"name": "tool1", "desc": "Tool 1"}],
            behavior_rules=["Rule A", "Rule B"],
        )
        assert tier1.content == tier2.content
        assert tier1.version == tier2.version

    def test_consecutive_calls_same_version(self):
        """相同输入, stable_tier 版本一致."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-01-15")
        tier1 = builder.build_stable_tier(
            agent_role="Agent", tools_index=[], behavior_rules=[],
        )
        tier2 = builder.build_stable_tier(
            agent_role="Agent", tools_index=[], behavior_rules=[],
        )
        assert tier1.version == tier2.version


# ---------------------------------------------------------------------------
# 7. context_tier 日内多次调用共享同一版本
# ---------------------------------------------------------------------------


class TestContextTierDailyVersion:
    """测试 context_tier 日内多次调用共享同一版本."""

    def test_same_day_same_version(self):
        """同一天构建的 context_tier 版本一致."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")
        tier1 = builder.build_context_tier(
            skills=[{"name": "s1"}], project_rules=["r1"],
        )
        tier2 = builder.build_context_tier(
            skills=[{"name": "s1"}], project_rules=["r1"],
        )
        assert tier1.version == tier2.version

    def test_same_day_same_version_different_skills(self):
        """同一天不同 skills, 版本仍一致 (版本是日期戳, 非内容哈希)."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")
        tier1 = builder.build_context_tier(
            skills=[{"name": "s1"}], project_rules=["r1"],
        )
        tier2 = builder.build_context_tier(
            skills=[{"name": "s2"}], project_rules=["r2"],
        )
        assert tier1.version == tier2.version

    def test_different_days_different_versions(self):
        """不同日期的 builder 生成不同版本."""
        builder1 = TieredPromptBuilder(stable_version="v1", context_date="2025-06-26")
        builder2 = TieredPromptBuilder(stable_version="v1", context_date="2025-06-27")
        tier1 = builder1.build_context_tier(skills=[], project_rules=[])
        tier2 = builder2.build_context_tier(skills=[], project_rules=[])
        assert tier1.version != tier2.version


# ---------------------------------------------------------------------------
# 8. volatile_tier 每次调用版本不同
# ---------------------------------------------------------------------------


class TestVolatileTierVersionUnique:
    """测试 volatile_tier 每次调用版本不同."""

    def test_consecutive_calls_different_versions(self):
        """连续调用 volatile_tier 版本不同."""
        builder = TieredPromptBuilder(stable_version="v1", context_date="2025-01-15")
        tier1 = builder.build_volatile_tier(
            current_event=None, task={"id": "1"},
        )
        # 确保时间戳不同 (至少 1ms)
        import time
        time.sleep(0.002)
        tier2 = builder.build_volatile_tier(
            current_event=None, task={"id": "1"},
        )
        assert tier1.version != tier2.version

    def test_version_is_numeric_timestamp(self):
        """volatile_tier 版本号是数字时间戳."""
        builder = TieredPromptBuilder()
        tier = builder.build_volatile_tier(
            current_event=None, task={"id": "1"},
        )
        assert tier.version.isdigit()
        # 应该是一个合理的时间戳 (毫秒级)
        ts = int(tier.version)
        assert ts > 1_000_000_000  # 大于 2001 年的时间戳


# ---------------------------------------------------------------------------
# 9. token 估算
# ---------------------------------------------------------------------------


class TestTokenEstimation:
    """测试 token 估算."""

    def test_empty_content_minimal_tokens(self):
        """空内容 token 估算为最小值 (仅 overhead)."""
        builder = TieredPromptBuilder()
        tier = PromptTier(
            tier_name="test", content="", version="v1", token_estimate=0, cacheable=True,
        )
        tokens = builder.estimate_tier_tokens(tier)
        # 空内容: 仅 _PER_MESSAGE_OVERHEAD = 4
        assert tokens == 4

    def test_chinese_content(self):
        """中文内容 token 估算合理."""
        builder = TieredPromptBuilder()
        tier = PromptTier(
            tier_name="test",
            content="你好世界你好世界",
            version="v1",
            token_estimate=0,
            cacheable=True,
        )
        tokens = builder.estimate_tier_tokens(tier)
        # 8 个中文字 / 1.5 = 5.33 + 4 overhead = 9
        assert tokens > 0
        assert tokens >= 9

    def test_english_content(self):
        """英文内容 token 估算合理."""
        builder = TieredPromptBuilder()
        tier = PromptTier(
            tier_name="test",
            content="Hello world test",
            version="v1",
            token_estimate=0,
            cacheable=True,
        )
        tokens = builder.estimate_tier_tokens(tier)
        # 16 chars / 4 = 4 + 4 overhead = 8
        assert tokens > 0
        assert tokens >= 8

    def test_longer_content_more_tokens(self):
        """更长内容 token 数更多."""
        builder = TieredPromptBuilder()
        short_tier = PromptTier(
            tier_name="test", content="short", version="v1", token_estimate=0, cacheable=True,
        )
        long_tier = PromptTier(
            tier_name="test", content="x" * 1000, version="v1", token_estimate=0, cacheable=True,
        )
        assert builder.estimate_tier_tokens(long_tier) > builder.estimate_tier_tokens(short_tier)

    def test_token_estimate_in_tier(self):
        """build 方法返回的 tier 中 token_estimate 与 estimate_tier_tokens 一致."""
        builder = TieredPromptBuilder(stable_version="v1")
        tier = builder.build_stable_tier(
            agent_role="You are a risk analyst.",
            tools_index=[{"name": "tool1", "desc": "Tool 1"}],
            behavior_rules=["Rule A"],
        )
        assert tier.token_estimate == builder.estimate_tier_tokens(tier)


# ---------------------------------------------------------------------------
# tiktoken 精确 token 计算
# ---------------------------------------------------------------------------


class TestPreciseTokenCount:
    """测试 tiktoken 精确 token 计算."""

    def test_count_tokens_precise_returns_positive(self):
        """精确计算返回正整数."""
        tokens = TieredPromptBuilder.count_tokens_precise("Hello world, this is a test.")
        assert tokens > 0

    def test_count_tokens_precise_empty_string(self):
        """空字符串返回 0."""
        tokens = TieredPromptBuilder.count_tokens_precise("")
        assert tokens == 0

    def test_count_tokens_precise_chinese(self):
        """中文字符也能精确计算."""
        tokens = TieredPromptBuilder.count_tokens_precise("你好世界，这是风控测试。")
        assert tokens > 0

    def test_count_tier_tokens_precise(self):
        """count_tier_tokens_precise 对 PromptTier 对象精确计算."""
        builder = TieredPromptBuilder()
        tier = PromptTier(
            tier_name="test",
            content="This is a test prompt with some content for token counting.",
            version="v1",
            token_estimate=0,
            cacheable=True,
        )
        precise = builder.count_tier_tokens_precise(tier)
        heuristic = builder.estimate_tier_tokens(tier)
        # 精确值与启发式值应该在同一数量级
        assert precise > 0
        assert heuristic > 0
        # 偏差不应超过 10 倍
        assert precise < heuristic * 10
        assert heuristic < precise * 10

    def test_precise_vs_heuristic_order_of_magnitude(self):
        """精确计算与启发式在同一数量级."""
        text = "You are a risk analyst. Analyze the following breach and provide recommendations."
        precise = TieredPromptBuilder.count_tokens_precise(text)
        heuristic = TieredPromptBuilder.estimate_tier_tokens_text(text)
        # 两者应在同一数量级 (启发式可能偏差不大)
        ratio = max(precise, heuristic) / max(min(precise, heuristic), 1)
        assert ratio < 5, f"precise={precise}, heuristic={heuristic}, ratio={ratio}"
