"""SkillReviser 单测."""

import sys
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
        "confidence": 0.6,
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


# ==================== 1. check_and_propose_revision: critic ok=True → 不提议 ====================


@pytest.mark.asyncio
async def test_check_and_propose_no_revision_when_ok():
    """critic ok=True 且无 issues → 不提议修订."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    reviser = SkillReviser(store)

    proposal = await reviser.check_and_propose_revision(
        skill_id=created["skill_id"],
        run_id="run-001",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_ok(),
    )

    assert proposal is None


# ==================== 2. check_and_propose_revision: critic ok=False → 提议修订 ====================


@pytest.mark.asyncio
async def test_check_and_propose_revision_when_fail():
    """critic ok=False → 提议修订."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    reviser = SkillReviser(store)

    proposal = await reviser.check_and_propose_revision(
        skill_id=created["skill_id"],
        run_id="run-001",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_fail(),
    )

    assert proposal is not None
    assert proposal.skill_id == created["skill_id"]
    assert proposal.revision_id.startswith("rev_")
    assert "持仓数据不完整" in proposal.reason or "INCOMPLETE_DATA" in proposal.reason
    assert len(proposal.revised_steps) > len(proposal.original_steps)
    assert proposal.proposed_by == "critic"
    assert proposal.proposed_at > 0


@pytest.mark.asyncio
async def test_check_and_propose_revision_skill_not_found():
    """skill_id 不存在 → 返回 None."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    reviser = SkillReviser(store)

    proposal = await reviser.check_and_propose_revision(
        skill_id="skill_nonexistent",
        run_id="run-001",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_fail(),
    )

    assert proposal is None


@pytest.mark.asyncio
async def test_check_and_propose_with_issues_but_ok_true():
    """critic ok=True 但有 issues → 仍然提议修订."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    reviser = SkillReviser(store)

    critic = _make_critic_ok()
    critic["issues"] = [{"message": "minor_warning", "code": "WARN"}]

    proposal = await reviser.check_and_propose_revision(
        skill_id=created["skill_id"],
        run_id="run-001",
        execution_result=_make_execution_result(),
        critic_final=critic,
    )

    assert proposal is not None
    assert "minor_warning" in proposal.reason


# ==================== 3. apply_revision: revision_history 追加, steps 更新 ====================


@pytest.mark.asyncio
async def test_apply_revision_updates_skill():
    """apply_revision → revision_history 追加, steps 和 failure_boundary 更新."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    reviser = SkillReviser(store)

    proposal = await reviser.check_and_propose_revision(
        skill_id=created["skill_id"],
        run_id="run-001",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_fail(),
    )
    assert proposal is not None

    updated = await reviser.apply_revision(
        skill_id=created["skill_id"],
        proposal=proposal,
    )

    # revision_history 追加
    assert len(updated["revision_history"]) == 1
    rev_entry = updated["revision_history"][0]
    assert rev_entry["revision_id"] == proposal.revision_id
    assert rev_entry["reason"] == proposal.reason
    assert rev_entry["proposed_by"] == "critic"

    # steps 更新
    assert updated["steps"] != created["steps"]
    assert len(updated["steps"]) == len(proposal.revised_steps)

    # failure_boundary 更新
    assert updated["failure_boundary"] != created["failure_boundary"]

    # write_origin 标记为 revision
    assert updated["write_origin"] == "revision"

    # updated_at 刷新
    assert updated["updated_at"] >= created["updated_at"]


@pytest.mark.asyncio
async def test_apply_revision_skill_not_found_raises():
    """apply_revision 对不存在的 skill_id → 抛出 KeyError."""
    from riskmonitor_multiagent.skills import RevisionProposal, SkillReviser, SkillStore

    store = SkillStore()
    reviser = SkillReviser(store)

    proposal = RevisionProposal(
        skill_id="skill_nonexistent",
        revision_id="rev_test123",
        reason="test",
        original_steps=[],
        revised_steps=[],
        original_failure_boundary="",
        revised_failure_boundary="",
        proposed_at=0,
        proposed_by="auto",
    )

    with pytest.raises(KeyError):
        await reviser.apply_revision(skill_id="skill_nonexistent", proposal=proposal)


# ==================== 4. ab_compare: revised 优于 original → passed=True ====================


@pytest.mark.asyncio
async def test_ab_compare_revised_better_than_original():
    """revised steps 优于 original → passed=True."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    reviser = SkillReviser(store)

    original_steps = created["steps"]
    # revised steps: 保留原有步骤 + 添加 failure_note + recovery 步骤
    revised_steps = [
        {**original_steps[0], "failure_note": "数据不完整"},
        {**original_steps[1], "failure_note": "限额遗漏"},
        {
            "description": "recovery: review failure and retry",
            "expected_outcome": "issue_resolved",
        },
    ]

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

    result = await reviser.ab_compare(
        skill_id=created["skill_id"],
        original_steps=original_steps,
        revised_steps=revised_steps,
        test_cases=test_cases,
    )

    assert result["passed"] is True
    assert result["revised_score"] > result["original_score"]
    assert len(result["case_results"]) == 2


