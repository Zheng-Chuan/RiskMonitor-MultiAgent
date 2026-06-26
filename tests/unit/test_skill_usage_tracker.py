"""SkillUsageTracker 单测."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

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


# ==================== 1. track_usage 记录 ====================


@pytest.mark.asyncio
async def test_track_usage_records_skill_id():
    """调用 track_usage → get_tracked_skills 返回正确的 skill_id."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill())
    tracker = SkillUsageTracker(store)

    tracker.track_usage(created["skill_id"], run_id="run-001", phase="planning")

    tracked = tracker.get_tracked_skills("run-001")
    assert tracked == [created["skill_id"]]


@pytest.mark.asyncio
async def test_track_usage_dedup_same_skill():
    """同一 run 中同一 skill_id 只记录一次."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill())
    tracker = SkillUsageTracker(store)

    tracker.track_usage(created["skill_id"], run_id="run-001")
    tracker.track_usage(created["skill_id"], run_id="run-001")

    tracked = tracker.get_tracked_skills("run-001")
    assert len(tracked) == 1
    assert tracked == [created["skill_id"]]


@pytest.mark.asyncio
async def test_track_usage_separate_runs():
    """不同 run 的跟踪记录相互独立."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill())
    tracker = SkillUsageTracker(store)

    tracker.track_usage(created["skill_id"], run_id="run-001")
    tracker.track_usage(created["skill_id"], run_id="run-002")

    assert tracker.get_tracked_skills("run-001") == [created["skill_id"]]
    assert tracker.get_tracked_skills("run-002") == [created["skill_id"]]
    assert tracker.get_tracked_skills("run-003") == []


# ==================== 2. 成功执行置信度上升 ====================


@pytest.mark.asyncio
async def test_success_execution_increases_confidence():
    """update_after_execution(success=True, ok=True) → confidence 增加."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))
    tracker = SkillUsageTracker(store)

    tracker.track_usage(created["skill_id"], run_id="run-001")
    results = await tracker.update_after_execution(
        run_id="run-001",
        execution_success=True,
        critic_ok=True,
    )

    assert len(results) == 1
    update = results[0]
    assert update["skill_id"] == created["skill_id"]
    assert update["old_confidence"] == pytest.approx(0.5)
    assert update["new_confidence"] == pytest.approx(0.55)
    assert update["new_confidence"] > update["old_confidence"]
    assert update["success"] is True
    assert update["old_status"] == "active"
    assert update["new_status"] == "active"


# ==================== 3. 失败执行置信度下降 ====================


@pytest.mark.asyncio
async def test_failure_execution_decreases_confidence():
    """update_after_execution(success=False) → confidence 减少."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))
    tracker = SkillUsageTracker(store)

    tracker.track_usage(created["skill_id"], run_id="run-001")
    results = await tracker.update_after_execution(
        run_id="run-001",
        execution_success=False,
        critic_ok=False,
    )

    assert len(results) == 1
    update = results[0]
    assert update["old_confidence"] == pytest.approx(0.5)
    assert update["new_confidence"] == pytest.approx(0.45)
    assert update["new_confidence"] < update["old_confidence"]
    assert update["success"] is False


# ==================== 4. 多次成功后置信度累积 ====================


