"""Skill 改进闭环端到端集成测试.

测试从 Skill 使用 → 失败 → 修订 → 再次使用 → 改善的完整流程.
使用真实 SkillStore (内存存储) 和 SkillReviser, 不依赖外部 LLM.

测试场景:
1. Skill 使用 → 失败 → 修订 → 再次使用 → 改善
2. 修订链路完整: check → propose → apply → verify
3. A/B 对比验证
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
        "confidence": 0.6,
    }
    base.update(kwargs)
    return base


def _make_critic_fail(**kwargs) -> dict:
    """构造 critic ok=False 的评审结果."""
    base = {
        "ok": False,
        "confidence": 0.3,
        "issues": [
            {"message": "持仓数据不完整", "code": "INCOMPLETE_DATA"},
            {"message": "限额核对遗漏", "code": "MISSING_CHECK"},
        ],
        "risk_level": "HIGH",
    }
    base.update(kwargs)
    return base


def _make_critic_ok(**kwargs) -> dict:
    """构造 critic ok=True 的评审结果."""
    base = {
        "ok": True,
        "confidence": 0.9,
        "issues": [],
        "risk_level": "LOW",
    }
    base.update(kwargs)
    return base


def _make_execution_result(**kwargs) -> dict:
    """构造执行结果."""
    base = {
        "status": "completed",
        "final_output": {"summary": "执行完成"},
        "failed_steps": [
            {"description": "核对限额", "step_id": "s2"},
        ],
        "receipts": [],
    }
    base.update(kwargs)
    return base


# ==================== 1. Skill 使用 → 失败 → 修订 → 再次使用 → 改善 ====================


@pytest.mark.asyncio
async def test_skill_revision_improves_outcome():
    """Skill 使用 → 失败 → 修订 → 再次使用 → A/B 对比显示改善."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    skill_id = created["skill_id"]
    original_steps = list(created["steps"])

    reviser = SkillReviser(store)

    # 1. Skill 被使用但执行失败 (critic ok=False)
    proposal = await reviser.check_and_propose_revision(
        skill_id=skill_id,
        run_id="run-001",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_fail(),
    )
    assert proposal is not None

    # 2. 应用修订
    updated = await reviser.apply_revision(skill_id=skill_id, proposal=proposal)
    assert len(updated["revision_history"]) == 1
    assert updated["steps"] != original_steps

    # 3. A/B 对比: revised steps 在失败场景中表现不劣于 original
    test_cases = [
        {
            "expected_outcomes": ["获取当前持仓", "确认是否超限", "issue_resolved"],
            "expect_failure": True,
        },
        {
            "expected_outcomes": ["获取当前持仓", "确认是否超限"],
            "expect_failure": True,
        },
    ]

    ab_result = await reviser.ab_compare(
        skill_id=skill_id,
        original_steps=original_steps,
        revised_steps=updated["steps"],
        test_cases=test_cases,
    )

    assert ab_result["passed"] is True
    assert ab_result["revised_score"] > ab_result["original_score"]

    # 4. 再次使用: critic ok=True → 不再提议修订
    proposal2 = await reviser.check_and_propose_revision(
        skill_id=skill_id,
        run_id="run-002",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_ok(),
    )
    assert proposal2 is None


# ==================== 2. 修订链路完整: check → propose → apply → verify ====================


