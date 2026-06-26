"""Skill 治理端到端集成测试.

测试从 Skill 积累到治理清理再到注入控制的完整流程.
使用真实 SkillStore (内存存储) 和 SkillInjector + SkillGovernor, 不依赖外部 LLM.

测试场景:
1. 大量 Skill 积累后注入 → 只返回高质量且不超限额的
2. 低质量 Skill 清理 → 归档后不再参与注入
3. prompt token 统计不超预算
"""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def _make_skill(**kwargs) -> dict:
    """构造测试用 Skill dict."""
    base = {
        "name": "交易台风险排查",
        "tags": ["risk", "trading"],
        "applicable_conditions": ["延迟异常", "告警触发"],
        "steps": [
            {"description": "查询持仓数据", "expected_outcome": "获取当前持仓"},
            {"description": "核对限额", "expected_outcome": "确认是否超限"},
        ],
        "failure_boundary": "禁止伪造数据",
    }
    base.update(kwargs)
    return base


def _make_task(**kwargs) -> dict:
    """构造测试用 task."""
    base = {
        "task_id": "task-governance-001",
        "intent": "query_positions",
        "content": {
            "category": "risk",
            "description": "查询交易台持仓并核对限额",
        },
    }
    base.update(kwargs)
    return base


# ==================== 1. 大量 Skill 积累后注入 → 只返回高质量且不超限额 ====================


@pytest.mark.asyncio
async def test_large_skill_pool_injection_quality_filter():
    """大量 Skill 积累后注入, 只返回高质量且不超限额的."""
    from riskmonitor_multiagent.skills import (
        SkillGovernanceConfig,
        SkillGovernor,
        SkillInjector,
        SkillStore,
    )

    store = SkillStore()

    # 创建 15 个 Skill: 5 个高置信度, 5 个中置信度, 5 个低置信度
    for i in range(5):
        await store.create(
            _make_skill(
                name=f"高置信度技能{i}",
                confidence=0.9,
                tags=["risk"],
            )
        )
    for i in range(5):
        await store.create(
            _make_skill(
                name=f"中置信度技能{i}",
                confidence=0.5,
                tags=["risk"],
            )
        )
    for i in range(5):
        await store.create(
            _make_skill(
                name=f"低置信度技能{i}",
                confidence=0.1,
                tags=["risk"],
            )
        )

    # 配置 governor: 最多 3 个, 最低置信度 0.3
    config = SkillGovernanceConfig(
        max_skills_per_category=3,
        min_confidence_for_injection=0.3,
        max_injection_token_budget=10000,
    )
    governor = SkillGovernor(store, config)
    injector = SkillInjector(
        store,
        min_confidence=0.0,  # store 级别不过滤, 交给 governor
        max_skills=15,
        governor=governor,
    )

    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
    )

    # 验证注入结果
    assert result["skill_enabled"] is True
    assert result["skill_count"] <= 3

    # 验证注入的都是高置信度 Skill
    for skill in result["skills"]:
        assert skill["confidence"] >= 0.3

    # 低置信度技能不应出现
    names = [s["name"] for s in result["skills"]]
    for name in names:
        assert "低置信度" not in name


# ==================== 2. 低质量 Skill 清理 → 归档后不再参与注入 ====================


@pytest.mark.asyncio
async def test_cleanup_archives_low_quality_and_excludes_from_injection():
    """低质量 Skill 清理后被归档, 不再参与注入."""
    from riskmonitor_multiagent.skills import (
        SkillGovernanceConfig,
        SkillGovernor,
        SkillInjector,
        SkillStore,
    )

    store = SkillStore()

    # 创建高质量和低质量 Skill
    await store.create(
        _make_skill(name="高质量技能", confidence=0.9, tags=["risk"])
    )
    await store.create(
        _make_skill(name="低质量技能", confidence=0.1, tags=["risk"])
    )

    # 清理前: 两个都参与注入
    injector_no_governor = SkillInjector(store, min_confidence=0.0, max_skills=10)
    result_before = await injector_no_governor.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
    )
    assert result_before["skill_count"] == 2

    # 执行清理
    config = SkillGovernanceConfig(auto_archive_threshold=0.15)
    governor = SkillGovernor(store, config)
    cleanup_result = await governor.cleanup_stale_skills()

    assert cleanup_result["archived_count"] == 1
    assert cleanup_result["total_scanned"] == 2

    # 清理后: 低质量技能被归档, 不再参与注入
    result_after = await injector_no_governor.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
    )
    assert result_after["skill_count"] == 1
    assert result_after["skills"][0]["name"] == "高质量技能"


# ==================== 3. prompt token 统计不超预算 ====================


