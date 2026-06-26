"""SessionSegmenter 单元测试.

测试场景:
1. should_segment 低于阈值不触发
2. should_segment 达到阈值触发
3. create_checkpoint 生成正确结构
4. parent_segment_id 链接
5. build_resume_context
6. get_segment_chain
7. summarize_segment
8. segment_index 递增
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


def _make_steps(count: int) -> list[dict[str, Any]]:
    """生成测试用步骤列表."""
    steps: list[dict[str, Any]] = []
    for i in range(count):
        steps.append({
            "step_id": f"step_{i:03d}",
            "kind": "delegate" if i % 2 == 0 else "tool_call",
            "status": "completed",
            "tool_name": f"risk_analyze_tool_{i}" if i % 2 == 1 else None,
            "target_agent": "risk_analyst" if i % 2 == 0 else "system_engineer",
        })
    return steps


# ---------------------------------------------------------------------------
# 1. should_segment 低于阈值不触发
# ---------------------------------------------------------------------------


class TestShouldSegmentBelowThreshold:
    """should_segment 在步数低于阈值时返回 False."""

    def test_zero_steps(self):
        """0步不触发."""
        segmenter = SessionSegmenter(max_steps_per_segment=10)
        assert segmenter.should_segment(0) is False

    def test_below_threshold(self):
        """步数低于阈值不触发."""
        segmenter = SessionSegmenter(max_steps_per_segment=10)
        assert segmenter.should_segment(5) is False

    def test_one_below_threshold(self):
        """差一步触发时不触发."""
        segmenter = SessionSegmenter(max_steps_per_segment=10)
        assert segmenter.should_segment(9) is False

    def test_custom_threshold(self):
        """自定义阈值."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        assert segmenter.should_segment(4) is False
        assert segmenter.should_segment(3) is False
        assert segmenter.should_segment(1) is False


# ---------------------------------------------------------------------------
# 2. should_segment 达到阈值触发
# ---------------------------------------------------------------------------


class TestShouldSegmentAtThreshold:
    """should_segment 在步数达到阈值时返回 True."""

    def test_at_threshold(self):
        """恰好达到阈值触发."""
        segmenter = SessionSegmenter(max_steps_per_segment=10)
        assert segmenter.should_segment(10) is True

    def test_above_threshold(self):
        """超过阈值触发."""
        segmenter = SessionSegmenter(max_steps_per_segment=10)
        assert segmenter.should_segment(15) is True
        assert segmenter.should_segment(100) is True

    def test_custom_threshold_trigger(self):
        """自定义阈值触发."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        assert segmenter.should_segment(5) is True
        assert segmenter.should_segment(8) is True

    def test_default_threshold(self):
        """默认阈值 10."""
        segmenter = SessionSegmenter()
        assert segmenter.max_steps_per_segment == 10
        assert segmenter.should_segment(9) is False
        assert segmenter.should_segment(10) is True


# ---------------------------------------------------------------------------
# 3. create_checkpoint 生成正确结构
# ---------------------------------------------------------------------------


class TestCreateCheckpoint:
    """create_checkpoint 生成正确结构."""

    @pytest.mark.asyncio
    async def test_checkpoint_basic_fields(self):
        """检查 checkpoint 基本字段."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        steps = _make_steps(5)
        checkpoint = await segmenter.create_checkpoint(
            run_id="run_001",
            step_count=5,
            steps=steps,
            parent_segment_id=None,
            context={"intent": {"type": "risk_analysis"}, "task": {"task_id": "t1"}},
        )

        assert isinstance(checkpoint, SegmentCheckpoint)
        assert checkpoint.segment_id.startswith("seg_")
        assert checkpoint.run_id == "run_001"
        assert checkpoint.parent_segment_id is None
        assert checkpoint.segment_index == 0
        assert checkpoint.step_count == 5
        assert isinstance(checkpoint.summary, str)
        assert len(checkpoint.summary) > 0
        assert isinstance(checkpoint.created_at, int)
        assert checkpoint.created_at > 0

    @pytest.mark.asyncio
    async def test_checkpoint_start_end_step_id(self):
        """检查 start_step_id 和 end_step_id."""
        segmenter = SessionSegmenter(max_steps_per_segment=3)
        steps = _make_steps(3)
        checkpoint = await segmenter.create_checkpoint(
            run_id="run_002",
            step_count=3,
            steps=steps,
        )

        assert checkpoint.start_step_id == "step_000"
        assert checkpoint.end_step_id == "step_002"

    @pytest.mark.asyncio
    async def test_checkpoint_context_snapshot(self):
        """检查 context_snapshot."""
        segmenter = SessionSegmenter(max_steps_per_segment=2)
        context = {
            "intent": {"primary_intent_type": "risk_analysis"},
            "task": {"task_id": "t_abc", "content": "analyze risk"},
        }
        checkpoint = await segmenter.create_checkpoint(
            run_id="run_003",
            step_count=2,
            steps=_make_steps(2),
            context=context,
        )

        assert checkpoint.context_snapshot == context
        # 修改原 context 不影响 checkpoint 的快照（浅拷贝）
        context["task"]["task_id"] = "modified"
        assert checkpoint.context_snapshot["task"]["task_id"] == "t_abc"

    @pytest.mark.asyncio
    async def test_checkpoint_empty_context(self):
        """context 为 None 时 context_snapshot 为空 dict."""
        segmenter = SessionSegmenter(max_steps_per_segment=1)
        checkpoint = await segmenter.create_checkpoint(
            run_id="run_004",
            step_count=1,
            steps=_make_steps(1),
            context=None,
        )
        assert checkpoint.context_snapshot == {}

    @pytest.mark.asyncio
    async def test_checkpoint_empty_steps(self):
        """空步骤列表也能创建 checkpoint."""
        segmenter = SessionSegmenter(max_steps_per_segment=1)
        checkpoint = await segmenter.create_checkpoint(
            run_id="run_005",
            step_count=0,
            steps=[],
        )
        assert checkpoint.start_step_id is None
        assert checkpoint.end_step_id is None
        assert "空分段" in checkpoint.summary

    @pytest.mark.asyncio
    async def test_segment_id_unique(self):
        """每次创建的 segment_id 唯一."""
        segmenter = SessionSegmenter(max_steps_per_segment=1)
        ids = set()
        for i in range(10):
            cp = await segmenter.create_checkpoint(
                run_id="run_006",
                step_count=1,
                steps=_make_steps(1),
            )
            ids.add(cp.segment_id)
        assert len(ids) == 10


