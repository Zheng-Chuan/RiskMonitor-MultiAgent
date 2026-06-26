"""Skill 置信度动态更新端到端集成测试.

测试从 Skill 创建 → 注入跟踪 → 执行后置信度更新的完整流程.
使用真实 SkillStore (内存存储) 和 ProactiveMultiAgentWorkflow, 不依赖外部 LLM.

测试场景:
1. 完整流程: 创建 Skill → 注入 → 执行成功 → 置信度上升
2. 失败流程: 创建 Skill → 注入 → 执行失败 → 置信度下降
3. 多次使用累积: 同一 Skill 被使用 3 次 → 置信度正确累积
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
        "task_id": "task-confidence-001",
        "intent": "query_positions",
        "content": {
            "category": "risk",
            "description": "查询交易台持仓并核对限额",
        },
    }
    base.update(kwargs)
    return base


def _make_intent_output(**kwargs) -> dict:
    """构造 intent_result.output."""
    base = {
        "primary_intent_type": "query_positions",
        "confidence": 0.95,
    }
    base.update(kwargs)
    return base


# ==================== 1. 完整流程: 创建 → 注入 → 执行成功 → 置信度上升 ====================


@pytest.mark.asyncio
async def test_full_flow_success_increases_confidence():
    """创建 Skill → 注入 → 执行成功 → 置信度上升."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        ProactiveMultiAgentWorkflow,
    )

    workflow = ProactiveMultiAgentWorkflow()

    # 1. 创建 Skill
    created = await workflow._skill_store.create(
        _make_skill(
            name="交易台风险排查",
            applicable_conditions=["延迟异常", "告警触发"],
            steps=[
                {"description": "查询持仓数据", "expected_outcome": "获取持仓"},
                {"description": "核对限额", "expected_outcome": "确认是否超限"},
            ],
            confidence=0.5,
        )
    )
    skill_id = created["skill_id"]
    assert created["confidence"] == pytest.approx(0.5)

    # 2. 注入 (会自动跟踪)
    run_id = "run-integration-001"
    context = await workflow._build_orchestrator_context(
        phase="plan",
        task=_make_task(),
        intent=_make_intent_output(),
        memory_enabled=True,
        planning_memory={"summary": {}},
        run_id=run_id,
    )

    # 验证注入成功
    skill_payload = context["skills"]
    assert skill_payload["skill_count"] >= 1
    assert skill_id in skill_payload["injected_skill_ids"]

    # 验证跟踪记录
    tracked = workflow._skill_usage_tracker.get_tracked_skills(run_id)
    assert skill_id in tracked

    # 3. 执行成功 → 更新置信度
    results = await workflow._skill_usage_tracker.update_after_execution(
        run_id=run_id,
        execution_success=True,
        critic_ok=True,
    )

    # 4. 验证置信度上升
    assert len(results) == 1
    update = results[0]
    assert update["skill_id"] == skill_id
    assert update["old_confidence"] == pytest.approx(0.5)
    assert update["new_confidence"] == pytest.approx(0.55)
    assert update["new_confidence"] > update["old_confidence"]

    # 验证 store 中也更新了
    stored = await workflow._skill_store.get(skill_id)
    assert stored["confidence"] == pytest.approx(0.55)
    assert stored["usage_count"] == 1


# ==================== 2. 失败流程: 创建 → 注入 → 执行失败 → 置信度下降 ====================


@pytest.mark.asyncio
async def test_full_flow_failure_decreases_confidence():
    """创建 Skill → 注入 → 执行失败 → 置信度下降."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        ProactiveMultiAgentWorkflow,
    )

    workflow = ProactiveMultiAgentWorkflow()

    created = await workflow._skill_store.create(
        _make_skill(confidence=0.5)
    )
    skill_id = created["skill_id"]

    run_id = "run-integration-002"
    await workflow._build_orchestrator_context(
        phase="plan",
        task=_make_task(),
        intent=_make_intent_output(),
        memory_enabled=True,
        planning_memory={"summary": {}},
        run_id=run_id,
    )

    # 执行失败 (execution_success=False)
    results = await workflow._skill_usage_tracker.update_after_execution(
        run_id=run_id,
        execution_success=False,
        critic_ok=False,
    )

    assert len(results) == 1
    update = results[0]
    assert update["old_confidence"] == pytest.approx(0.5)
    assert update["new_confidence"] == pytest.approx(0.45)
    assert update["new_confidence"] < update["old_confidence"]
    assert update["success"] is False

    stored = await workflow._skill_store.get(skill_id)
    assert stored["confidence"] == pytest.approx(0.45)
    assert stored["usage_count"] == 1


# ==================== 3. 多次使用累积 ====================


@pytest.mark.asyncio
async def test_multiple_uses_accumulate_confidence():
    """同一 Skill 被使用 3 次 → 置信度正确累积."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        ProactiveMultiAgentWorkflow,
    )

    workflow = ProactiveMultiAgentWorkflow()

    created = await workflow._skill_store.create(
        _make_skill(confidence=0.5)
    )
    skill_id = created["skill_id"]

    # 3 次成功使用
    for i in range(3):
        run_id = f"run-integration-accum-{i:03d}"
        await workflow._build_orchestrator_context(
            phase="plan",
            task=_make_task(),
            intent=_make_intent_output(),
            memory_enabled=True,
            planning_memory={"summary": {}},
            run_id=run_id,
        )
        await workflow._skill_usage_tracker.update_after_execution(
            run_id=run_id,
            execution_success=True,
            critic_ok=True,
        )
        workflow._skill_usage_tracker.clear_tracking(run_id)

    stored = await workflow._skill_store.get(skill_id)
    # 0.5 + 0.05*3 = 0.65
    assert stored["confidence"] == pytest.approx(0.65)
    assert stored["usage_count"] == 3
    assert stored["success_rate"] == pytest.approx(1.0)
    assert stored["status"] == "active"