# ==================== 5. ab_compare: revised 劣于 original → passed=False ====================


@pytest.mark.asyncio
async def test_ab_compare_revised_worse_than_original():
    """revised steps 劣于 original → passed=False."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    reviser = SkillReviser(store)

    original_steps = [
        {"description": "查询持仓数据", "expected_outcome": "获取当前持仓"},
        {"description": "核对限额", "expected_outcome": "确认是否超限"},
    ]
    # revised steps: 缺少 expected_outcome, 无 recovery
    revised_steps = [
        {"description": "查询持仓数据"},  # 缺少 expected_outcome
    ]

    test_cases = [
        {
            "expected_outcomes": ["获取当前持仓", "确认是否超限"],
            "expect_failure": False,
        },
        {
            "expected_outcomes": ["获取当前持仓", "确认是否超限"],
            "expect_failure": False,
        },
    ]

    result = await reviser.ab_compare(
        skill_id=created["skill_id"],
        original_steps=original_steps,
        revised_steps=revised_steps,
        test_cases=test_cases,
    )

    assert result["passed"] is False
    assert result["revised_score"] < result["original_score"]


@pytest.mark.asyncio
async def test_ab_compare_empty_test_cases():
    """空 test_cases → passed=True (revised_score >= original_score, 均为 0)."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    reviser = SkillReviser(store)

    result = await reviser.ab_compare(
        skill_id=created["skill_id"],
        original_steps=created["steps"],
        revised_steps=created["steps"],
        test_cases=[],
    )

    assert result["original_score"] == 0.0
    assert result["revised_score"] == 0.0
    assert result["passed"] is True
    assert result["case_results"] == []


# ==================== 6. _extract_failure_reason: 从 issues 提取 ====================


def test_extract_failure_reason_from_issues():
    """从 critic issues 列表提取失败原因."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    reviser = SkillReviser(SkillStore())

    critic_final = {
        "ok": False,
        "issues": [
            {"message": "数据不完整", "code": "INCOMPLETE"},
            {"message": "限额错误", "code": "LIMIT_ERR"},
            {"message": "超时", "code": "TIMEOUT"},
        ],
    }

    reason = reviser._extract_failure_reason(critic_final)
    assert "数据不完整" in reason
    assert "限额错误" in reason
    assert "超时" in reason


def test_extract_failure_reason_from_issues_string():
    """issues 为字符串列表时也能提取."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    reviser = SkillReviser(SkillStore())

    critic_final = {
        "ok": False,
        "issues": ["步骤1失败", "步骤2超时"],
    }

    reason = reviser._extract_failure_reason(critic_final)
    assert "步骤1失败" in reason
    assert "步骤2超时" in reason


def test_extract_failure_reason_from_risk_level():
    """无 issues 时从 risk_level 提取."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    reviser = SkillReviser(SkillStore())

    critic_final = {
        "ok": False,
        "issues": [],
        "risk_level": "HIGH",
    }

    reason = reviser._extract_failure_reason(critic_final)
    assert "HIGH" in reason


def test_extract_failure_reason_fallback():
    """无 issues 和 risk_level 时回退到默认."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    reviser = SkillReviser(SkillStore())

    critic_final = {"ok": False}

    reason = reviser._extract_failure_reason(critic_final)
    assert reason == "execution_suboptimal"


