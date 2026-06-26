"""SkillGovernor 单测."""

import sys
import time
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


# ==================== 测试数据构造 ====================


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


def _make_injection_skill(**kwargs) -> dict:
    """构造注入格式的 Skill dict (模拟 SkillInjector._build_injection_item)."""
    base = {
        "skill_id": "skill_test001",
        "name": "交易台风险排查",
        "applicable_conditions": ["延迟异常", "告警触发"],
        "steps": [
            {"description": "查询持仓数据", "expected_outcome": "获取当前持仓"},
        ],
        "failure_boundary": "禁止伪造数据",
        "confidence": 0.8,
    }
    base.update(kwargs)
    return base


# ==================== 1. enforce_injection_limits: 过滤低置信度 Skill ====================


@pytest.mark.asyncio
async def test_enforce_injection_limits_filters_low_confidence():
    """confidence < min_confidence_for_injection 的 Skill 被过滤."""
    from riskmonitor_multiagent.skills import SkillGovernanceConfig, SkillGovernor, SkillStore

    store = SkillStore()
    config = SkillGovernanceConfig(min_confidence_for_injection=0.3)
    governor = SkillGovernor(store, config)

    skills = [
        _make_injection_skill(skill_id="s1", name="低置信度", confidence=0.1),
        _make_injection_skill(skill_id="s2", name="中置信度", confidence=0.5),
        _make_injection_skill(skill_id="s3", name="高置信度", confidence=0.8),
    ]

    result = await governor.enforce_injection_limits(skills)

    names = [s["name"] for s in result]
    assert "低置信度" not in names
    assert "中置信度" in names
    assert "高置信度" in names
    assert len(result) == 2


# ==================== 2. enforce_injection_limits: 过滤非 active Skill ====================


@pytest.mark.asyncio
async def test_enforce_injection_limits_filters_non_active():
    """status != 'active' 的 Skill 被过滤."""
    from riskmonitor_multiagent.skills import SkillGovernanceConfig, SkillGovernor, SkillStore

    store = SkillStore()
    config = SkillGovernanceConfig(min_confidence_for_injection=0.0)
    governor = SkillGovernor(store, config)

    skills = [
        _make_injection_skill(skill_id="s1", name="活跃", confidence=0.8, status="active"),
        _make_injection_skill(skill_id="s2", name="废弃", confidence=0.8, status="deprecated"),
        _make_injection_skill(skill_id="s3", name="归档", confidence=0.8, status="archived"),
    ]

    result = await governor.enforce_injection_limits(skills)

    names = [s["name"] for s in result]
    assert "活跃" in names
    assert "废弃" not in names
    assert "归档" not in names
    assert len(result) == 1


# ==================== 3. enforce_injection_limits: 按 confidence 降序排序 ====================


@pytest.mark.asyncio
async def test_enforce_injection_limits_sorts_by_confidence_desc():
    """按 confidence 降序排序."""
    from riskmonitor_multiagent.skills import SkillGovernanceConfig, SkillGovernor, SkillStore

    store = SkillStore()
    config = SkillGovernanceConfig(
        min_confidence_for_injection=0.0,
        max_skills_per_category=10,
        max_injection_token_budget=10000,
    )
    governor = SkillGovernor(store, config)

    skills = [
        _make_injection_skill(skill_id="s1", name="中", confidence=0.5),
        _make_injection_skill(skill_id="s2", name="高", confidence=0.9),
        _make_injection_skill(skill_id="s3", name="低", confidence=0.3),
    ]

    result = await governor.enforce_injection_limits(skills)

    assert len(result) == 3
    confidences = [s["confidence"] for s in result]
    assert confidences == sorted(confidences, reverse=True)
    assert result[0]["name"] == "高"
    assert result[1]["name"] == "中"
    assert result[2]["name"] == "低"


# ==================== 4. enforce_injection_limits: 限制数量不超过 max_skills_per_category ====================


@pytest.mark.asyncio
async def test_enforce_injection_limits_limits_count():
    """限制数量不超过 max_skills_per_category."""
    from riskmonitor_multiagent.skills import SkillGovernanceConfig, SkillGovernor, SkillStore

    store = SkillStore()
    config = SkillGovernanceConfig(
        min_confidence_for_injection=0.0,
        max_skills_per_category=2,
        max_injection_token_budget=10000,
    )
    governor = SkillGovernor(store, config)

    skills = [
        _make_injection_skill(skill_id="s1", name="A", confidence=0.9),
        _make_injection_skill(skill_id="s2", name="B", confidence=0.8),
        _make_injection_skill(skill_id="s3", name="C", confidence=0.7),
        _make_injection_skill(skill_id="s4", name="D", confidence=0.6),
        _make_injection_skill(skill_id="s5", name="E", confidence=0.5),
    ]

    result = await governor.enforce_injection_limits(skills)

    assert len(result) <= 2
    # 应该保留置信度最高的两个
    names = [s["name"] for s in result]
    assert "A" in names
    assert "B" in names