@pytest.mark.asyncio
async def test_multiple_successes_accumulate_confidence():
    """连续 3 次成功 → confidence 持续上升."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))
    tracker = SkillUsageTracker(store)

    for i in range(3):
        run_id = f"run-{i:03d}"
        tracker.track_usage(created["skill_id"], run_id=run_id)
        await tracker.update_after_execution(
            run_id=run_id,
            execution_success=True,
            critic_ok=True,
        )
        tracker.clear_tracking(run_id)

    stored = await store.get(created["skill_id"])
    assert stored["confidence"] == pytest.approx(0.65)
    assert stored["usage_count"] == 3


# ==================== 5. 连续失败自动降级 ====================


@pytest.mark.asyncio
async def test_consecutive_failures_deprecate():
    """confidence 降到 0.3 以下 → status 变为 deprecated."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.35))
    tracker = SkillUsageTracker(store)

    # 0.35 - 0.05 = 0.30 (not below 0.3, still active)
    tracker.track_usage(created["skill_id"], run_id="run-001")
    results = await tracker.update_after_execution(
        run_id="run-001", execution_success=False, critic_ok=False
    )
    assert results[0]["new_status"] == "active"
    assert results[0]["new_confidence"] == pytest.approx(0.30)

    # 0.30 - 0.05 = 0.25 (below 0.3, deprecated)
    tracker.clear_tracking("run-001")
    tracker.track_usage(created["skill_id"], run_id="run-002")
    results = await tracker.update_after_execution(
        run_id="run-002", execution_success=False, critic_ok=False
    )
    assert results[0]["new_status"] == "deprecated"
    assert results[0]["new_confidence"] == pytest.approx(0.25)


# ==================== 6. 极端失败自动归档 ====================


@pytest.mark.asyncio
async def test_extreme_failures_archive():
    """confidence 降到 0.15 以下 → status 变为 archived."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.2))
    tracker = SkillUsageTracker(store)

    # 0.2 - 0.05 = 0.15 (not below 0.15, deprecated since below 0.3)
    tracker.track_usage(created["skill_id"], run_id="run-001")
    results = await tracker.update_after_execution(
        run_id="run-001", execution_success=False, critic_ok=False
    )
    assert results[0]["new_status"] == "deprecated"
    assert results[0]["new_confidence"] == pytest.approx(0.15)

    # 0.15 - 0.05 = 0.10 (below 0.15, archived)
    tracker.clear_tracking("run-001")
    tracker.track_usage(created["skill_id"], run_id="run-002")
    results = await tracker.update_after_execution(
        run_id="run-002", execution_success=False, critic_ok=False
    )
    assert results[0]["new_status"] == "archived"
    assert results[0]["new_confidence"] == pytest.approx(0.10)


# ==================== 7. clear_tracking 清理 ====================


@pytest.mark.asyncio
async def test_clear_tracking_empties_records():
    """clear_tracking 后 get_tracked_skills 返回空."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill())
    tracker = SkillUsageTracker(store)

    tracker.track_usage(created["skill_id"], run_id="run-001")
    assert len(tracker.get_tracked_skills("run-001")) == 1

    tracker.clear_tracking("run-001")
    assert tracker.get_tracked_skills("run-001") == []


@pytest.mark.asyncio
async def test_clear_tracking_nonexistent_run_safe():
    """clear_tracking 不存在的 run_id 不报错."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    tracker = SkillUsageTracker(store)
    # Should not raise
    tracker.clear_tracking("run-nonexistent")


# ==================== 8. 多个 Skill 同时更新 ====================


@pytest.mark.asyncio
async def test_multiple_skills_updated_at_once():
    """跟踪 3 个 Skill → 一次执行后全部更新."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    tracker = SkillUsageTracker(store)

    skill_ids = []
    for i in range(3):
        created = await store.create(
            _make_skill(name=f"技能{i}", confidence=0.5)
        )
        skill_ids.append(created["skill_id"])
        tracker.track_usage(created["skill_id"], run_id="run-001")

    assert len(tracker.get_tracked_skills("run-001")) == 3

    results = await tracker.update_after_execution(
        run_id="run-001",
        execution_success=True,
        critic_ok=True,
    )

    assert len(results) == 3
    updated_ids = {r["skill_id"] for r in results}
    assert updated_ids == set(skill_ids)
    for r in results:
        assert r["new_confidence"] == pytest.approx(0.55)
        assert r["success"] is True


# ==================== 9. execution_success 和 critic_ok 组合判断 ====================


