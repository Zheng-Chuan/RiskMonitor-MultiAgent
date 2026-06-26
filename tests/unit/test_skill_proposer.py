"""SkillProposer 单测."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


# ==================== 测试数据构造 ====================


def _make_task(**kwargs) -> dict:
    """构造测试用 task."""
    base = {
        "task_id": "task-001",
        "intent": "query_positions",
        "content": {
            "category": "risk",
            "description": "查询交易台持仓并核对限额",
        },
    }
    base.update(kwargs)
    return base


def _make_critic_final(**kwargs) -> dict:
    """构造测试用 critic_final."""
    base = {
        "ok": True,
        "confidence": 0.9,
        "risk_level": "LOW",
        "issues": [],
        "run_summary": {
            "text": "执行后审查完成",
            "key_points": ["receipt_count=2", "blocked_count=0"],
        },
    }
    base.update(kwargs)
    return base


def _make_orchestrator_output(**kwargs) -> dict:
    """构造测试用 orchestrator_output."""
    base = {
        "schema_version": "orchestrator_output.v1",
        "intent": {"type": "query_positions", "confidence": 0.95, "slots": {}},
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
    base.update(kwargs)
    return base


def _make_receipts() -> list[dict]:
    """构造测试用 receipts."""
    return [
        {"command_id": "cmd-001", "status": "completed", "result": {"data": "ok"}},
        {"command_id": "cmd-002", "status": "completed", "result": {"data": "ok"}},
    ]


# ==================== 1. 高质量完成产生提案 ====================


@pytest.mark.asyncio
async def test_high_quality_produces_proposal():
    """confidence >= 0.85, ok=True -> 生成 Skill 提案 (action=created)."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store, confidence_threshold=0.85)

    result = await proposer.propose(
        run_id="run-001",
        task=_make_task(),
        critic_final=_make_critic_final(ok=True, confidence=0.9),
        orchestrator_output=_make_orchestrator_output(),
        receipts=_make_receipts(),
    )

    assert result["action"] == "created"
    assert result["skill_id"] is not None
    assert result["skill_id"].startswith("skill_")
    assert result["reason"] == "no_similar_skill_found"


# ==================== 2. 低质量不产生提案 ====================


@pytest.mark.asyncio
async def test_low_quality_skips_proposal():
    """confidence < 0.85, ok=False -> action=skipped."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store, confidence_threshold=0.85)

    result = await proposer.propose(
        run_id="run-002",
        task=_make_task(),
        critic_final=_make_critic_final(ok=False, confidence=0.4),
        orchestrator_output=_make_orchestrator_output(),
        receipts=_make_receipts(),
    )

    assert result["action"] == "skipped"
    assert result["skill_id"] is None
    assert "below threshold" in result["reason"]


@pytest.mark.asyncio
async def test_ok_false_with_high_confidence_still_skips():
    """ok=False 但 confidence 高 -> 仍然 skipped (ok 检查优先)."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store, confidence_threshold=0.85)

    result = await proposer.propose(
        run_id="run-003",
        task=_make_task(),
        critic_final=_make_critic_final(ok=False, confidence=0.95),
        orchestrator_output=_make_orchestrator_output(),
        receipts=_make_receipts(),
    )

    assert result["action"] == "skipped"


