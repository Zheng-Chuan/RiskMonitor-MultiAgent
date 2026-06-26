"""会话分段与链接集成测试.

测试场景:
1. 超长任务自动分段: 15步任务（max_steps=10）→ 产生 2 段
2. 分段不丢失上下文: 检查 checkpoint 的 context_snapshot
3. 从中间段恢复: build_resume_context → 包含前段摘要
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.memory.session_segmenter import (
    SegmentCheckpoint,
    SessionSegmenter,
)


def _make_execution_steps(count: int, *, run_id: str = "run_long_001") -> list[dict[str, Any]]:
    """生成模拟执行步骤记录."""
    steps: list[dict[str, Any]] = []
    for i in range(count):
        kind = "delegate" if i % 3 != 2 else "tool_call"
        steps.append({
            "step_id": f"{run_id}_step_{i:03d}",
            "kind": kind,
            "status": "completed",
            "tool_name": f"risk_query_tool" if kind == "tool_call" else None,
            "target_agent": "risk_analyst" if kind == "delegate" else "system_engineer",
        })
    return steps


async def _simulate_workflow_segmentation(
    *,
    segmenter: SessionSegmenter,
    run_id: str,
    total_steps: int,
    intent: dict[str, Any],
    task: dict[str, Any],
) -> list[SegmentCheckpoint]:
    """模拟工作流执行循环中的分段逻辑.

    每完成一个 step 后检查是否需要分段.
    """
    completed_step_records: list[dict[str, Any]] = []
    current_segment_id: str | None = None
    checkpoints: list[SegmentCheckpoint] = []

    for i in range(total_steps):
        # 模拟完成一个 step
        step = {
            "step_id": f"{run_id}_step_{i:03d}",
            "kind": "delegate" if i % 3 != 2 else "tool_call",
            "status": "completed",
            "tool_name": "risk_query_tool" if i % 3 == 2 else None,
            "target_agent": "risk_analyst" if i % 3 != 2 else "system_engineer",
        }
        completed_step_records.append(step)

        step_count = len(completed_step_records)
        if segmenter.should_segment(step_count):
            checkpoint = await segmenter.create_checkpoint(
                run_id=run_id,
                step_count=step_count,
                steps=list(completed_step_records),
                parent_segment_id=current_segment_id,
                context={"intent": intent, "task": task},
            )
            current_segment_id = checkpoint.segment_id
            checkpoints.append(checkpoint)
            # 清空已完成步骤记录, 开始新段
            completed_step_records.clear()

    # 循环结束后: 为剩余步骤创建最终检查点
    if completed_step_records:
        final_checkpoint = await segmenter.create_checkpoint(
            run_id=run_id,
            step_count=len(completed_step_records),
            steps=list(completed_step_records),
            parent_segment_id=current_segment_id,
            context={"intent": intent, "task": task},
        )
        checkpoints.append(final_checkpoint)

    return checkpoints


# ---------------------------------------------------------------------------
# 1. 超长任务自动分段
# ---------------------------------------------------------------------------


class TestLongTaskAutoSegmentation:
    """超长任务自动分段."""

    @pytest.mark.asyncio
    async def test_15_step_task_produces_2_segments(self):
        """15步任务（max_steps=10）→ 产生 2 段."""
        segmenter = SessionSegmenter(max_steps_per_segment=10)
        checkpoints = await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id="run_long_001",
            total_steps=15,
            intent={"primary_intent_type": "risk_analysis"},
            task={"task_id": "task_001", "content": "Analyze 15-step risk scenario"},
        )

        # 15步 / 10步每段 → 第10步触发段0(10步), 剩余5步创建最终段1(5步)
        assert len(checkpoints) == 2

    @pytest.mark.asyncio
    async def test_15_step_task_with_max_7_produces_3_segments(self):
        """15步任务（max_steps=7）→ 产生 3 段."""
        segmenter = SessionSegmenter(max_steps_per_segment=7)
        checkpoints = await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id="run_long_002",
            total_steps=15,
            intent={"primary_intent_type": "risk_analysis"},
            task={"task_id": "task_002", "content": "Analyze 15-step risk scenario"},
        )

        # 15步 / 7步每段 → 第7步触发段0, 第14步触发段1, 剩余1步创建最终段2
        assert len(checkpoints) == 3

    @pytest.mark.asyncio
    async def test_segment_indices_sequential(self):
        """分段 index 从 0 递增."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        checkpoints = await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id="run_long_003",
            total_steps=15,
            intent={"primary_intent_type": "risk_analysis"},
            task={"task_id": "task_003", "content": "Long task"},
        )

        for i, cp in enumerate(checkpoints):
            assert cp.segment_index == i

    @pytest.mark.asyncio
    async def test_segment_chain_via_parent_id(self):
        """分段通过 parent_segment_id 链接."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        checkpoints = await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id="run_long_004",
            total_steps=15,
            intent={"primary_intent_type": "risk_analysis"},
            task={"task_id": "task_004", "content": "Long task"},
        )

        # 第一段 parent 为 None
        assert checkpoints[0].parent_segment_id is None
        # 后续段的 parent 指向前一段
        for i in range(1, len(checkpoints)):
            assert checkpoints[i].parent_segment_id == checkpoints[i - 1].segment_id

    @pytest.mark.asyncio
    async def test_get_segment_chain_returns_all(self):
        """get_segment_chain 返回所有分段."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id="run_long_005",
            total_steps=20,
            intent={"primary_intent_type": "risk_analysis"},
            task={"task_id": "task_005", "content": "Long task"},
        )

        chain = segmenter.get_segment_chain("run_long_005")
        # 20步 / 5步每段 → 4段
        assert len(chain) == 4
        # 按 index 排序
        for i, cp in enumerate(chain):
            assert cp.segment_index == i

    @pytest.mark.asyncio
    async def test_each_segment_has_summary(self):
        """每段都有非空摘要."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        checkpoints = await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id="run_long_006",
            total_steps=15,
            intent={"primary_intent_type": "risk_analysis"},
            task={"task_id": "task_006", "content": "Long task"},
        )

        for cp in checkpoints:
            assert isinstance(cp.summary, str)
            assert len(cp.summary) > 0


# ---------------------------------------------------------------------------
# 2. 分段不丢失上下文
# ---------------------------------------------------------------------------


class TestContextPreservation:
    """分段不丢失上下文."""

    @pytest.mark.asyncio
    async def test_context_snapshot_contains_intent(self):
        """context_snapshot 包含 intent."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        intent = {"primary_intent_type": "risk_analysis", "severity": "high"}
        task = {"task_id": "task_ctx_001", "content": "Analyze risk"}

        checkpoints = await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id="run_ctx_001",
            total_steps=10,
            intent=intent,
            task=task,
        )

        for cp in checkpoints:
            assert "intent" in cp.context_snapshot
            assert cp.context_snapshot["intent"] == intent

    @pytest.mark.asyncio
    async def test_context_snapshot_contains_task(self):
        """context_snapshot 包含 task."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        intent = {"primary_intent_type": "risk_analysis"}
        task = {"task_id": "task_ctx_002", "content": "Deep risk analysis"}

        checkpoints = await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id="run_ctx_002",
            total_steps=10,
            intent=intent,
            task=task,
        )

        for cp in checkpoints:
            assert "task" in cp.context_snapshot
            assert cp.context_snapshot["task"] == task

    @pytest.mark.asyncio
    async def test_checkpoint_step_ids_correct(self):
        """每段的 start_step_id 和 end_step_id 正确."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        run_id = "run_ctx_003"
        checkpoints = await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id=run_id,
            total_steps=10,
            intent={"primary_intent_type": "risk_analysis"},
            task={"task_id": "task_ctx_003", "content": "Long task"},
        )

        # 第一段: step 0~4
        assert checkpoints[0].start_step_id == f"{run_id}_step_000"
        assert checkpoints[0].end_step_id == f"{run_id}_step_004"
        # 第二段: step 5~9
        assert checkpoints[1].start_step_id == f"{run_id}_step_005"
        assert checkpoints[1].end_step_id == f"{run_id}_step_009"

    @pytest.mark.asyncio
    async def test_context_snapshot_deep_copy(self):
        """context_snapshot 是深拷贝, 修改不影响."""
        segmenter = SessionSegmenter(max_steps_per_segment=3)
        intent = {"primary_intent_type": "risk_analysis"}
        task = {"task_id": "task_ctx_004", "content": "Analyze"}

        checkpoints = await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id="run_ctx_004",
            total_steps=3,
            intent=intent,
            task=task,
        )

        assert len(checkpoints) >= 1
        cp = checkpoints[0]
        # 修改原始数据
        intent["primary_intent_type"] = "modified"
        # checkpoint 中的快照不受影响（浅拷贝隔离）
        assert cp.context_snapshot["intent"]["primary_intent_type"] == "risk_analysis"