# ==================== 5. enforce_injection_limits: token 预算限制截断 ====================


@pytest.mark.asyncio
async def test_enforce_injection_limits_token_budget_truncation():
    """token 预算超限时截断."""
    from riskmonitor_multiagent.skills import SkillGovernanceConfig, SkillGovernor, SkillStore

    store = SkillStore()
    # 设置很小的 token 预算
    config = SkillGovernanceConfig(
        min_confidence_for_injection=0.0,
        max_skills_per_category=10,
        max_injection_token_budget=10,
    )
    governor = SkillGovernor(store, config)

    # 创建有较长文本的 Skill
    skills = [
        _make_injection_skill(
            skill_id="s1",
            name="技能A",
            confidence=0.9,
            steps=[
                {"description": "这是一个非常长的步骤描述" * 5, "expected_outcome": "结果"},
            ],
        ),
        _make_injection_skill(
            skill_id="s2",
            name="技能B",
            confidence=0.8,
            steps=[
                {"description": "另一个非常长的步骤描述" * 5, "expected_outcome": "结果"},
            ],
        ),
    ]

    result = await governor.enforce_injection_limits(skills)

    # 由于 token 预算很小, 只能放入第一个 Skill
    assert len(result) <= 1
    # 第一个 Skill (更高置信度) 应该被保留
    if result:
        assert result[0]["name"] == "技能A"


# ==================== 6. cleanup_stale_skills: 过期 Skill 归档 ====================


@pytest.mark.asyncio
async def test_cleanup_stale_skills_archives_expired():
    """过期且低置信度的 Skill 被归档."""
    from riskmonitor_multiagent.skills import SkillGovernanceConfig, SkillGovernor, SkillStore

    store = SkillStore()
    # 100 天前的时间戳 (毫秒)
    old_time = int((time.time() - 100 * 24 * 60 * 60) * 1000)

    await store.create(
        _make_skill(
            name="过期低置信度",
            confidence=0.25,
            created_at=old_time,
        )
    )

    config = SkillGovernanceConfig(
        max_skill_age_days=90,
        auto_archive_threshold=0.15,
        auto_deprecate_threshold=0.3,
    )
    governor = SkillGovernor(store, config)
    result = await governor.cleanup_stale_skills()

    assert result["archived_count"] >= 1
    assert result["total_scanned"] >= 1

    # 验证 Skill 状态已变为 archived
    all_skills = await store.list_all()
    target = [s for s in all_skills if s["name"] == "过期低置信度"][0]
    assert target["status"] == "archived"


# ==================== 7. cleanup_stale_skills: 低置信度 Skill 归档 ====================


@pytest.mark.asyncio
async def test_cleanup_stale_skills_archives_low_confidence():
    """confidence < auto_archive_threshold 的 Skill 被归档 (无论是否过期)."""
    from riskmonitor_multiagent.skills import SkillGovernanceConfig, SkillGovernor, SkillStore

    store = SkillStore()

    await store.create(
        _make_skill(
            name="极低置信度",
            confidence=0.1,
        )
    )

    config = SkillGovernanceConfig(
        max_skill_age_days=90,
        auto_archive_threshold=0.15,
        auto_deprecate_threshold=0.3,
    )
    governor = SkillGovernor(store, config)
    result = await governor.cleanup_stale_skills()

    assert result["archived_count"] >= 1

    all_skills = await store.list_all()
    target = [s for s in all_skills if s["name"] == "极低置信度"][0]
    assert target["status"] == "archived"


# ==================== 8. cleanup_stale_skills: 返回正确统计 ====================