@pytest.mark.asyncio
async def test_full_revision_chain():
    """修订链路: check → propose → apply → verify (store 中的数据正确更新)."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    skill_id = created["skill_id"]

    reviser = SkillReviser(store)

    # Step 1: check_and_propose_revision
    proposal = await reviser.check_and_propose_revision(
        skill_id=skill_id,
        run_id="run-chain-001",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_fail(),
    )
    assert proposal is not None
    assert proposal.skill_id == skill_id
    assert proposal.revision_id.startswith("rev_")
    assert len(proposal.original_steps) == 2
    assert len(proposal.revised_steps) == 3  # 2 original + 1 recovery

    # Step 2: apply_revision
    result = await reviser.apply_revision(skill_id=skill_id, proposal=proposal)

    # Step 3: verify store 中的数据
    assert result["skill_id"] == skill_id
    assert result["write_origin"] == "revision"
    assert len(result["revision_history"]) == 1

    rev_entry = result["revision_history"][0]
    assert rev_entry["revision_id"] == proposal.revision_id
    assert rev_entry["reason"] == proposal.reason
    assert rev_entry["proposed_by"] == "critic"
    assert rev_entry["original_steps"] == proposal.original_steps
    assert rev_entry["revised_steps"] == proposal.revised_steps
    assert rev_entry["original_failure_boundary"] == proposal.original_failure_boundary
    assert rev_entry["revised_failure_boundary"] == proposal.revised_failure_boundary

    # verify steps 已更新
    assert result["steps"] == proposal.revised_steps
    # verify failure_boundary 已更新
    assert result["failure_boundary"] == proposal.revised_failure_boundary
    # verify updated_at 已刷新
    assert result["updated_at"] >= created["updated_at"]

    # verify 从 store 重新读取数据一致
    stored = await store.get(skill_id)
    assert stored["steps"] == proposal.revised_steps
    assert stored["failure_boundary"] == proposal.revised_failure_boundary
    assert len(stored["revision_history"]) == 1


# ==================== 3. A/B 对比验证 ====================


@pytest.mark.asyncio
async def test_ab_compare_integration():
    """A/B 对比集成测试: 修订后的 steps 在多种场景中不劣于修订前."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    skill_id = created["skill_id"]
    original_steps = list(created["steps"])

    reviser = SkillReviser(store)

    # 生成修订提案
    proposal = await reviser.check_and_propose_revision(
        skill_id=skill_id,
        run_id="run-ab-001",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_fail(),
    )
    assert proposal is not None

    # A/B 对比: 多种场景
    test_cases = [
        # 场景1: 预期失败, recovery 步骤有帮助
        {
            "expected_outcomes": ["获取当前持仓", "确认是否超限", "issue_resolved"],
            "expect_failure": True,
        },
        # 场景2: 预期成功, failure_note 仍有帮助
        {
            "expected_outcomes": ["获取当前持仓", "确认是否超限"],
            "expect_failure": False,
        },
        # 场景3: 无特别期望
        {
            "expected_outcomes": [],
            "expect_failure": True,
        },
    ]

    result = await reviser.ab_compare(
        skill_id=skill_id,
        original_steps=original_steps,
        revised_steps=proposal.revised_steps,
        test_cases=test_cases,
    )

    assert result["passed"] is True
    assert result["revised_score"] >= result["original_score"]
    assert len(result["case_results"]) == 3

    for case_result in result["case_results"]:
        assert "original_score" in case_result
        assert "revised_score" in case_result
        assert 0.0 <= case_result["original_score"] <= 1.0
        assert 0.0 <= case_result["revised_score"] <= 1.0


# ==================== 4. 多次修订链路 ====================


@pytest.mark.asyncio
async def test_multiple_revision_chain():
    """连续多次修订 → revision_history 累积, 每次 steps 都更新."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    skill_id = created["skill_id"]

    reviser = SkillReviser(store)

    for i in range(3):
        proposal = await reviser.check_and_propose_revision(
            skill_id=skill_id,
            run_id=f"run-multi-{i:03d}",
            execution_result=_make_execution_result(),
            critic_final=_make_critic_fail(),
        )
        assert proposal is not None
        result = await reviser.apply_revision(skill_id=skill_id, proposal=proposal)

        # 验证 revision_history 累积
        assert len(result["revision_history"]) == i + 1

        # 验证每次 revision_id 不同
        rev_ids = [r["revision_id"] for r in result["revision_history"]]
        assert len(set(rev_ids)) == i + 1

    stored = await store.get(skill_id)
    assert len(stored["revision_history"]) == 3

    # 验证可回滚: 第一次修订的 original_steps 等于原始 steps
    first_rev = stored["revision_history"][0]
    assert first_rev["original_steps"] == created["steps"]


# ==================== 5. 异常隔离: 修订失败不影响主流程 ====================


@pytest.mark.asyncio
async def test_revision_exception_isolated():
    """SkillReviser 异常不影响后续操作."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore
    from unittest.mock import AsyncMock, patch

    store = SkillStore()
    created = await store.create(_make_skill())
    skill_id = created["skill_id"]

    reviser = SkillReviser(store)

    # 正常提议修订
    proposal = await reviser.check_and_propose_revision(
        skill_id=skill_id,
        run_id="run-exc-001",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_fail(),
    )
    assert proposal is not None

    # 模拟 store.update 抛异常
    with patch.object(
        store, "update", new_callable=AsyncMock, side_effect=RuntimeError("db error")
    ):
        with pytest.raises(RuntimeError):
            await reviser.apply_revision(skill_id=skill_id, proposal=proposal)

    # 验证 store 中的数据未变 (update 失败)
    stored = await store.get(skill_id)
    assert stored["steps"] == created["steps"]
    assert len(stored["revision_history"]) == 0

    # 验证可以正常重新提议和修订
    proposal2 = await reviser.check_and_propose_revision(
        skill_id=skill_id,
        run_id="run-exc-002",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_fail(),
    )
    assert proposal2 is not None

    result = await reviser.apply_revision(skill_id=skill_id, proposal=proposal2)
    assert len(result["revision_history"]) == 1