# ---------------------------------------------------------------------------
# 4. parent_segment_id 链接
# ---------------------------------------------------------------------------


class TestParentSegmentLink:
    """parent_segment_id 链接测试."""

    @pytest.mark.asyncio
    async def test_first_segment_no_parent(self):
        """第一段 parent_segment_id 为 None."""
        segmenter = SessionSegmenter(max_steps_per_segment=3)
        checkpoint = await segmenter.create_checkpoint(
            run_id="run_link_001",
            step_count=3,
            steps=_make_steps(3),
            parent_segment_id=None,
        )
        assert checkpoint.parent_segment_id is None

    @pytest.mark.asyncio
    async def test_chain_links_correct(self):
        """连续分段 parent 链正确."""
        segmenter = SessionSegmenter(max_steps_per_segment=3)
        parent_id: str | None = None
        checkpoints: list[SegmentCheckpoint] = []

        for i in range(3):
            cp = await segmenter.create_checkpoint(
                run_id="run_link_002",
                step_count=3,
                steps=_make_steps(3),
                parent_segment_id=parent_id,
            )
            checkpoints.append(cp)
            parent_id = cp.segment_id

        # 第一段 parent 为 None
        assert checkpoints[0].parent_segment_id is None
        # 第二段 parent 为第一段 id
        assert checkpoints[1].parent_segment_id == checkpoints[0].segment_id
        # 第三段 parent 为第二段 id
        assert checkpoints[2].parent_segment_id == checkpoints[1].segment_id


# ---------------------------------------------------------------------------
# 5. build_resume_context
# ---------------------------------------------------------------------------