def test_extract_failure_reason_from_summary():
    """有 summary 时作为回退."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    reviser = SkillReviser(SkillStore())

    critic_final = {
        "ok": False,
        "issues": [],
        "summary": "执行结果不达标, 需要重新排查",
    }

    reason = reviser._extract_failure_reason(critic_final)
    assert "执行结果不达标" in reason


# ==================== 7. _generate_revised_steps: 保留成功步骤, 添加 recovery ====================


def test_generate_revised_steps_preserves_successful_steps():
    """_generate_revised_steps 保留成功的步骤, 对失败步骤添加 failure_note."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    reviser = SkillReviser(SkillStore())

    original_steps = [
        {"description": "查询持仓数据", "expected_outcome": "获取当前持仓"},
        {"description": "核对限额", "expected_outcome": "确认是否超限"},
    ]
    execution_result = {
        "failed_steps": [
            {"description": "核对限额", "step_id": "s2"},
        ],
    }
    failure_reason = "限额核对遗漏"

    revised = reviser._generate_revised_steps(
        original_steps=original_steps,
        failure_reason=failure_reason,
        execution_result=execution_result,
    )

    # 保留原有步骤
    assert len(revised) == 3  # 2 original + 1 recovery

    # 成功步骤不添加 failure_note
    assert "failure_note" not in revised[0]

    # 失败步骤添加 failure_note
    assert "failure_note" in revised[1]
    assert revised[1]["failure_note"] == failure_reason

    # 最后一个是 recovery 步骤
    recovery_step = revised[-1]
    assert "recovery" in recovery_step["description"].lower()
    assert recovery_step["expected_outcome"] == "issue_resolved"


def test_generate_revised_steps_adds_recovery():
    """_generate_revised_steps 总是添加 recovery 步骤."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    reviser = SkillReviser(SkillStore())

    original_steps = [
        {"description": "step1", "expected_outcome": "outcome1"},
    ]
    execution_result = {"failed_steps": []}

    revised = reviser._generate_revised_steps(
        original_steps=original_steps,
        failure_reason="test_reason",
        execution_result=execution_result,
    )

    assert len(revised) == 2  # 1 original + 1 recovery
    assert "recovery" in revised[-1]["description"].lower()


def test_generate_revised_steps_empty_original():
    """original_steps 为空时仍添加 recovery 步骤."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    reviser = SkillReviser(SkillStore())

    revised = reviser._generate_revised_steps(
        original_steps=[],
        failure_reason="test",
        execution_result={},
    )

    assert len(revised) == 1
    assert "recovery" in revised[0]["description"].lower()


def test_generate_revised_steps_from_receipts():
    """从 receipts 中提取失败步骤."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    reviser = SkillReviser(SkillStore())

    original_steps = [
        {"description": "step_a", "expected_outcome": "a_done"},
        {"description": "step_b", "expected_outcome": "b_done"},
    ]
    execution_result = {
        "receipts": [
            {"step_id": "step_a", "status": "ok"},
            {"step_id": "step_b", "status": "failed"},
        ],
    }

    revised = reviser._generate_revised_steps(
        original_steps=original_steps,
        failure_reason="receipt_failure",
        execution_result=execution_result,
    )

    # step_b should have failure_note
    assert "failure_note" in revised[1]
    assert revised[1]["failure_note"] == "receipt_failure"
    # step_a should NOT have failure_note
    assert "failure_note" not in revised[0]


# ==================== 8. 多次修订: revision_history 累积 ====================


@pytest.mark.asyncio
async def test_multiple_revisions_accumulate_history():
    """连续多次修订 → revision_history 累积."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    reviser = SkillReviser(store)

    for i in range(3):
        proposal = await reviser.check_and_propose_revision(
            skill_id=created["skill_id"],
            run_id=f"run-{i:03d}",
            execution_result=_make_execution_result(),
            critic_final=_make_critic_fail(),
        )
        assert proposal is not None
        await reviser.apply_revision(
            skill_id=created["skill_id"],
            proposal=proposal,
        )

    stored = await store.get(created["skill_id"])
    assert len(stored["revision_history"]) == 3

    # 每个 revision_entry 都有不同的 revision_id
    rev_ids = [r["revision_id"] for r in stored["revision_history"]]
    assert len(set(rev_ids)) == 3

    # steps 经过多次修订后包含多次 recovery
    steps = stored["steps"]
    recovery_count = sum(
        1 for s in steps if "recovery" in str(s.get("description", "")).lower()
    )
    assert recovery_count >= 1


