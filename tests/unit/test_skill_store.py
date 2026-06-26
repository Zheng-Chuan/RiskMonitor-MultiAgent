"""SkillStore 单测."""

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


# ==================== create + get ====================


@pytest.mark.asyncio
async def test_create_and_get_roundtrip():
    """测试 create + get 往返."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    assert created["skill_id"].startswith("skill_")
    assert created["name"] == "交易台风险排查"
    assert created["status"] == "active"

    fetched = await store.get(created["skill_id"])
    assert fetched is not None
    assert fetched["name"] == "交易台风险排查"
    assert fetched["skill_id"] == created["skill_id"]


@pytest.mark.asyncio
async def test_get_nonexistent_returns_none():
    """测试 get 不存在的 skill_id 返回 None."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    assert await store.get("skill_nonexistent") is None


@pytest.mark.asyncio
async def test_create_invalid_skill_raises():
    """测试 create 非法 skill 抛出异常."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    with pytest.raises(ValueError, match="bad_name"):
        await store.create({"tags": ["x"]})


# ==================== update ====================


@pytest.mark.asyncio
async def test_update_partial_fields():
    """测试 update 部分字段."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    updated = await store.update(
        created["skill_id"], {"confidence": 0.9, "tags": ["risk", "updated"]}
    )
    assert updated["confidence"] == 0.9
    assert "updated" in updated["tags"]
    assert updated["skill_id"] == created["skill_id"]
    assert updated["created_at"] == created["created_at"]
    assert updated["updated_at"] >= created["updated_at"]


@pytest.mark.asyncio
async def test_update_nonexistent_raises():
    """测试 update 不存在的 skill_id 抛出异常."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    with pytest.raises(KeyError):
        await store.update("skill_nonexistent", {"confidence": 0.9})


@pytest.mark.asyncio
async def test_update_invalid_patch_raises():
    """测试 update 非法 patch 抛出异常."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    with pytest.raises(ValueError, match="unsupported_status"):
        await store.update(created["skill_id"], {"status": "unknown"})


# ==================== delete ====================


@pytest.mark.asyncio
async def test_delete():
    """测试 delete."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    assert await store.delete(created["skill_id"]) is True
    assert await store.get(created["skill_id"]) is None


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_false():
    """测试 delete 不存在的 skill_id 返回 False."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    assert await store.delete("skill_nonexistent") is False


# ==================== list_all ====================


@pytest.mark.asyncio
async def test_list_all_with_status_filter():
    """测试 list_all 带 status 过滤."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    await store.create(_make_skill(name="skill1"))
    await store.create(_make_skill(name="skill2", status="deprecated"))
    await store.create(_make_skill(name="skill3", status="archived"))

    all_skills = await store.list_all()
    assert len(all_skills) == 3

    active = await store.list_all(status="active")
    assert len(active) == 1
    assert active[0]["name"] == "skill1"

    deprecated = await store.list_all(status="deprecated")
    assert len(deprecated) == 1
    assert deprecated[0]["name"] == "skill2"

    archived = await store.list_all(status="archived")
    assert len(archived) == 1
    assert archived[0]["name"] == "skill3"


@pytest.mark.asyncio
async def test_list_all_with_tag_filter():
    """测试 list_all 带 tag 过滤."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    await store.create(_make_skill(name="skill1", tags=["risk", "trading"]))
    await store.create(_make_skill(name="skill2", tags=["compliance"]))
    await store.create(_make_skill(name="skill3", tags=["risk", "audit"]))

    risk_tagged = await store.list_all(tag="risk")
    assert len(risk_tagged) == 2

    trading_tagged = await store.list_all(tag="trading")
    assert len(trading_tagged) == 1
    assert trading_tagged[0]["name"] == "skill1"

    compliance_tagged = await store.list_all(tag="compliance")
    assert len(compliance_tagged) == 1
    assert compliance_tagged[0]["name"] == "skill2"


@pytest.mark.asyncio
async def test_list_all_with_status_and_tag_filter():
    """测试 list_all 同时带 status 和 tag 过滤."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    await store.create(_make_skill(name="skill1", tags=["risk"], status="active"))
    await store.create(_make_skill(name="skill2", tags=["risk"], status="deprecated"))

    active_risk = await store.list_all(status="active", tag="risk")
    assert len(active_risk) == 1
    assert active_risk[0]["name"] == "skill1"


# ==================== search ====================


@pytest.mark.asyncio
async def test_search_semantic():
    """测试 search 语义检索."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    await store.create(
        _make_skill(
            name="交易台风险排查",
            applicable_conditions=["延迟异常"],
            steps=[
                {"description": "查询持仓数据", "expected_outcome": "获取持仓"}
            ],
        )
    )
    await store.create(
        _make_skill(
            name="合规报告生成",
            tags=["compliance"],
            applicable_conditions=["季度审计"],
            steps=[
                {"description": "收集审计数据", "expected_outcome": "生成报告"}
            ],
        )
    )

    hits = await store.search("交易台持仓延迟异常排查")
    assert len(hits) >= 1
    assert hits[0]["name"] == "交易台风险排查"
    assert hits[0].get("semantic_score", 0.0) > 0.0


