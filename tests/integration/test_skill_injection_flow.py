"""Skill 注入规划链路端到端集成测试.

测试从 Skill 创建到 orchestrator context 注入的完整流程.
使用真实 SkillStore (内存存储) 和 ProactiveMultiAgentWorkflow, 不依赖外部 LLM.

测试场景:
1. 创建 Skill → 构建 orchestrator context → 检查 context 中是否包含 skills
2. skill_off 对照: memory_enabled=False → context 中 skills 为空
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
        "task_id": "task-injection-001",
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


# ==================== 端到端: Skill 注入到 orchestrator context ====================


@pytest.mark.asyncio
async def test_skill_injected_into_orchestrator_context():
    """创建 Skill → 构建 orchestrator context → 检查 context 中包含 skills."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        ProactiveMultiAgentWorkflow,
    )

    workflow = ProactiveMultiAgentWorkflow()

    # 在 workflow 的 _skill_store 中创建匹配的 Skill
    await workflow._skill_store.create(
        _make_skill(
            name="交易台风险排查",
            applicable_conditions=["延迟异常", "告警触发"],
            steps=[
                {"description": "查询持仓数据", "expected_outcome": "获取持仓"},
                {"description": "核对限额", "expected_outcome": "确认是否超限"},
            ],
            failure_boundary="禁止伪造数据",
            confidence=0.85,
        )
    )

    # 构建 orchestrator context
    context = await workflow._build_orchestrator_context(
        phase="plan",
        task=_make_task(),
        intent=_make_intent_output(),
        memory_enabled=True,
        planning_memory={"summary": {}},
    )

    # 验证 context 包含 skills 字段
    assert "skills" in context
    skill_payload = context["skills"]
    assert skill_payload["skill_enabled"] is True
    assert skill_payload["skill_count"] >= 1
    assert len(skill_payload["skills"]) >= 1

    # 验证注入的 Skill 内容
    injected = skill_payload["skills"][0]
    assert injected["name"] == "交易台风险排查"
    assert injected["skill_id"].startswith("skill_")
    assert len(injected["steps"]) == 2
    assert injected["steps"][0]["description"] == "查询持仓数据"
    assert injected["failure_boundary"] == "禁止伪造数据"
    assert injected["confidence"] == pytest.approx(0.85)

    # 验证 injection_summary 存在且包含数量
    assert "injection_summary" in skill_payload
    assert str(skill_payload["skill_count"]) in skill_payload["injection_summary"]


@pytest.mark.asyncio
async def test_skill_off_context_has_empty_skills():
    """skill_enabled=False → context 中 skills 为空."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        ProactiveMultiAgentWorkflow,
    )

    workflow = ProactiveMultiAgentWorkflow()

    # 即使创建了 Skill, skill_off 时也不应注入
    await workflow._skill_store.create(
        _make_skill(
            name="交易台风险排查",
            confidence=0.9,
        )
    )

    context = await workflow._build_orchestrator_context(
        phase="plan",
        task=_make_task(),
        intent=_make_intent_output(),
        memory_enabled=False,  # skill 跟随 memory_enabled
        planning_memory={"summary": {}},
    )

    # 验证 skills 存在但为空
    assert "skills" in context
    skill_payload = context["skills"]
    assert skill_payload["skill_enabled"] is False
    assert skill_payload["skills"] == []
    assert skill_payload["skill_count"] == 0


@pytest.mark.asyncio
async def test_no_matching_skill_returns_empty():
    """SkillStore 中无匹配 Skill → context skills 为空但结构正确."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        ProactiveMultiAgentWorkflow,
    )

    workflow = ProactiveMultiAgentWorkflow()
    # 不创建任何 Skill

    context = await workflow._build_orchestrator_context(
        phase="plan",
        task=_make_task(),
        intent=_make_intent_output(),
        memory_enabled=True,
        planning_memory={"summary": {}},
    )

    assert "skills" in context
    skill_payload = context["skills"]
    assert skill_payload["skill_enabled"] is True
    assert skill_payload["skills"] == []
    assert skill_payload["skill_count"] == 0


@pytest.mark.asyncio
async def test_replan_phase_also_injects_skills():
    """replan 阶段也注入 Skill."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        ProactiveMultiAgentWorkflow,
    )

    workflow = ProactiveMultiAgentWorkflow()

    await workflow._skill_store.create(
        _make_skill(
            name="交易台风险排查",
            confidence=0.85,
        )
    )

    context = await workflow._build_orchestrator_context(
        phase="replan",
        task=_make_task(),
        intent=_make_intent_output(),
        memory_enabled=True,
        planning_memory={"summary": {}},
    )

    assert context["phase"] == "replan"
    assert "skills" in context
    assert context["skills"]["skill_enabled"] is True
    assert context["skills"]["skill_count"] >= 1


@pytest.mark.asyncio
async def test_skill_injection_does_not_affect_memory_field():
    """Skill 注入不影响 memory 字段."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        ProactiveMultiAgentWorkflow,
    )

    workflow = ProactiveMultiAgentWorkflow()

    await workflow._skill_store.create(
        _make_skill(confidence=0.9)
    )

    memory_summary = {"hit_count": 3, "texts": ["test memory"]}
    context = await workflow._build_orchestrator_context(
        phase="plan",
        task=_make_task(),
        intent=_make_intent_output(),
        memory_enabled=True,
        planning_memory={"summary": memory_summary},
    )

    # memory 字段应正常存在
    assert context["memory"] == memory_summary
    # skills 字段也应存在
    assert "skills" in context