# ==================== 额外: A/B 对比集成到 check_and_propose ====================


@pytest.mark.asyncio
async def test_ab_compare_after_proposal():
    """先提议修订, 再做 A/B 对比, 验证 revised 不劣于 original."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    reviser = SkillReviser(store)

    proposal = await reviser.check_and_propose_revision(
        skill_id=created["skill_id"],
        run_id="run-001",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_fail(),
    )
    assert proposal is not None

    test_cases = [
        {
            "expected_outcomes": ["获取当前持仓", "确认是否超限", "issue_resolved"],
            "expect_failure": True,
        },
    ]

    ab_result = await reviser.ab_compare(
        skill_id=created["skill_id"],
        original_steps=proposal.original_steps,
        revised_steps=proposal.revised_steps,
        test_cases=test_cases,
    )

    assert ab_result["passed"] is True
    assert ab_result["revised_score"] >= ab_result["original_score"]


# ==================== 额外: proposed_by 判断 ====================


@pytest.mark.asyncio
async def test_proposed_by_auto_when_ok_but_has_issues():
    """critic ok=True 但有 issues → proposed_by='auto' (非 critic 触发)."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    reviser = SkillReviser(store)

    critic = _make_critic_ok()
    critic["issues"] = [{"message": "warning", "code": "WARN"}]

    proposal = await reviser.check_and_propose_revision(
        skill_id=created["skill_id"],
        run_id="run-001",
        execution_result=_make_execution_result(),
        critic_final=critic,
    )

    assert proposal is not None
    assert proposal.proposed_by == "auto"


@pytest.mark.asyncio
async def test_proposed_by_critic_when_not_ok():
    """critic ok=False → proposed_by='critic'."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    reviser = SkillReviser(store)

    proposal = await reviser.check_and_propose_revision(
        skill_id=created["skill_id"],
        run_id="run-001",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_fail(),
    )

    assert proposal is not None
    assert proposal.proposed_by == "critic"


# ==================== 额外: _generate_revised_failure_boundary ====================


def test_generate_revised_failure_boundary_appends():
    """failure_boundary 追加新的失败原因."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    reviser = SkillReviser(SkillStore())

    result = reviser._generate_revised_failure_boundary(
        original_failure_boundary="禁止伪造数据",
        failure_reason="数据不完整",
    )
    assert "禁止伪造数据" in result
    assert "数据不完整" in result


def test_generate_revised_failure_boundary_empty_original():
    """原 failure_boundary 为空时直接使用 failure_reason."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    reviser = SkillReviser(SkillStore())

    result = reviser._generate_revised_failure_boundary(
        original_failure_boundary="",
        failure_reason="数据不完整",
    )
    assert result == "数据不完整"


def test_generate_revised_failure_boundary_duplicate():
    """failure_reason 已在 original 中时不重复添加."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    reviser = SkillReviser(SkillStore())

    result = reviser._generate_revised_failure_boundary(
        original_failure_boundary="数据不完整; 禁止伪造",
        failure_reason="数据不完整",
    )
    assert result == "数据不完整; 禁止伪造"


# ==================== 额外: revision_history 可回滚 ====================


@pytest.mark.asyncio
async def test_revision_history_can_rollback():
    """apply_revision 后可以通过 revision_history 回滚到原始 steps."""
    from riskmonitor_multiagent.skills import SkillReviser, SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    original_steps = list(created["steps"])
    original_fb = created["failure_boundary"]

    reviser = SkillReviser(store)

    proposal = await reviser.check_and_propose_revision(
        skill_id=created["skill_id"],
        run_id="run-001",
        execution_result=_make_execution_result(),
        critic_final=_make_critic_fail(),
    )
    await reviser.apply_revision(skill_id=created["skill_id"], proposal=proposal)

    # 验证已修改
    modified = await store.get(created["skill_id"])
    assert modified["steps"] != original_steps

    # 回滚: 用 revision_history 中的 original_steps 恢复
    rev_entry = modified["revision_history"][0]
    await store.update(created["skill_id"], {
        "steps": rev_entry["original_steps"],
        "failure_boundary": rev_entry["original_failure_boundary"],
    })

    rolled_back = await store.get(created["skill_id"])
    assert rolled_back["steps"] == original_steps
    assert rolled_back["failure_boundary"] == original_fb