@pytest.mark.asyncio
async def test_search_filters_non_active():
    """测试 search 过滤非 active 的 Skill."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    await store.create(_make_skill(name="活跃技能", status="active"))
    await store.create(_make_skill(name="废弃技能", status="deprecated"))

    hits = await store.search("技能")
    names = [h["name"] for h in hits]
    assert "活跃技能" in names
    assert "废弃技能" not in names


@pytest.mark.asyncio
async def test_search_min_confidence_filter():
    """测试 search min_confidence 过滤."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    await store.create(_make_skill(name="低置信度技能", confidence=0.3))
    await store.create(_make_skill(name="高置信度技能", confidence=0.9))

    all_hits = await store.search("技能", min_confidence=0.0)
    assert len(all_hits) >= 2

    high_only = await store.search("技能", min_confidence=0.5)
    assert len(high_only) == 1
    assert high_only[0]["name"] == "高置信度技能"


@pytest.mark.asyncio
async def test_search_empty_query_returns_empty():
    """测试 search 空查询返回空列表."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    await store.create(_make_skill())
    hits = await store.search("")
    assert hits == []


# ==================== find_similar ====================


@pytest.mark.asyncio
async def test_find_similar_finds_match():
    """测试 find_similar 找到相似 Skill."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    await store.create(
        _make_skill(
            name="交易台风险排查流程",
            steps=[
                {"description": "查询持仓数据并核对限额", "expected_outcome": "确认风险"}
            ],
        )
    )

    candidate = _make_skill(
        name="交易台风险排查流程",
        steps=[
            {"description": "查询持仓数据并核对限额", "expected_outcome": "确认风险"}
        ],
    )
    similar = await store.find_similar(candidate, threshold=0.0)
    assert len(similar) >= 1
    assert similar[0]["name"] == "交易台风险排查流程"


@pytest.mark.asyncio
async def test_find_similar_excludes_self():
    """测试 find_similar 排除自身."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(name="排查流程"))

    # 用已存储的 skill 查找相似, 应排除自身
    stored = await store.get(created["skill_id"])
    assert stored is not None
    similar = await store.find_similar(stored, threshold=0.0)
    assert all(s["skill_id"] != created["skill_id"] for s in similar)


@pytest.mark.asyncio
async def test_find_similar_high_threshold():
    """测试 find_similar 高阈值不匹配不相关 Skill."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    await store.create(
        _make_skill(
            name="交易台风险排查",
            steps=[{"description": "查持仓", "expected_outcome": "获取数据"}],
        )
    )
    candidate = _make_skill(
        name="合规报告生成",
        tags=["compliance"],
        steps=[{"description": "收集审计数据", "expected_outcome": "生成报告"}],
    )
    similar = await store.find_similar(candidate, threshold=0.99)
    assert len(similar) == 0


# ==================== update_confidence ====================


@pytest.mark.asyncio
async def test_update_confidence_success():
    """测试 update_confidence 成功场景."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))
    updated = await store.update_confidence(created["skill_id"], True, delta=0.1)
    assert updated["confidence"] == pytest.approx(0.6)
    assert updated["usage_count"] == 1
    assert updated["success_rate"] == pytest.approx(1.0)
    assert updated["status"] == "active"


@pytest.mark.asyncio
async def test_update_confidence_failure():
    """测试 update_confidence 失败场景."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))
    updated = await store.update_confidence(created["skill_id"], False, delta=0.1)
    assert updated["confidence"] == pytest.approx(0.4)
    assert updated["usage_count"] == 1
    assert updated["success_rate"] == pytest.approx(0.0)
    assert updated["status"] == "active"


@pytest.mark.asyncio
async def test_update_confidence_mixed():
    """测试 update_confidence 混合成功失败场景."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))

    # 成功一次
    await store.update_confidence(created["skill_id"], True, delta=0.1)
    # 失败一次
    updated = await store.update_confidence(
        created["skill_id"], False, delta=0.1
    )
    assert updated["confidence"] == pytest.approx(0.5)
    assert updated["usage_count"] == 2
    assert updated["success_rate"] == pytest.approx(0.5)
    assert updated["status"] == "active"


@pytest.mark.asyncio
async def test_update_confidence_caps_at_1():
    """测试 update_confidence 上限为 1.0."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.95))
    updated = await store.update_confidence(created["skill_id"], True, delta=0.1)
    assert updated["confidence"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_update_confidence_floors_at_0():
    """测试 update_confidence 下限为 0.0."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.05))
    updated = await store.update_confidence(created["skill_id"], False, delta=0.1)
    assert updated["confidence"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_low_confidence_deprecated():
    """测试低置信度自动降级到 deprecated."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.3))
    updated = await store.update_confidence(created["skill_id"], False, delta=0.05)
    assert updated["confidence"] == pytest.approx(0.25)
    assert updated["status"] == "deprecated"


@pytest.mark.asyncio
async def test_low_confidence_archived():
    """测试极低置信度自动降级到 archived."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.2))
    updated = await store.update_confidence(created["skill_id"], False, delta=0.1)
    assert updated["confidence"] == pytest.approx(0.1)
    assert updated["status"] == "archived"


@pytest.mark.asyncio
async def test_update_confidence_nonexistent_raises():
    """测试 update_confidence 不存在的 skill_id 抛出异常."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    with pytest.raises(KeyError):
        await store.update_confidence("skill_nonexistent", True)


# ==================== health_check ====================


@pytest.mark.asyncio
async def test_health_check():
    """测试 health_check."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    assert await store.health_check() is True