class TestBuildResumeContext:
    """build_resume_context 测试."""

    @pytest.mark.asyncio
    async def test_resume_context_contains_summary(self):
        """恢复上下文包含 summary."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        checkpoint = await segmenter.create_checkpoint(
            run_id="run_resume_001",
            step_count=5,
            steps=_make_steps(5),
            context={"intent": {"type": "analysis"}},
        )
        ctx = segmenter.build_resume_context(checkpoint)

        assert "summary" in ctx
        assert ctx["summary"] == checkpoint.summary
        assert isinstance(ctx["summary"], str)
        assert len(ctx["summary"]) > 0

    @pytest.mark.asyncio
    async def test_resume_context_contains_parent_info(self):
        """恢复上下文包含 parent_segment_id."""
        segmenter = SessionSegmenter(max_steps_per_segment=3)

        cp1 = await segmenter.create_checkpoint(
            run_id="run_resume_002",
            step_count=3,
            steps=_make_steps(3),
            parent_segment_id=None,
        )
        cp2 = await segmenter.create_checkpoint(
            run_id="run_resume_002",
            step_count=3,
            steps=_make_steps(3),
            parent_segment_id=cp1.segment_id,
        )

        ctx2 = segmenter.build_resume_context(cp2)
        assert ctx2["parent_segment_id"] == cp1.segment_id
        assert ctx2["segment_index"] == 1

    @pytest.mark.asyncio
    async def test_resume_context_contains_segment_index(self):
        """恢复上下文包含 segment_index."""
        segmenter = SessionSegmenter(max_steps_per_segment=2)
        cp = await segmenter.create_checkpoint(
            run_id="run_resume_003",
            step_count=2,
            steps=_make_steps(2),
        )
        ctx = segmenter.build_resume_context(cp)
        assert ctx["segment_index"] == 0

    @pytest.mark.asyncio
    async def test_resume_context_contains_step_ids(self):
        """恢复上下文包含 start/end step_id."""
        segmenter = SessionSegmenter(max_steps_per_segment=3)
        cp = await segmenter.create_checkpoint(
            run_id="run_resume_004",
            step_count=3,
            steps=_make_steps(3),
        )
        ctx = segmenter.build_resume_context(cp)
        assert ctx["start_step_id"] == "step_000"
        assert ctx["end_step_id"] == "step_002"

    @pytest.mark.asyncio
    async def test_resume_context_contains_context_snapshot(self):
        """恢复上下文包含 context_snapshot."""
        segmenter = SessionSegmenter(max_steps_per_segment=2)
        context = {"intent": "test", "task_id": "t1"}
        cp = await segmenter.create_checkpoint(
            run_id="run_resume_005",
            step_count=2,
            steps=_make_steps(2),
            context=context,
        )
        ctx = segmenter.build_resume_context(cp)
        assert ctx["context_snapshot"] == context

    @pytest.mark.asyncio
    async def test_resume_context_modification_isolated(self):
        """修改恢复上下文不影响原始 checkpoint."""
        segmenter = SessionSegmenter(max_steps_per_segment=2)
        cp = await segmenter.create_checkpoint(
            run_id="run_resume_006",
            step_count=2,
            steps=_make_steps(2),
            context={"key": "value"},
        )
        ctx = segmenter.build_resume_context(cp)
        ctx["context_snapshot"]["key"] = "modified"
        # 原始 checkpoint 不受影响
        assert cp.context_snapshot["key"] == "value"


# ---------------------------------------------------------------------------
# 6. get_segment_chain
# ---------------------------------------------------------------------------


class TestGetSegmentChain:
    """get_segment_chain 测试."""

    @pytest.mark.asyncio
    async def test_empty_run_returns_empty_list(self):
        """无分段的 run 返回空列表."""
        segmenter = SessionSegmenter(max_steps_per_segment=10)
        chain = segmenter.get_segment_chain("nonexistent_run")
        assert chain == []

    @pytest.mark.asyncio
    async def test_single_segment(self):
        """单段返回长度为 1 的列表."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        await segmenter.create_checkpoint(
            run_id="run_chain_001",
            step_count=5,
            steps=_make_steps(5),
        )
        chain = segmenter.get_segment_chain("run_chain_001")
        assert len(chain) == 1
        assert chain[0].segment_index == 0

    @pytest.mark.asyncio
    async def test_multiple_segments_ordered_by_index(self):
        """多段按 segment_index 排序返回."""
        segmenter = SessionSegmenter(max_steps_per_segment=3)
        parent_id: str | None = None
        for i in range(4):
            cp = await segmenter.create_checkpoint(
                run_id="run_chain_002",
                step_count=3,
                steps=_make_steps(3),
                parent_segment_id=parent_id,
            )
            parent_id = cp.segment_id

        chain = segmenter.get_segment_chain("run_chain_002")
        assert len(chain) == 4
        for i, cp in enumerate(chain):
            assert cp.segment_index == i

    @pytest.mark.asyncio
    async def test_different_runs_isolated(self):
        """不同 run 的分段链互相隔离."""
        segmenter = SessionSegmenter(max_steps_per_segment=2)
        await segmenter.create_checkpoint(
            run_id="run_a",
            step_count=2,
            steps=_make_steps(2),
        )
        await segmenter.create_checkpoint(
            run_id="run_b",
            step_count=2,
            steps=_make_steps(2),
        )

        chain_a = segmenter.get_segment_chain("run_a")
        chain_b = segmenter.get_segment_chain("run_b")
        assert len(chain_a) == 1
        assert len(chain_b) == 1
        assert chain_a[0].run_id == "run_a"
        assert chain_b[0].run_id == "run_b"


# ---------------------------------------------------------------------------
# 7. summarize_segment
# ---------------------------------------------------------------------------