@pytest.mark.asyncio
async def test_cleanup_stale_skills_returns_correct_stats():
    """cleanup_stale_skills 返回正确的统计信息."""
    from riskmonitor_multiagent.skills import SkillGovernanceConfig, SkillGovernor, SkillStore

    store = SkillStore()
    old_time = int((time.time() - 100 * 24 * 60 * 60) * 1000)

    # 极低置信度 → archived
    await store.create(_make_skill(name="s1", confidence=0.1))
    # 过期 + 低置信度 → archived
    await store.create(
        _make_skill(name="s2", confidence=0.25, created_at=old_time)
    )
    # 过期 + 高置信度 → deprecated
    await store.create(
        _make_skill(name="s3", confidence=0.8, created_at=old_time)
    )
    # 正常 Skill → 不变
    await store.create(_make_skill(name="s4", confidence=0.8))

    config = SkillGovernanceConfig(
        max_skill_age_days=90,
        auto_archive_threshold=0.15,
        auto_deprecate_threshold=0.3,
    )
    governor = SkillGovernor(store, config)
    result = await governor.cleanup_stale_skills()

    assert result["total_scanned"] == 4
    assert result["archived_count"] == 2  # s1 + s2
    assert result["deprecated_count"] == 1  # s3


# ==================== 9. merge_duplicate_skills: 高相似度 Skill 合并 ====================


@pytest.mark.asyncio
async def test_merge_duplicate_skills_merges_high_similarity():
    """高相似度 Skill 被合并 (低置信度被归档)."""
    from riskmonitor_multiagent.skills import SkillGovernanceConfig, SkillGovernor, SkillStore

    store = SkillStore()

    # 创建两个内容完全相同的 Skill (不同置信度)
    common_data = {
        "name": "交易台风险排查",
        "tags": ["risk", "trading"],
        "applicable_conditions": ["延迟异常", "告警触发"],
        "steps": [
            {"description": "查询持仓数据", "expected_outcome": "获取当前持仓"},
            {"description": "核对限额", "expected_outcome": "确认是否超限"},
        ],
        "failure_boundary": "禁止伪造数据",
    }

    await store.create(_make_skill(**common_data, confidence=0.9))
    await store.create(_make_skill(**common_data, confidence=0.6))

    governor = SkillGovernor(store, SkillGovernanceConfig())
    result = await governor.merge_duplicate_skills(similarity_threshold=0.5)

    assert result["merged_count"] >= 1
    assert result["total_pairs_checked"] >= 1

    # 验证保留的是高置信度的
    active_skills = await store.list_all(status="active")
    archived_skills = await store.list_all(status="archived")
    assert len(active_skills) == 1
    assert len(archived_skills) == 1
    assert active_skills[0]["confidence"] == pytest.approx(0.9)


# ==================== 10. merge_duplicate_skills: 低相似度不合并 ====================


@pytest.mark.asyncio
async def test_merge_duplicate_skills_no_merge_low_similarity():
    """低相似度 Skill 不合并."""
    from riskmonitor_multiagent.skills import SkillGovernanceConfig, SkillGovernor, SkillStore

    store = SkillStore()

    # 创建两个完全不同的 Skill
    await store.create(
        _make_skill(
            name="交易台风险排查",
            tags=["risk"],
            applicable_conditions=["延迟异常"],
            steps=[{"description": "查询持仓", "expected_outcome": "获取持仓"}],
            confidence=0.9,
        )
    )
    await store.create(
        _make_skill(
            name="数据库备份恢复",
            tags=["database"],
            applicable_conditions=["备份失败"],
            steps=[{"description": "检查磁盘空间", "expected_outcome": "确认空间"}],
            confidence=0.8,
        )
    )

    governor = SkillGovernor(store, SkillGovernanceConfig())
    result = await governor.merge_duplicate_skills(similarity_threshold=0.9)

    assert result["merged_count"] == 0

    active_skills = await store.list_all(status="active")
    assert len(active_skills) == 2


# ==================== 11. estimate_skills_token_cost: 估算合理 ====================


def test_estimate_skills_token_cost_reasonable():
    """token 估算值合理."""
    from riskmonitor_multiagent.skills import SkillGovernor, SkillStore

    store = SkillStore()
    governor = SkillGovernor(store)

    # 纯中文 Skill
    chinese_skill = _make_injection_skill(
        name="风险排查",
        applicable_conditions=["延迟异常"],
        steps=[{"description": "查询持仓", "expected_outcome": "获取持仓"}],
        failure_boundary="禁止伪造",
    )
    chinese_tokens = governor.estimate_skills_token_cost([chinese_skill])
    # 应该有合理的 token 数 (> 0)
    assert chinese_tokens > 0

    # 纯英文 Skill
    english_skill = _make_injection_skill(
        name="Risk Check",
        applicable_conditions=["latency alert"],
        steps=[{"description": "query positions", "expected_outcome": "get data"}],
        failure_boundary="no fake data",
    )
    english_tokens = governor.estimate_skills_token_cost([english_skill])
    assert english_tokens > 0

    # 多个 Skill 的 token 数应该大于单个
    multi_tokens = governor.estimate_skills_token_cost(
        [chinese_skill, english_skill]
    )
    assert multi_tokens > chinese_tokens
    assert multi_tokens > english_tokens

    # 空 Skill 列表 token 数为 0
    assert governor.estimate_skills_token_cost([]) == 0