# ==================== 4. 注入时不传 run_id 不跟踪 ====================


@pytest.mark.asyncio
async def test_no_run_id_no_tracking():
    """_build_orchestrator_context 不传 run_id → 不跟踪."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        ProactiveMultiAgentWorkflow,
    )

    workflow = ProactiveMultiAgentWorkflow()

    await workflow._skill_store.create(_make_skill(confidence=0.5))

    # 不传 run_id
    context = await workflow._build_orchestrator_context(
        phase="plan",
        task=_make_task(),
        intent=_make_intent_output(),
        memory_enabled=True,
        planning_memory={"summary": {}},
    )

    # 注入仍然正常
    assert context["skills"]["skill_count"] >= 1
    # 但没有跟踪记录
    assert workflow._skill_usage_tracker.get_tracked_skills("any-run") == []


# ==================== 5. 清理跟踪后不影响下次使用 ====================


@pytest.mark.asyncio
async def test_clear_tracking_does_not_affect_store():
    """clear_tracking 只清理跟踪记录, 不影响 SkillStore 中的数据."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        ProactiveMultiAgentWorkflow,
    )

    workflow = ProactiveMultiAgentWorkflow()

    created = await workflow._skill_store.create(
        _make_skill(confidence=0.5)
    )
    skill_id = created["skill_id"]

    run_id = "run-integration-clear-001"
    await workflow._build_orchestrator_context(
        phase="plan",
        task=_make_task(),
        intent=_make_intent_output(),
        memory_enabled=True,
        planning_memory={"summary": {}},
        run_id=run_id,
    )
    await workflow._skill_usage_tracker.update_after_execution(
        run_id=run_id,
        execution_success=True,
        critic_ok=True,
    )

    # 清理跟踪
    workflow._skill_usage_tracker.clear_tracking(run_id)
    assert workflow._skill_usage_tracker.get_tracked_skills(run_id) == []

    # store 中的数据不受影响
    stored = await workflow._skill_store.get(skill_id)
    assert stored is not None
    assert stored["confidence"] == pytest.approx(0.55)


# ==================== 6. SkillInjector 返回 injected_skill_ids ====================


@pytest.mark.asyncio
async def test_injector_returns_injected_skill_ids():
    """SkillInjector.retrieve_applicable_skills 返回 injected_skill_ids 列表."""
    from riskmonitor_multiagent.skills import SkillInjector, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.9))

    injector = SkillInjector(store, min_confidence=0.3, max_skills=3)
    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
    )

    assert "injected_skill_ids" in result
    assert created["skill_id"] in result["injected_skill_ids"]

    # property 也可用
    assert created["skill_id"] in injector.last_injected_skill_ids


@pytest.mark.asyncio
async def test_injector_last_injected_skill_ids_empty_when_no_match():
    """无匹配 Skill 时 last_injected_skill_ids 为空."""
    from riskmonitor_multiagent.skills import SkillInjector, SkillStore

    store = SkillStore()
    injector = SkillInjector(store)

    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
    )

    assert result["injected_skill_ids"] == []
    assert injector.last_injected_skill_ids == []


@pytest.mark.asyncio
async def test_injector_last_injected_skill_ids_empty_when_disabled():
    """skill_enabled=False 时 last_injected_skill_ids 为空."""
    from riskmonitor_multiagent.skills import SkillInjector, SkillStore

    store = SkillStore()
    await store.create(_make_skill(confidence=0.9))
    injector = SkillInjector(store)

    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=False,
    )

    assert result["injected_skill_ids"] == []
    assert injector.last_injected_skill_ids == []