class TestSummarizeSegment:
    """summarize_segment 测试."""

    @pytest.mark.asyncio
    async def test_non_empty_summary(self):
        """步骤列表生成非空摘要."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        steps = _make_steps(5)
        summary = await segmenter.summarize_segment(steps)

        assert isinstance(summary, str)
        assert len(summary) > 0
        # 摘要应包含 step_id
        assert "step_000" in summary

    @pytest.mark.asyncio
    async def test_empty_steps_summary(self):
        """空步骤列表生成空分段提示."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        summary = await segmenter.summarize_segment([])
        assert "空分段" in summary

    @pytest.mark.asyncio
    async def test_summary_contains_step_info(self):
        """摘要包含步骤关键信息."""
        segmenter = SessionSegmenter(max_steps_per_segment=3)
        steps = [
            {
                "step_id": "analyze_risk",
                "kind": "delegate",
                "status": "completed",
                "target_agent": "risk_analyst",
                "tool_name": None,
            },
            {
                "step_id": "query_data",
                "kind": "tool_call",
                "status": "completed",
                "tool_name": "query_db",
                "target_agent": "system_engineer",
            },
        ]
        summary = await segmenter.summarize_segment(steps)

        assert "analyze_risk" in summary
        assert "delegate" in summary
        assert "query_data" in summary
        assert "tool_call" in summary
        assert "query_db" in summary

    @pytest.mark.asyncio
    async def test_summary_truncates_long_step_list(self):
        """步骤过多时摘要截断."""
        segmenter = SessionSegmenter(max_steps_per_segment=50)
        steps = _make_steps(50)
        summary = await segmenter.summarize_segment(steps)

        # 摘要应包含总数提示
        assert "50" in summary
        assert "步" in summary

    @pytest.mark.asyncio
    async def test_summary_no_llm_dependency(self):
        """摘要不依赖 LLM（纯字符串拼接）."""
        segmenter = SessionSegmenter(max_steps_per_segment=3)
        steps = _make_steps(3)
        summary = await segmenter.summarize_segment(steps)

        # 摘要是纯文本, 不包含 LLM 调用痕迹
        assert isinstance(summary, str)
        assert "[" in summary  # 使用 [...] 格式


# ---------------------------------------------------------------------------
# 8. segment_index 递增
# ---------------------------------------------------------------------------


class TestSegmentIndexIncrement:
    """segment_index 递增测试."""

    @pytest.mark.asyncio
    async def test_index_starts_from_zero(self):
        """第一段 index 为 0."""
        segmenter = SessionSegmenter(max_steps_per_segment=5)
        cp = await segmenter.create_checkpoint(
            run_id="run_idx_001",
            step_count=5,
            steps=_make_steps(5),
        )
        assert cp.segment_index == 0

    @pytest.mark.asyncio
    async def test_index_increments(self):
        """多次分段 index 从 0 递增."""
        segmenter = SessionSegmenter(max_steps_per_segment=3)
        indices: list[int] = []
        for i in range(5):
            cp = await segmenter.create_checkpoint(
                run_id="run_idx_002",
                step_count=3,
                steps=_make_steps(3),
            )
            indices.append(cp.segment_index)

        assert indices == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_index_independent_per_run(self):
        """不同 run 的 index 独立计数."""
        segmenter = SessionSegmenter(max_steps_per_segment=2)

        cp_a1 = await segmenter.create_checkpoint(
            run_id="run_a",
            step_count=2,
            steps=_make_steps(2),
        )
        cp_b1 = await segmenter.create_checkpoint(
            run_id="run_b",
            step_count=2,
            steps=_make_steps(2),
        )
        cp_a2 = await segmenter.create_checkpoint(
            run_id="run_a",
            step_count=2,
            steps=_make_steps(2),
        )

        assert cp_a1.segment_index == 0
        assert cp_b1.segment_index == 0
        assert cp_a2.segment_index == 1


# ---------------------------------------------------------------------------
# 9. 异常隔离测试
# ---------------------------------------------------------------------------


class TestExceptionIsolation:
    """分段操作异常隔离测试."""

    @pytest.mark.asyncio
    async def test_create_checkpoint_with_malformed_steps(self):
        """畸形步骤数据不导致崩溃."""
        segmenter = SessionSegmenter(max_steps_per_segment=3)
        # 步骤缺少 step_id 等字段
        malformed_steps: list[dict[str, Any]] = [
            {"kind": "delegate"},
            {"status": "completed"},
            {},
        ]
        checkpoint = await segmenter.create_checkpoint(
            run_id="run_exc_001",
            step_count=3,
            steps=malformed_steps,
        )
        assert checkpoint is not None
        assert checkpoint.step_count == 3
        assert isinstance(checkpoint.summary, str)

    @pytest.mark.asyncio
    async def test_summarize_with_none_values(self):
        """步骤含 None 值不崩溃."""
        segmenter = SessionSegmenter(max_steps_per_segment=3)
        steps: list[dict[str, Any]] = [
            {"step_id": None, "kind": None, "status": None},
            {"step_id": "s1", "kind": "delegate", "status": "completed"},
        ]
        summary = await segmenter.summarize_segment(steps)
        assert isinstance(summary, str)
        assert len(summary) > 0