# ==================== 12. get_governance_report: 报告结构完整 ====================


@pytest.mark.asyncio
async def test_get_governance_report_structure():
    """get_governance_report 返回完整结构."""
    from riskmonitor_multiagent.skills import SkillGovernanceConfig, SkillGovernor, SkillStore

    store = SkillStore()

    await store.create(_make_skill(name="s1", confidence=0.9, status="active"))
    await store.create(
        _make_skill(name="s2", confidence=0.2, status="deprecated")
    )
    await store.create(
        _make_skill(name="s3", confidence=0.1, status="active")
    )

    governor = SkillGovernor(store, SkillGovernanceConfig())
    report = await governor.get_governance_report()

    # 检查所有字段
    expected_keys = {
        "total_skills",
        "active_skills",
        "deprecated_skills",
        "archived_skills",
        "avg_confidence",
        "total_usage_count",
        "avg_success_rate",
        "by_category",
        "oldest_skill_age_days",
        "cleanup_needed",
    }
    assert expected_keys.issubset(set(report.keys()))

    # 检查具体值
    assert report["total_skills"] == 3
    assert report["active_skills"] == 2
    assert report["deprecated_skills"] == 1
    assert report["archived_skills"] == 0
    assert report["total_usage_count"] == 0  # 新创建的 Skill usage_count=0
    assert isinstance(report["by_category"], dict)
    assert isinstance(report["oldest_skill_age_days"], int)
    assert isinstance(report["cleanup_needed"], bool)
    # s3 confidence=0.1 < auto_archive_threshold=0.15 且未归档, cleanup_needed 应为 True
    assert report["cleanup_needed"] is True


# ==================== 额外: 默认配置测试 ====================


def test_default_config_values():
    """SkillGovernanceConfig 默认值正确."""
    from riskmonitor_multiagent.skills import SkillGovernanceConfig

    config = SkillGovernanceConfig()
    assert config.max_skills_per_category == 10
    assert config.min_confidence_for_injection == 0.3
    assert config.max_skill_age_days == 90
    assert config.max_injection_token_budget == 2000
    assert config.auto_archive_threshold == 0.15
    assert config.auto_deprecate_threshold == 0.3


# ==================== 额外: 自定义配置测试 ====================


@pytest.mark.asyncio
async def test_custom_config_values():
    """自定义配置生效."""
    from riskmonitor_multiagent.skills import SkillGovernanceConfig, SkillGovernor, SkillStore

    store = SkillStore()
    config = SkillGovernanceConfig(
        min_confidence_for_injection=0.6,
        max_skills_per_category=3,
        max_injection_token_budget=5000,
    )
    governor = SkillGovernor(store, config)

    skills = [
        _make_injection_skill(skill_id="s1", name="低", confidence=0.4),
        _make_injection_skill(skill_id="s2", name="高", confidence=0.8),
    ]

    result = await governor.enforce_injection_limits(skills)

    # confidence=0.4 < 0.6 被过滤
    names = [s["name"] for s in result]
    assert "低" not in names
    assert "高" in names


# ==================== 额外: 空列表安全处理 ====================


@pytest.mark.asyncio
async def test_enforce_injection_limits_empty_list():
    """空 Skill 列表安全返回空."""
    from riskmonitor_multiagent.skills import SkillGovernor, SkillStore

    store = SkillStore()
    governor = SkillGovernor(store)

    result = await governor.enforce_injection_limits([])
    assert result == []


# ==================== 额外: cleanup 不影响正常 Skill ====================


@pytest.mark.asyncio
async def test_cleanup_does_not_affect_normal_skills():
    """正常 (未过期 + 高置信度) Skill 不受 cleanup 影响."""
    from riskmonitor_multiagent.skills import SkillGovernanceConfig, SkillGovernor, SkillStore

    store = SkillStore()

    await store.create(_make_skill(name="正常", confidence=0.9))

    governor = SkillGovernor(store, SkillGovernanceConfig())
    result = await governor.cleanup_stale_skills()

    assert result["archived_count"] == 0
    assert result["deprecated_count"] == 0

    active = await store.list_all(status="active")
    assert len(active) == 1
