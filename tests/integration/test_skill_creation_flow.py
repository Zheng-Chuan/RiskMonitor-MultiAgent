"""SkillProposer 端到端集成测试.

测试从 mock run 到 Skill 创建和去重更新的完整流程.
使用真实 SkillStore (内存存储), 不依赖外部 LLM.
"""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def _build_mock_run(
    *,
    run_id: str = "integration-run-001",
    intent: str = "query_risk_positions",
    category: str = "risk",
) -> dict:
    """构建高质量 mock run 的输入参数."""
    task = {
        "task_id": f"task-{run_id}",
        "intent": intent,
        "content": {
            "category": category,
            "description": f"查询并分析{category}相关持仓数据",
        },
    }
    orchestrator_output = {
        "schema_version": "orchestrator_output.v1",
        "intent": {"type": intent, "confidence": 0.95, "slots": {}},
        "plan_steps": [
            {
                "kind": "delegate",
                "step_id": "s1",
                "reason": "需要系统工程师分析技术层面",
                "target_agent": "system_engineer",
                "instruction": "分析系统层面可能原因",
            },
            {
                "kind": "delegate",
                "step_id": "s2",
                "reason": "需要风险分析师评估业务影响",
                "target_agent": "risk_analyst",
                "instruction": "评估业务层面影响",
            },
            {
                "kind": "finalize",
                "step_id": "s3",
                "reason": "综合双视角输出结论",
                "instruction": "基于分析做最终结论",
            },
        ],
        "commands": None,
        "evidence": {},
    }
    critic_final = {
        "ok": True,
        "confidence": 0.92,
        "risk_level": "LOW",
        "issues": [],
        "run_summary": {
            "text": "执行后审查完成",
            "key_points": ["receipt_count=2", "blocked_count=0"],
        },
    }
    receipts = [
        {"command_id": "cmd-001", "status": "completed", "result": {"data": "ok"}},
        {"command_id": "cmd-002", "status": "completed", "result": {"data": "ok"}},
    ]
    return {
        "run_id": run_id,
        "task": task,
        "orchestrator_output": orchestrator_output,
        "critic_final": critic_final,
        "receipts": receipts,
    }


# ==================== 端到端: 创建 -> 去重更新 ====================


@pytest.mark.asyncio
async def test_end_to_end_create_then_update():
    """端到端: 第一次创建 Skill, 第二次相同模式去重更新."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store, confidence_threshold=0.85)

    mock = _build_mock_run(run_id="integration-run-001")

    # 第一次: 应该创建
    result1 = await proposer.propose(
        run_id=mock["run_id"],
        task=mock["task"],
        critic_final=mock["critic_final"],
        orchestrator_output=mock["orchestrator_output"],
        receipts=mock["receipts"],
    )

    assert result1["action"] == "created"
    assert result1["skill_id"] is not None
    assert result1["skill_id"].startswith("skill_")
    assert result1["similarity_score"] == 0.0

    # 验证 Skill 确实存储到 SkillStore
    stored = await store.get(result1["skill_id"])
    assert stored is not None
    assert stored["name"] == "query_risk_positions"
    assert stored["tags"] == ["risk"]
    assert stored["confidence"] == pytest.approx(0.92)
    assert stored["source_run_id"] == "integration-run-001"
    assert stored["status"] == "active"
    assert len(stored["steps"]) == 3

    # 第二次相同模式: 应该更新 (去重)
    mock2 = _build_mock_run(run_id="integration-run-002")
    result2 = await proposer.propose(
        run_id=mock2["run_id"],
        task=mock2["task"],
        critic_final=mock2["critic_final"],
        orchestrator_output=mock2["orchestrator_output"],
        receipts=mock2["receipts"],
    )

    assert result2["action"] == "updated"
    assert result2["skill_id"] == result1["skill_id"]
    assert result2["similarity_score"] >= 0.85

    # 验证更新后的 Skill
    updated = await store.get(result2["skill_id"])
    assert updated is not None
    # usage_count 不变 (更新不改 usage_count)
    assert updated["usage_count"] == 0
    # source_run_id 更新为新的 run_id
    assert updated["source_run_id"] == "integration-run-002"
    # revision_history 有记录
    assert len(updated["revision_history"]) >= 1
    assert updated["revision_history"][-1]["run_id"] == "integration-run-002"


@pytest.mark.asyncio
async def test_end_to_end_different_patterns_create_separate():
    """不同模式创建不同的 Skill."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    # 第一个模式: 风险排查
    mock1 = _build_mock_run(
        run_id="integration-run-003",
        intent="query_risk_positions",
        category="risk",
    )
    result1 = await proposer.propose(
        run_id=mock1["run_id"],
        task=mock1["task"],
        critic_final=mock1["critic_final"],
        orchestrator_output=mock1["orchestrator_output"],
        receipts=mock1["receipts"],
    )
    assert result1["action"] == "created"

    # 第二个模式: 合规检查 (不同的 intent 和 category)
    mock2 = _build_mock_run(
        run_id="integration-run-004",
        intent="generate_compliance_report",
        category="compliance",
    )
    # 使用不同的 plan_steps 以降低语义相似度
    mock2["orchestrator_output"]["plan_steps"] = [
        {
            "kind": "delegate",
            "step_id": "s1",
            "reason": "收集审计数据",
            "target_agent": "risk_analyst",
            "instruction": "收集季度审计数据",
        },
        {
            "kind": "finalize",
            "step_id": "s2",
            "reason": "生成合规报告",
            "instruction": "生成合规报告并归档",
        },
    ]
    result2 = await proposer.propose(
        run_id=mock2["run_id"],
        task=mock2["task"],
        critic_final=mock2["critic_final"],
        orchestrator_output=mock2["orchestrator_output"],
        receipts=mock2["receipts"],
    )
    assert result2["action"] == "created"
    assert result2["skill_id"] != result1["skill_id"]

    # 验证两个 Skill 都存在
    all_skills = await store.list_all()
    assert len(all_skills) >= 2