@pytest.mark.asyncio
async def test_confidence_defaults_when_missing():
    """critic_final 没有 confidence 字段时, ok=True 默认 0.9, ok=False 默认 0.4."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store, confidence_threshold=0.85)

    # ok=True, 无 confidence -> 默认 0.9 -> 应该创建
    result = await proposer.propose(
        run_id="run-004",
        task=_make_task(),
        critic_final={"ok": True, "risk_level": "LOW", "issues": []},
        orchestrator_output=_make_orchestrator_output(),
    )
    assert result["action"] == "created"

    # ok=False, 无 confidence -> 默认 0.4 -> 应该跳过
    result2 = await proposer.propose(
        run_id="run-005",
        task=_make_task(),
        critic_final={"ok": False, "risk_level": "HIGH", "issues": [{"code": "err"}]},
        orchestrator_output=_make_orchestrator_output(),
    )
    assert result2["action"] == "skipped"


# ==================== 3. 语义去重创建 ====================


@pytest.mark.asyncio
async def test_first_proposal_creates_skill():
    """首次创建 -> action=created."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    result = await proposer.propose(
        run_id="run-006",
        task=_make_task(),
        critic_final=_make_critic_final(),
        orchestrator_output=_make_orchestrator_output(),
        receipts=_make_receipts(),
    )

    assert result["action"] == "created"
    assert result["similarity_score"] == 0.0

    # 验证 Skill 确实存储了
    stored = await store.get(result["skill_id"])
    assert stored is not None
    assert stored["name"] == "query_positions"
    assert stored["source_run_id"] == "run-006"


# ==================== 4. 语义去重更新 ====================


@pytest.mark.asyncio
async def test_duplicate_proposal_updates_skill():
    """相似 Skill 已存在 -> action=updated."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    # 第一次创建
    first = await proposer.propose(
        run_id="run-007",
        task=_make_task(),
        critic_final=_make_critic_final(),
        orchestrator_output=_make_orchestrator_output(),
        receipts=_make_receipts(),
    )
    assert first["action"] == "created"
    original_skill_id = first["skill_id"]

    # 第二次相同模式 -> 应更新
    second = await proposer.propose(
        run_id="run-008",
        task=_make_task(),
        critic_final=_make_critic_final(),
        orchestrator_output=_make_orchestrator_output(),
        receipts=_make_receipts(),
    )
    assert second["action"] == "updated"
    assert second["skill_id"] == original_skill_id
    assert second["similarity_score"] >= 0.85

    # 验证 usage_count 未变 (更新不改 usage_count)
    stored = await store.get(original_skill_id)
    assert stored["usage_count"] == 0
    # 验证 revision_history 被更新
    assert len(stored["revision_history"]) >= 1
    assert stored["revision_history"][-1]["action"] == "updated"
    assert stored["revision_history"][-1]["run_id"] == "run-008"


# ==================== 5. Skill 提案内容正确性 ====================


@pytest.mark.asyncio
async def test_proposal_content_correctness():
    """检查 name, tags, steps, failure_boundary 等."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    result = await proposer.propose(
        run_id="run-009",
        task=_make_task(
            intent="analyze_risk_exposure",
            content={"category": "compliance", "description": "合规风险检查"},
        ),
        critic_final=_make_critic_final(
            risk_level="MEDIUM",
            issues=[{"code": "warn_001", "message": "轻微限额偏差"}],
        ),
        orchestrator_output=_make_orchestrator_output(),
        receipts=_make_receipts(),
    )

    assert result["action"] == "created"
    stored = await store.get(result["skill_id"])
    assert stored is not None

    # name: intent 前 50 字符
    assert stored["name"] == "analyze_risk_exposure"

    # tags: 从 content.category
    assert stored["tags"] == ["compliance"]

    # failure_boundary: 从 issues
    assert "轻微限额偏差" in stored["failure_boundary"]

    # confidence
    assert stored["confidence"] == 0.9

    # source_run_id
    assert stored["source_run_id"] == "run-009"

    # source_agent_id
    assert stored["source_agent_id"] == "skill_proposer"