@pytest.mark.asyncio
async def test_combination_success_true_ok_true():
    """success=True, ok=True → delta=+0.05 (success)."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))
    tracker = SkillUsageTracker(store)

    tracker.track_usage(created["skill_id"], run_id="run-001")
    results = await tracker.update_after_execution(
        run_id="run-001", execution_success=True, critic_ok=True
    )

    assert results[0]["new_confidence"] == pytest.approx(0.55)
    assert results[0]["success"] is True


@pytest.mark.asyncio
async def test_combination_success_true_ok_false():
    """success=True, ok=False → delta=-0.05 (failure)."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))
    tracker = SkillUsageTracker(store)

    tracker.track_usage(created["skill_id"], run_id="run-001")
    results = await tracker.update_after_execution(
        run_id="run-001", execution_success=True, critic_ok=False
    )

    assert results[0]["new_confidence"] == pytest.approx(0.45)
    assert results[0]["success"] is False


@pytest.mark.asyncio
async def test_combination_success_false_ok_true():
    """success=False, ok=True → delta=-0.05 (failure)."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))
    tracker = SkillUsageTracker(store)

    tracker.track_usage(created["skill_id"], run_id="run-001")
    results = await tracker.update_after_execution(
        run_id="run-001", execution_success=False, critic_ok=True
    )

    assert results[0]["new_confidence"] == pytest.approx(0.45)
    assert results[0]["success"] is False


@pytest.mark.asyncio
async def test_combination_success_false_ok_false():
    """success=False, ok=False → delta=-0.05 (failure)."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))
    tracker = SkillUsageTracker(store)

    tracker.track_usage(created["skill_id"], run_id="run-001")
    results = await tracker.update_after_execution(
        run_id="run-001", execution_success=False, critic_ok=False
    )

    assert results[0]["new_confidence"] == pytest.approx(0.45)
    assert results[0]["success"] is False


# ==================== 额外: 无跟踪记录时返回空 ====================


@pytest.mark.asyncio
async def test_no_tracked_skills_returns_empty():
    """无跟踪记录 → update_after_execution 返回空列表."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    tracker = SkillUsageTracker(store)

    results = await tracker.update_after_execution(
        run_id="run-nonexistent",
        execution_success=True,
        critic_ok=True,
    )
    assert results == []


# ==================== 额外: 自定义 delta ====================


@pytest.mark.asyncio
async def test_custom_success_delta():
    """自定义 success_delta=0.1 → 成功时 confidence 增加 0.1."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))
    tracker = SkillUsageTracker(store, success_delta=0.1, fail_delta=0.1)

    tracker.track_usage(created["skill_id"], run_id="run-001")
    results = await tracker.update_after_execution(
        run_id="run-001", execution_success=True, critic_ok=True
    )

    assert results[0]["new_confidence"] == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_custom_fail_delta():
    """自定义 fail_delta=0.1 → 失败时 confidence 减少 0.1."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))
    tracker = SkillUsageTracker(store, success_delta=0.05, fail_delta=0.1)

    tracker.track_usage(created["skill_id"], run_id="run-001")
    results = await tracker.update_after_execution(
        run_id="run-001", execution_success=False, critic_ok=False
    )

    assert results[0]["new_confidence"] == pytest.approx(0.4)


# ==================== 额外: 异常隔离 ====================


@pytest.mark.asyncio
async def test_update_confidence_exception_does_not_crash():
    """skill_store.update_confidence 抛异常时不崩溃, 返回空结果."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    created = await store.create(_make_skill())
    tracker = SkillUsageTracker(store)

    tracker.track_usage(created["skill_id"], run_id="run-001")

    with patch.object(
        store, "update_confidence", new_callable=AsyncMock, side_effect=RuntimeError("db error")
    ):
        results = await tracker.update_after_execution(
            run_id="run-001", execution_success=True, critic_ok=True
        )

    assert results == []


@pytest.mark.asyncio
async def test_skill_not_found_skipped():
    """skill_id 在 store 中不存在时跳过, 不崩溃."""
    from riskmonitor_multiagent.skills import SkillStore, SkillUsageTracker

    store = SkillStore()
    tracker = SkillUsageTracker(store)

    tracker.track_usage("skill_nonexistent", run_id="run-001")
    results = await tracker.update_after_execution(
        run_id="run-001", execution_success=True, critic_ok=True
    )

    assert results == []