# ==================== 6. revision_history 可回滚 ====================


@pytest.mark.asyncio
async def test_revision_history_rollback():
    """apply_revision 后可以通过 revision_history 回滚到任意版本."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    skill_id = created["skill_id"]
    original_steps = list(created["steps"])
    original_fb = created["failure_boundary"]

    reviser = SkillReviser(store)

    # 第一次修订
    proposal1 = await reviser.check_and_propose_revision(
        skill_id=skill_id,
        run_id="run-rollback-001",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_fail(),
    )
    result1 = await reviser.apply_revision(skill_id=skill_id, proposal=proposal1)

    # 第二次修订
    proposal2 = await reviser.check_and_propose_revision(
        skill_id=skill_id,
        run_id="run-rollback-002",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_fail(),
    )
    result2 = await reviser.apply_revision(skill_id=skill_id, proposal=proposal2)

    assert len(result2["revision_history"]) == 2

    # 回滚到第一次修订前的状态 (使用第一次修订的 original_steps)
    first_rev = result2["revision_history"][0]
    await store.update(skill_id, {
        "steps": first_rev["original_steps"],
        "failure_boundary": first_rev["original_failure_boundary"],
    })

    rolled_back = await store.get(skill_id)
    assert rolled_back["steps"] == original_steps
    assert rolled_back["failure_boundary"] == original_fb
    # revision_history 保留 (可追溯)
    assert len(rolled_back["revision_history"]) == 2


# ==================== 7. 与 ProactiveMultiAgentWorkflow 集成 ====================


@pytest.mark.asyncio
async def test_workflow_revision_after_critic_fail():
    """ProactiveMultiAgentWorkflow 中 critic 失败后自动触发 Skill 修订."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        ProactiveMultiAgentWorkflow,
    )

    workflow = ProactiveMultiAgentWorkflow()

    # 创建 Skill
    created = await workflow._skill_store.create(_make_skill(confidence=0.7))
    skill_id = created["skill_id"]
    original_steps = list(created["steps"])

    # 模拟 Skill 注入 + 跟踪
    run_id = "run-workflow-revision"
    workflow._skill_usage_tracker.track_usage(skill_id, run_id=run_id)

    # 模拟执行失败 + critic 失败 → 触发修订
    execution_result = _make_execution_result()
    critic_final = _make_critic_fail()

    # 手动模拟 post-critic 逻辑
    tracked_skill_ids = workflow._skill_usage_tracker.get_tracked_skills(run_id)
    assert skill_id in tracked_skill_ids

    # 清理跟踪 (模拟 finally 块)
    workflow._skill_usage_tracker.clear_tracking(run_id)

    # 使用 SkillReviser 进行修订
    from riskmonitor_multiagent.skills import SkillReviser

    reviser = SkillReviser(workflow._skill_store)
    proposal = await reviser.check_and_propose_revision(
        skill_id=skill_id,
        run_id=run_id,
        execution_result=execution_result.get("final_output", {}),
        critic_final=critic_final,
    )
    assert proposal is not None

    result = await reviser.apply_revision(skill_id=skill_id, proposal=proposal)

    # 验证 Skill 已修订
    assert result["steps"] != original_steps
    assert len(result["revision_history"]) == 1
    assert result["write_origin"] == "revision"

    # 验证 store 中的数据一致
    stored = await workflow._skill_store.get(skill_id)
    assert len(stored["revision_history"]) == 1
    assert stored["steps"] == result["steps"]