@pytest.mark.asyncio
async def test_proposal_name_truncation():
    """name 截断到 50 字符并去掉特殊字符."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    long_intent = "这是一个非常非常长的意图描述字符串用于测试名称截断功能是否正常工作" * 3

    result = await proposer.propose(
        run_id="run-010",
        task=_make_task(intent=long_intent),
        critic_final=_make_critic_final(),
        orchestrator_output=_make_orchestrator_output(),
    )

    assert result["action"] == "created"
    stored = await store.get(result["skill_id"])
    assert stored is not None
    # name 不超过 50 字符 (原始 intent 前 50 字符去特殊字符后)
    assert len(stored["name"]) <= 50
    assert len(stored["name"]) > 0


@pytest.mark.asyncio
async def test_proposal_tags_default_general():
    """没有 category 时 tags 默认 ["general"]."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    result = await proposer.propose(
        run_id="run-011",
        task={"task_id": "t1", "intent": "do_something"},
        critic_final=_make_critic_final(),
        orchestrator_output=_make_orchestrator_output(),
    )

    assert result["action"] == "created"
    stored = await store.get(result["skill_id"])
    assert stored["tags"] == ["general"]


# ==================== 6. 从 plan_steps 提取步骤 ====================


@pytest.mark.asyncio
async def test_steps_extracted_from_plan_steps():
    """验证 steps 列表正确生成."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    orchestrator = _make_orchestrator_output(
        plan_steps=[
            {
                "kind": "delegate",
                "step_id": "s1",
                "reason": "分析系统",
                "target_agent": "system_engineer",
                "instruction": "检查数据库连接",
            },
            {
                "kind": "tool_call",
                "step_id": "s2",
                "reason": "查询数据",
                "instruction": "执行SQL查询",
            },
            {
                "kind": "finalize",
                "step_id": "s3",
                "reason": "汇总结果",
                "instruction": "生成报告",
            },
        ]
    )

    result = await proposer.propose(
        run_id="run-012",
        task=_make_task(),
        critic_final=_make_critic_final(),
        orchestrator_output=orchestrator,
    )

    assert result["action"] == "created"
    stored = await store.get(result["skill_id"])
    assert stored is not None
    assert len(stored["steps"]) == 3

    # 第一步: instruction 作为 description
    assert stored["steps"][0]["description"] == "检查数据库连接"
    assert stored["steps"][0]["expected_outcome"] == "system_engineer"

    # 第二步
    assert stored["steps"][1]["description"] == "执行SQL查询"

    # 第三步
    assert stored["steps"][2]["description"] == "生成报告"


@pytest.mark.asyncio
async def test_steps_empty_plan_steps_fallback():
    """plan_steps 为空时使用默认步骤."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    result = await proposer.propose(
        run_id="run-013",
        task=_make_task(),
        critic_final=_make_critic_final(),
        orchestrator_output={"plan_steps": []},
    )

    assert result["action"] == "created"
    stored = await store.get(result["skill_id"])
    assert len(stored["steps"]) == 1
    assert stored["steps"][0]["description"] == "execute_task"


@pytest.mark.asyncio
async def test_steps_missing_plan_steps_fallback():
    """orchestrator_output 没有 plan_steps 时使用默认步骤."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    result = await proposer.propose(
        run_id="run-014",
        task=_make_task(),
        critic_final=_make_critic_final(),
        orchestrator_output={},
    )

    assert result["action"] == "created"
    stored = await store.get(result["skill_id"])
    assert len(stored["steps"]) == 1
    assert stored["steps"][0]["description"] == "execute_task"


# ==================== 7. 异常处理 ====================


@pytest.mark.asyncio
async def test_skill_store_failure_does_not_crash():
    """SkillStore 操作失败时不崩溃."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    # mock find_similar 抛出异常
    with patch.object(
        store, "find_similar", new_callable=AsyncMock, side_effect=RuntimeError("db error")
    ):
        result = await proposer.propose(
            run_id="run-015",
            task=_make_task(),
            critic_final=_make_critic_final(),
            orchestrator_output=_make_orchestrator_output(),
        )

    # find_similar 失败 -> 视为无相似 -> 创建新 Skill
    assert result["action"] == "created"
    assert result["skill_id"] is not None


