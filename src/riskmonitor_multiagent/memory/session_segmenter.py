"""
会话分段与链接.

长任务自动分段, 每段有 summary checkpoint.
新段通过 parent_segment_id 链接, 恢复时可从任意段的 checkpoint 继续.

设计约束:
1. 分段操作不影响主流程（异常隔离）
2. 摘要不依赖 LLM（使用截取关键步骤描述的方式）
3. 遵循现有代码风格
"""

from __future__ import annotations

import copy
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 每条步骤描述在摘要中的最大长度
_MAX_STEP_DESC_LEN = 120

# 摘要中最多包含的步骤数
_MAX_SUMMARY_STEPS = 5


@dataclass
class SegmentCheckpoint:
    """分段检查点."""

    segment_id: str  # "seg_" + uuid
    run_id: str
    parent_segment_id: str | None  # 前一段的 segment_id
    segment_index: int  # 第几段（0-based）
    summary: str  # 本段摘要
    step_count: int  # 本段步数
    start_step_id: str | None
    end_step_id: str | None
    created_at: int  # 毫秒时间戳
    context_snapshot: dict[str, Any] = field(default_factory=dict)  # 关键上下文快照（用于恢复）


class SessionSegmenter:
    """长任务自动分段, 每段有 summary checkpoint.

    在执行循环中, 每完成一个 step 后检查是否需要分段.
    达到 max_steps_per_segment 时创建检查点, 记录本段摘要和上下文快照.
    新段通过 parent_segment_id 链接, 恢复时可从任意段的 checkpoint 继续.
    """

    def __init__(self, *, max_steps_per_segment: int = 10) -> None:
        """初始化会话分段器.

        Args:
            max_steps_per_segment: 每段最大步数
        """
        self._max_steps_per_segment = max_steps_per_segment
        # 按 run_id 存储所有分段: {run_id: [SegmentCheckpoint, ...]}
        self._segments: dict[str, list[SegmentCheckpoint]] = {}

    @property
    def max_steps_per_segment(self) -> int:
        return self._max_steps_per_segment

    def should_segment(self, current_step_count: int) -> bool:
        """判断是否需要分段.

        current_step_count >= max_steps_per_segment 时触发.

        Args:
            current_step_count: 当前已完成的步数

        Returns:
            True 如果需要分段
        """
        return current_step_count >= self._max_steps_per_segment

    async def create_checkpoint(
        self,
        *,
        run_id: str,
        step_count: int,
        steps: list[dict[str, Any]],
        parent_segment_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> SegmentCheckpoint:
        """创建分段检查点.

        1. 生成 segment_id
        2. 从 steps 提取摘要（取关键步骤的 description）
        3. 记录 start/end step_id
        4. 保存 context 快照

        Args:
            run_id: 运行 ID
            step_count: 本段步数
            steps: 本段步骤列表
            parent_segment_id: 前一段的 segment_id
            context: 关键上下文快照

        Returns:
            SegmentCheckpoint 检查点
        """
        segment_id = f"seg_{uuid.uuid4().hex[:12]}"
        segments = self._segments.setdefault(run_id, [])
        segment_index = len(segments)

        summary = await self.summarize_segment(steps)

        start_step_id = self._extract_step_id(steps, first=True) if steps else None
        end_step_id = self._extract_step_id(steps, first=False) if steps else None

        context_snapshot = copy.deepcopy(context) if isinstance(context, dict) else {}

        checkpoint = SegmentCheckpoint(
            segment_id=segment_id,
            run_id=run_id,
            parent_segment_id=parent_segment_id,
            segment_index=segment_index,
            summary=summary,
            step_count=step_count,
            start_step_id=start_step_id,
            end_step_id=end_step_id,
            created_at=int(time.time() * 1000),
            context_snapshot=context_snapshot,
        )

        segments.append(checkpoint)
        logger.info(
            "Session segment created: run_id=%s segment=%d steps=%d summary_len=%d",
            run_id,
            segment_index,
            step_count,
            len(summary),
        )
        return checkpoint

    def build_resume_context(self, checkpoint: SegmentCheckpoint) -> dict[str, Any]:
        """从检查点构建恢复上下文.

        返回包含 summary, parent_segment_id, segment_index 的字典.

        Args:
            checkpoint: 分段检查点

        Returns:
            恢复上下文字典
        """
        return {
            "summary": checkpoint.summary,
            "parent_segment_id": checkpoint.parent_segment_id,
            "segment_index": checkpoint.segment_index,
            "segment_id": checkpoint.segment_id,
            "step_count": checkpoint.step_count,
            "start_step_id": checkpoint.start_step_id,
            "end_step_id": checkpoint.end_step_id,
            "context_snapshot": copy.deepcopy(checkpoint.context_snapshot),
        }

    def get_segment_chain(self, run_id: str) -> list[SegmentCheckpoint]:
        """获取某次 run 的所有分段链（按 segment_index 排序）.

        Args:
            run_id: 运行 ID

        Returns:
            按 segment_index 排序的检查点列表
        """
        segments = self._segments.get(run_id, [])
        return sorted(segments, key=lambda s: s.segment_index)

    async def summarize_segment(self, steps: list[dict[str, Any]]) -> str:
        """生成本段摘要. 截取关键步骤描述拼接, 不依赖 LLM.

        取每个步骤的 step_id, kind, status, tool_name 等关键信息拼接.
        最多包含 _MAX_SUMMARY_STEPS 个步骤, 每条描述截取前 _MAX_STEP_DESC_LEN 字符.

        Args:
            steps: 本段步骤列表

        Returns:
            摘要文本
        """
        if not steps:
            return "（空分段）"

        parts: list[str] = []
        # 选取关键步骤: 优先取 delegate/tool_call 类型, 不足时取全部
        key_steps = [s for s in steps if s.get("kind") in ("delegate", "tool_call")]
        if len(key_steps) < _MAX_SUMMARY_STEPS:
            # 补充其他类型步骤
            other_steps = [s for s in steps if s.get("kind") not in ("delegate", "tool_call")]
            key_steps = key_steps + other_steps

        selected = key_steps[:_MAX_SUMMARY_STEPS]

        for step in selected:
            step_id = str(step.get("step_id") or "")
            kind = str(step.get("kind") or "")
            status = str(step.get("status") or "")
            tool_name = step.get("tool_name") or ""
            target_agent = step.get("target_agent") or ""

            # 构建描述行
            desc_parts: list[str] = []
            if step_id:
                desc_parts.append(f"step={step_id}")
            if kind:
                desc_parts.append(f"kind={kind}")
            if target_agent:
                desc_parts.append(f"agent={target_agent}")
            if tool_name:
                desc_parts.append(f"tool={tool_name}")
            if status:
                desc_parts.append(f"status={status}")

            line = ", ".join(desc_parts)
            if len(line) > _MAX_STEP_DESC_LEN:
                line = line[:_MAX_STEP_DESC_LEN] + "..."
            parts.append(f"[{line}]")

        summary = " | ".join(parts)

        # 如果有更多步骤未包含, 追加省略提示
        total = len(steps)
        if total > _MAX_SUMMARY_STEPS:
            summary += f" ...（共{total}步, 摘要仅显示前{len(selected)}步）"

        return summary

    def _extract_step_id(self, steps: list[dict[str, Any]], *, first: bool) -> str | None:
        """从步骤列表中提取首/尾 step_id.

        Args:
            steps: 步骤列表
            first: True 提取首步, False 提取尾步

        Returns:
            step_id 或 None
        """
        if not steps:
            return None
        target = steps[0] if first else steps[-1]
        step_id = target.get("step_id")
        if isinstance(step_id, str) and step_id:
            return step_id
        return None


__all__ = [
    "SegmentCheckpoint",
    "SessionSegmenter",
]