# ==================== 7. critic_ok=False 导致失败 ====================


@pytest.mark.asyncio
async def test_critic_not_ok_treated_as_failure():
    """execution_success=True 但 critic_ok=False → 置信度下降."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        ProactiveMultiAgentWorkflow,
    )

    workflow = ProactiveMultiAgentWorkflow()

    created = await workflow._skill_store.create(
        _make_skill(confidence=0.5)
    )
    skill_id = created["skill_id"]

    run_id = "run-integration-critic-fail"
    await workflow._build_orchestrator_context(
        phase="plan",
        task=_make_task(),
        intent=_make_intent_output(),
        memory_enabled=True,
        planning_memory={"summary": {}},
        run_id=run_id,
    )

    results = await workflow._skill_usage_tracker.update_after_execution(
        run_id=run_id,
        execution_success=True,
        critic_ok=False,
    )

    assert len(results) == 1
    assert results[0]["new_confidence"] == pytest.approx(0.45)
    assert results[0]["success"] is False


# ==================== 8. 连续失败导致降级 ====================


@pytest.mark.asyncio
async def test_consecutive_failures_degrade_in_workflow():
    """连续失败 → Skill 自动降级为 deprecated 再到 archived."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        ProactiveMultiAgentWorkflow,
    )

    workflow = ProactiveMultiAgentWorkflow()

    created = await workflow._skill_store.create(
        _make_skill(confidence=0.35)
    )
    skill_id = created["skill_id"]

    # 第1次失败: 0.35 -> 0.30 (active, 刚好等于 0.3 不低于)
    # 通过注入流程自动跟踪
    run_id = "run-degrade-001"
    await workflow._build_orchestrator_context(
        phase="plan", task=_make_task(), intent=_make_intent_output(),
        memory_enabled=True, planning_memory={"summary": {}}, run_id=run_id,
    )
    await workflow._skill_usage_tracker.update_after_execution(
        run_id=run_id, execution_success=False, critic_ok=False
    )
    workflow._skill_usage_tracker.clear_tracking(run_id)
    stored = await workflow._skill_store.get(skill_id)
    assert stored["status"] == "active"
    assert stored["confidence"] == pytest.approx(0.30)

    # 第2次失败: 0.30 -> 0.25 (deprecated, below 0.3)
    # Skill 仍为 active, 注入流程可自动跟踪
    run_id = "run-degrade-002"
    await workflow._build_orchestrator_context(
        phase="plan", task=_make_task(), intent=_make_intent_output(),
        memory_enabled=True, planning_memory={"summary": {}}, run_id=run_id,
    )
    await workflow._skill_usage_tracker.update_after_execution(
        run_id=run_id, execution_success=False, critic_ok=False
    )
    workflow._skill_usage_tracker.clear_tracking(run_id)
    stored = await workflow._skill_store.get(skill_id)
    assert stored["status"] == "deprecated"
    assert stored["confidence"] == pytest.approx(0.25)

    # 第3次失败: 0.25 -> 0.20 (deprecated, still above 0.15)
    # Skill 已 deprecated, search 不再返回它, 手动跟踪
    run_id = "run-degrade-003"
    workflow._skill_usage_tracker.track_usage(skill_id, run_id=run_id)
    await workflow._skill_usage_tracker.update_after_execution(
        run_id=run_id, execution_success=False, critic_ok=False
    )
    workflow._skill_usage_tracker.clear_tracking(run_id)
    stored = await workflow._skill_store.get(skill_id)
    assert stored["status"] == "deprecated"
    assert stored["confidence"] == pytest.approx(0.20)

    # 第4次失败: 0.20 -> 0.15 (deprecated, equals 0.15 not below)
    run_id = "run-degrade-004"
    workflow._skill_usage_tracker.track_usage(skill_id, run_id=run_id)
    await workflow._skill_usage_tracker.update_after_execution(
        run_id=run_id, execution_success=False, critic_ok=False
    )
    workflow._skill_usage_tracker.clear_tracking(run_id)
    stored = await workflow._skill_store.get(skill_id)
    assert stored["status"] == "deprecated"
    assert stored["confidence"] == pytest.approx(0.15)

    # 第5次失败: 0.15 -> 0.10 (archived, below 0.15)
    run_id = "run-degrade-005"
    workflow._skill_usage_tracker.track_usage(skill_id, run_id=run_id)
    await workflow._skill_usage_tracker.update_after_execution(
        run_id=run_id, execution_success=False, critic_ok=False
    )
    workflow._skill_usage_tracker.clear_tracking(run_id)
    stored = await workflow._skill_store.get(skill_id)
    assert stored["status"] == "archived"
    assert stored["confidence"] == pytest.approx(0.10)