@pytest.mark.asyncio
async def test_token_budget_limits_prompt_size():
    """Skill 注入不超过 token 预算."""
    from riskmonitor_multiagent.skills import (
        SkillGovernanceConfig,
        SkillGovernor,
        SkillInjector,
        SkillStore,
    )

    store = SkillStore()

    # 创建 5 个相同内容的 Skill (内容匹配 query, 单个约 28 token)
    for i in range(5):
        await store.create(
            _make_skill(
                name=f"查询持仓排查{i}",
                confidence=0.9,
            )
        )

    # 设置很小的 token 预算 (仅容纳 1 个 Skill)
    config = SkillGovernanceConfig(
        max_skills_per_category=10,
        min_confidence_for_injection=0.3,
        max_injection_token_budget=50,
    )
    governor = SkillGovernor(store, config)
    injector = SkillInjector(
        store,
        min_confidence=0.0,
        max_skills=10,
        governor=governor,
    )

    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
    )

    # 验证注入的 Skill 数量受 token 预算限制 (只有 1 个)
    assert result["skill_count"] >= 1
    assert result["skill_count"] < 5

    # 计算实际 token 开销, 验证不超预算
    injected_skills = result["skills"]
    actual_tokens = governor.estimate_skills_token_cost(injected_skills)
    assert actual_tokens <= config.max_injection_token_budget

    # 验证如果多加一个 Skill 就会超预算
    all_active = await store.list_all(status="active")
    injected_ids = {s["skill_id"] for s in injected_skills}
    not_injected = [s for s in all_active if s["skill_id"] not in injected_ids]
    if not_injected:
        next_skill_tokens = governor.estimate_skills_token_cost([not_injected[0]])
        assert actual_tokens + next_skill_tokens > config.max_injection_token_budget


# ==================== 4. 治理报告反映清理后状态 ====================


@pytest.mark.asyncio
async def test_governance_report_after_cleanup():
    """治理报告反映清理后的状态."""
    from riskmonitor_multiagent.skills import (
        SkillGovernanceConfig,
        SkillGovernor,
        SkillStore,
    )

    store = SkillStore()

    # 创建混合质量的 Skill
    await store.create(_make_skill(name="s1", confidence=0.9))
    await store.create(_make_skill(name="s2", confidence=0.5))
    await store.create(_make_skill(name="s3", confidence=0.1))

    governor = SkillGovernor(store, SkillGovernanceConfig(auto_archive_threshold=0.15))

    # 清理前报告
    report_before = await governor.get_governance_report()
    assert report_before["total_skills"] == 3
    assert report_before["active_skills"] == 3
    assert report_before["archived_skills"] == 0
    assert report_before["cleanup_needed"] is True

    # 执行清理
    await governor.cleanup_stale_skills()

    # 清理后报告
    report_after = await governor.get_governance_report()
    assert report_after["total_skills"] == 3  # 总数不变, 只是状态改变
    assert report_after["active_skills"] == 2  # s1 + s2
    assert report_after["archived_skills"] == 1  # s3
    # cleanup_needed 应该为 False (低置信度 Skill 已归档)
    assert report_after["cleanup_needed"] is False


# ==================== 5. SkillInjector 无 governor 时行为不变 ====================


@pytest.mark.asyncio
async def test_injector_without_governor_unchanged_behavior():
    """无 governor 时 SkillInjector 行为与原来一致 (不回归)."""
    from riskmonitor_multiagent.skills import SkillInjector, SkillStore

    store = SkillStore()
    await store.create(_make_skill(name="正常技能", confidence=0.9))
    await store.create(_make_skill(name="低置信度", confidence=0.1))

    # 无 governor
    injector = SkillInjector(store, min_confidence=0.3, max_skills=5)
    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
    )

    # 行为与原来一致: SkillStore.search 已过滤 confidence < min_confidence
    assert result["skill_enabled"] is True
    assert result["skill_count"] == 1
    assert result["skills"][0]["name"] == "正常技能"


# ==================== 6. governor 异常不影响主流程 ====================


@pytest.mark.asyncio
async def test_governor_exception_does_not_break_injection():
    """governor 异常时 SkillInjector 仍返回安全结构."""
    from unittest.mock import AsyncMock, patch

    from riskmonitor_multiagent.skills import (
        SkillGovernanceConfig,
        SkillGovernor,
        SkillInjector,
        SkillStore,
    )

    store = SkillStore()
    await store.create(_make_skill(confidence=0.9))

    governor = SkillGovernor(store, SkillGovernanceConfig())
    injector = SkillInjector(
        store,
        min_confidence=0.3,
        max_skills=5,
        governor=governor,
    )

    # mock governor.enforce_injection_limits 抛异常
    with patch.object(
        governor,
        "enforce_injection_limits",
        new_callable=AsyncMock,
        side_effect=RuntimeError("governor error"),
    ):
        result = await injector.retrieve_applicable_skills(
            task=_make_task(),
            skill_enabled=True,
        )

    # 异常被捕获, 仍返回正常的注入结果
    assert result["skill_enabled"] is True
    assert result["skill_count"] >= 1  # 治理前的结果