# ---------------------------------------------------------------------------
# 3. 从中间段恢复
# ---------------------------------------------------------------------------


class TestResumeFromMiddleSegment:
    """从中间段恢复."""

    @pytest.mark.asyncio
    async def test_resume_context_contains_summary(self):
        """从中间段恢复时, 恢复上下文包含前段摘要."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        checkpoints = await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id="run_resume_001",
            total_steps=15,
            intent={"primary_intent_type": "risk_analysis"},
            task={"task_id": "task_resume_001", "content": "Long task"},
        )

        # 从第二段恢复
        middle_checkpoint = checkpoints[1]
        resume_ctx = segmenter.build_resume_context(middle_checkpoint)

        assert "summary" in resume_ctx
        assert resume_ctx["summary"] == middle_checkpoint.summary
        assert len(resume_ctx["summary"]) > 0

    @pytest.mark.asyncio
    async def test_resume_context_contains_parent_link(self):
        """从中间段恢复时, 恢复上下文包含 parent_segment_id."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        checkpoints = await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id="run_resume_002",
            total_steps=15,
            intent={"primary_intent_type": "risk_analysis"},
            task={"task_id": "task_resume_002", "content": "Long task"},
        )

        middle_checkpoint = checkpoints[1]
        resume_ctx = segmenter.build_resume_context(middle_checkpoint)

        assert resume_ctx["parent_segment_id"] == checkpoints[0].segment_id
        assert resume_ctx["segment_index"] == 1

    @pytest.mark.asyncio
    async def test_resume_context_contains_segment_id(self):
        """从中间段恢复时, 恢复上下文包含 segment_id."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        checkpoints = await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id="run_resume_003",
            total_steps=10,
            intent={"primary_intent_type": "risk_analysis"},
            task={"task_id": "task_resume_003", "content": "Long task"},
        )

        cp = checkpoints[1]
        resume_ctx = segmenter.build_resume_context(cp)
        assert resume_ctx["segment_id"] == cp.segment_id

    @pytest.mark.asyncio
    async def test_resume_context_contains_context_snapshot(self):
        """从中间段恢复时, 恢复上下文包含 context_snapshot."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        intent = {"primary_intent_type": "risk_analysis", "severity": "high"}
        task = {"task_id": "task_resume_004", "content": "Resume test"}

        checkpoints = await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id="run_resume_004",
            total_steps=10,
            intent=intent,
            task=task,
        )

        cp = checkpoints[1]
        resume_ctx = segmenter.build_resume_context(cp)

        assert "context_snapshot" in resume_ctx
        assert resume_ctx["context_snapshot"]["intent"] == intent
        assert resume_ctx["context_snapshot"]["task"] == task

    @pytest.mark.asyncio
    async def test_full_resume_workflow(self):
        """完整的恢复流程: 获取链 → 选中间段 → 构建恢复上下文."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        run_id = "run_resume_full_001"
        await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id=run_id,
            total_steps=20,
            intent={"primary_intent_type": "risk_analysis"},
            task={"task_id": "task_full_001", "content": "Full resume test"},
        )

        # 1. 获取分段链
        chain = segmenter.get_segment_chain(run_id)
        assert len(chain) >= 3

        # 2. 选择中间段（第2段, index=1）
        middle = chain[1]
        assert middle.segment_index == 1

        # 3. 构建恢复上下文
        resume_ctx = segmenter.build_resume_context(middle)

        # 4. 验证恢复上下文完整性
        assert resume_ctx["segment_id"] == middle.segment_id
        assert resume_ctx["parent_segment_id"] == chain[0].segment_id
        assert resume_ctx["segment_index"] == 1
        assert isinstance(resume_ctx["summary"], str)
        assert len(resume_ctx["summary"]) > 0
        assert "intent" in resume_ctx["context_snapshot"]
        assert "task" in resume_ctx["context_snapshot"]
        assert resume_ctx["step_count"] == 5
        assert resume_ctx["start_step_id"] is not None
        assert resume_ctx["end_step_id"] is not None

    @pytest.mark.asyncio
    async def test_resume_from_first_segment(self):
        """从第一段恢复, parent 为 None."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        checkpoints = await _simulate_workflow_segmentation(
            segmenter=segmenter,
            run_id="run_resume_005",
            total_steps=10,
            intent={"primary_intent_type": "risk_analysis"},
            task={"task_id": "task_resume_005", "content": "Test"},
        )

        first = checkpoints[0]
        resume_ctx = segmenter.build_resume_context(first)

        assert resume_ctx["parent_segment_id"] is None
        assert resume_ctx["segment_index"] == 0
        assert len(resume_ctx["summary"]) > 0