@pytest.mark.asyncio
async def test_create_failure_returns_skipped():
    """skill_store.create 失败时返回 skipped."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    # mock create 抛出异常
    with patch.object(
        store, "create", new_callable=AsyncMock, side_effect=ValueError("validation error")
    ):
        result = await proposer.propose(
            run_id="run-016",
            task=_make_task(),
            critic_final=_make_critic_final(),
            orchestrator_output=_make_orchestrator_output(),
        )

    assert result["action"] == "skipped"
    assert "create_failed" in result["reason"]


@pytest.mark.asyncio
async def test_update_failure_returns_skipped():
    """skill_store.update 失败时返回 skipped."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    # 先创建一个 Skill
    first = await proposer.propose(
        run_id="run-017",
        task=_make_task(),
        critic_final=_make_critic_final(),
        orchestrator_output=_make_orchestrator_output(),
    )
    assert first["action"] == "created"

    # mock update 抛出异常
    with patch.object(
        store, "update", new_callable=AsyncMock, side_effect=KeyError("not found")
    ):
        result = await proposer.propose(
            run_id="run-018",
            task=_make_task(),
            critic_final=_make_critic_final(),
            orchestrator_output=_make_orchestrator_output(),
        )

    assert result["action"] == "skipped"
    assert "update_failed" in result["reason"]


# ==================== 额外: failure_boundary 推导 ====================


@pytest.mark.asyncio
async def test_failure_boundary_from_issues():
    """failure_boundary 从 issues 推导."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    result = await proposer.propose(
        run_id="run-019",
        task=_make_task(),
        critic_final=_make_critic_final(
            ok=True,
            confidence=0.9,
            issues=[
                {"code": "warn_001", "message": "限额偏差告警"},
                {"code": "warn_002", "message": "延迟略高"},
            ],
        ),
        orchestrator_output=_make_orchestrator_output(),
    )

    assert result["action"] == "created"
    stored = await store.get(result["skill_id"])
    assert "限额偏差告警" in stored["failure_boundary"]
    assert "延迟略高" in stored["failure_boundary"]


@pytest.mark.asyncio
async def test_failure_boundary_from_risk_level():
    """没有 issues 时 failure_boundary 从 risk_level 推导."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    result = await proposer.propose(
        run_id="run-020",
        task=_make_task(),
        critic_final=_make_critic_final(
            ok=True,
            confidence=0.9,
            risk_level="MEDIUM",
            issues=[],
        ),
        orchestrator_output=_make_orchestrator_output(),
    )

    assert result["action"] == "created"
    stored = await store.get(result["skill_id"])
    assert stored["failure_boundary"] == "risk_level=MEDIUM"


@pytest.mark.asyncio
async def test_failure_boundary_default():
    """没有 issues 和 risk_level 时使用默认值."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    result = await proposer.propose(
        run_id="run-021",
        task=_make_task(),
        critic_final={"ok": True, "confidence": 0.9},
        orchestrator_output=_make_orchestrator_output(),
    )

    assert result["action"] == "created"
    stored = await store.get(result["skill_id"])
    assert stored["failure_boundary"] == "no_known_failure_boundary"


# ==================== 额外: payload 风格 task 兼容 ====================


@pytest.mark.asyncio
async def test_payload_style_task():
    """兼容 payload.content 风格的 task."""
    from riskmonitor_multiagent.skills import SkillProposer, SkillStore

    store = SkillStore()
    proposer = SkillProposer(store)

    task = {
        "task_id": "task-payload",
        "payload": {
            "content": "查询交易台TRADER-001的持仓数据",
        },
    }

    result = await proposer.propose(
        run_id="run-022",
        task=task,
        critic_final=_make_critic_final(),
        orchestrator_output=_make_orchestrator_output(),
    )

    assert result["action"] == "created"
    stored = await store.get(result["skill_id"])
    # name 从 payload.content 提取
    assert "查询交易台" in stored["name"]
    # applicable_conditions 从 payload.content 提取
    assert any("查询交易台" in c for c in stored["applicable_conditions"])