@pytest.mark.asyncio
async def test_end_to_end_low_quality_skipped():
    """低质量 run 不创建 Skill."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    mock = _build_mock_run(run_id="integration-run-005")
    mock["critic_final"] = {
        "ok": False,
        "confidence": 0.3,
        "risk_level": "HIGH",
        "issues": [{"code": "blocked", "message": "命令被阻断"}],
    }

    result = await proposer.propose(
        run_id=mock["run_id"],
        task=mock["task"],
        critic_final=mock["critic_final"],
        orchestrator_output=mock["orchestrator_output"],
        receipts=mock["receipts"],
    )

    assert result["action"] == "skipped"
    assert result["skill_id"] is None

    # 验证没有创建 Skill
    all_skills = await store.list_all()
    assert len(all_skills) == 0


@pytest.mark.asyncio
async def test_end_to_end_multiple_updates_accumulate_revisions():
    """多次更新累积 revision_history."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    # 第一次创建
    mock1 = _build_mock_run(run_id="integration-run-006")
    result1 = await proposer.propose(
        run_id=mock1["run_id"],
        task=mock1["task"],
        critic_final=mock1["critic_final"],
        orchestrator_output=mock1["orchestrator_output"],
        receipts=mock1["receipts"],
    )
    assert result1["action"] == "created"

    # 第二次更新
    mock2 = _build_mock_run(run_id="integration-run-007")
    result2 = await proposer.propose(
        run_id=mock2["run_id"],
        task=mock2["task"],
        critic_final=mock2["critic_final"],
        orchestrator_output=mock2["orchestrator_output"],
        receipts=mock2["receipts"],
    )
    assert result2["action"] == "updated"

    # 第三次更新
    mock3 = _build_mock_run(run_id="integration-run-008")
    result3 = await proposer.propose(
        run_id=mock3["run_id"],
        task=mock3["task"],
        critic_final=mock3["critic_final"],
        orchestrator_output=mock3["orchestrator_output"],
        receipts=mock3["receipts"],
    )
    assert result3["action"] == "updated"

    # 验证 revision_history 有两条记录
    stored = await store.get(result1["skill_id"])
    assert stored is not None
    assert len(stored["revision_history"]) == 2
    assert stored["revision_history"][0]["run_id"] == "integration-run-007"
    assert stored["revision_history"][1]["run_id"] == "integration-run-008"
