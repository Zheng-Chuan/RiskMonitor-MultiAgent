"""
上下文压缩器.

在 LLM 调用前估算对话历史的 token 数, 超限时自动压缩上下文.
策略: 保护头尾消息, 中间部分进行摘要或截断.

设计约束:
1. 保护头尾: 系统提示和最近步骤必须完整保留
2. LLM 摘要可选: enable_llm_summary=False 时使用截断策略
3. token 估算: 使用简单启发式, 不依赖 tiktoken
4. 异常隔离: 压缩失败时使用原始消息继续, 不中断主流程
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 中文字符的 Unicode 范围正则
_CJK_PATTERN = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"
    r"\U00020000-\U0002a6df\U0002a700-\U0002b73f"
    r"\U0002b740-\U0002b81f\U0002b820-\U0002ceaf]"
)

# 每条消息的元数据开销(估算 role 等结构开销)
_PER_MESSAGE_OVERHEAD = 4


@dataclass
class CompressionResult:
    """压缩结果."""

    compressed: bool  # 是否触发了压缩
    original_tokens: int  # 压缩前估算 token 数
    compressed_tokens: int  # 压缩后 token 数
    compression_ratio: float  # 压缩比 (compressed/original)
    protected_head_count: int  # 保留的头部消息数
    protected_tail_count: int  # 保留的尾部消息数
    summarized_count: int  # 被摘要的中间消息数
    compressed_messages: list[dict[str, Any]] = field(default_factory=list)  # 压缩后的消息列表
    summary_text: str | None = None  # 摘要文本(如果有)


class ContextCompressor:
    """在 LLM 调用前估算 token 数, 超限时触发压缩.

    压缩策略:
    1. 保护头部消息 (system prompt + task)
    2. 保护尾部消息 (最近几步 ReAct)
    3. 中间部分进行摘要:
       - enable_llm_summary=True: 调用 LLM 生成摘要
       - enable_llm_summary=False: 截断每条消息前 100 字拼接
    4. 构建压缩后消息: head + summary_message + tail
    """

    def __init__(
        self,
        *,
        max_tokens: int = 6000,
        head_protect_count: int = 2,
        tail_protect_count: int = 4,
        compression_threshold: float = 0.85,
        enable_llm_summary: bool = True,
    ) -> None:
        """初始化上下文压缩器.

        Args:
            max_tokens: 上下文 token 上限
            head_protect_count: 保护头部消息数 (system + user task)
            tail_protect_count: 保护尾部消息数 (最近的 ReAct 步骤)
            compression_threshold: 达到上限的百分比时触发压缩
            enable_llm_summary: 是否使用 LLM 做摘要
        """
        self._max_tokens = max_tokens
        self._head_protect_count = head_protect_count
        self._tail_protect_count = tail_protect_count
        self._compression_threshold = compression_threshold
        self._enable_llm_summary = enable_llm_summary

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def compression_threshold(self) -> float:
        return self._compression_threshold

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """估算消息列表的 token 数.

        使用简单启发式:
        - 中文字符按 1.5 字/token
        - 英文字符按 4 字符/token
        - 每条消息额外计算 4 token 的结构开销

        Args:
            messages: 消息列表, 每条包含 role 和 content

        Returns:
            估算的 token 数
        """
        total_tokens = 0
        for msg in messages:
            content = msg.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            total_tokens += self._estimate_text_tokens(content)
            total_tokens += _PER_MESSAGE_OVERHEAD
        return total_tokens

    def _estimate_text_tokens(self, text: str) -> int:
        """估算文本的 token 数."""
        if not text:
            return 0
        # 统计中文字符数
        cjk_chars = len(_CJK_PATTERN.findall(text))
        # 非中文字符数
        non_cjk_chars = len(text) - cjk_chars
        # 中文按 1.5 字/token, 英文按 4 字符/token
        cjk_tokens = cjk_chars / 1.5
        en_tokens = non_cjk_chars / 4.0
        return int(cjk_tokens + en_tokens)

    def should_compress(self, messages: list[dict[str, Any]]) -> bool:
        """判断是否需要压缩.

        当估算 token 数 >= max_tokens * compression_threshold 时触发.

        Args:
            messages: 消息列表

        Returns:
            True 如果需要压缩
        """
        estimated = self.estimate_tokens(messages)
        threshold = self._max_tokens * self._compression_threshold
        return estimated >= threshold

    async def compress(
        self,
        messages: list[dict[str, Any]],
        *,
        task_context: dict[str, Any] | None = None,
    ) -> CompressionResult:
        """压缩上下文.

        Args:
            messages: 原始消息列表
            task_context: 可选的任务上下文信息

        Returns:
            CompressionResult 包含压缩结果
        """
        original_tokens = 0

        try:
            original_tokens = self.estimate_tokens(messages)

            # 如果不需要压缩, 返回未压缩结果
            if not self.should_compress(messages):
                return CompressionResult(
                    compressed=False,
                    original_tokens=original_tokens,
                    compressed_tokens=original_tokens,
                    compression_ratio=1.0,
                    protected_head_count=0,
                    protected_tail_count=0,
                    summarized_count=0,
                    compressed_messages=messages,
                    summary_text=None,
                )

            # 消息数太少无法压缩
            total_messages = len(messages)
            min_needed = self._head_protect_count + self._tail_protect_count
            if total_messages <= min_needed:
                return CompressionResult(
                    compressed=False,
                    original_tokens=original_tokens,
                    compressed_tokens=original_tokens,
                    compression_ratio=1.0,
                    protected_head_count=0,
                    protected_tail_count=0,
                    summarized_count=0,
                    compressed_messages=messages,
                    summary_text=None,
                )

            # 分割消息: head + middle + tail
            head_messages = messages[: self._head_protect_count]
            tail_messages = messages[-self._tail_protect_count :]
            middle_messages = messages[self._head_protect_count : -self._tail_protect_count]

            summarized_count = len(middle_messages)

            # 生成摘要
            if self._enable_llm_summary:
                summary_text = await self._generate_llm_summary(middle_messages, task_context)
            else:
                summary_text = self._generate_truncated_summary(middle_messages)

            # 构建压缩后消息
            summary_message = self._build_summary_message(summary_text)
            compressed_messages = list(head_messages) + [summary_message] + list(tail_messages)

            compressed_tokens = self.estimate_tokens(compressed_messages)
            compression_ratio = (
                compressed_tokens / original_tokens if original_tokens > 0 else 0.0
            )

            logger.info(
                "Context compressed: %d -> %d tokens (%.1f%% ratio, %d messages summarized)",
                original_tokens,
                compressed_tokens,
                compression_ratio * 100,
                summarized_count,
            )

            return CompressionResult(
                compressed=True,
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
                compression_ratio=compression_ratio,
                protected_head_count=len(head_messages),
                protected_tail_count=len(tail_messages),
                summarized_count=summarized_count,
                compressed_messages=compressed_messages,
                summary_text=summary_text,
            )

        except Exception as e:
            logger.warning("Context compression failed, using original messages: %s", e)
            return CompressionResult(
                compressed=False,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                compression_ratio=1.0,
                protected_head_count=0,
                protected_tail_count=0,
                summarized_count=0,
                compressed_messages=messages,
                summary_text=None,
            )

    async def _generate_llm_summary(
        self,
        middle_messages: list[dict[str, Any]],
        task_context: dict[str, Any] | None,
    ) -> str:
        """使用 LLM 生成中间消息的摘要.

        Args:
            middle_messages: 需要摘要的中间消息
            task_context: 可选的任务上下文

        Returns:
            摘要文本
        """
        # 构建待摘要的对话历史文本
        history_text = self._format_messages_for_summary(middle_messages)

        summary_prompt = (
            "请将以下对话历史总结为关键信息, 保留:\n"
            "- 已完成的步骤和结果\n"
            "- 发现的问题和错误\n"
            "- 当前正在处理的任务\n"
            "总结不超过 300 字.\n\n"
            f"对话历史:\n{history_text}"
        )

        try:
            from riskmonitor_multiagent.llm import LlmClient

            client = LlmClient()
            resp = await client.chat_completions(
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个对话历史摘要助手,请简洁准确地总结关键信息.",
                    },
                    {"role": "user", "content": summary_prompt},
                ],
                temperature=0.3,
                max_tokens=512,
                use_cache=False,
            )
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            summary = content.strip() if content.strip() else self._generate_truncated_summary(middle_messages)
            return summary
        except Exception as e:
            logger.warning("LLM summary failed, falling back to truncation: %s", e)
            return self._generate_truncated_summary(middle_messages)

    def _generate_truncated_summary(self, middle_messages: list[dict[str, Any]]) -> str:
        """使用截断策略生成摘要.

        取每条消息的前 100 字拼接.

        Args:
            middle_messages: 需要摘要的中间消息

        Returns:
            截断摘要文本
        """
        parts: list[str] = []
        for msg in middle_messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            # 取前 100 字
            truncated = content[:100]
            if len(content) > 100:
                truncated += "..."
            parts.append(f"[{role}] {truncated}")
        return "\n".join(parts)

    def _format_messages_for_summary(self, messages: list[dict[str, Any]]) -> str:
        """格式化消息列表为摘要输入文本."""
        lines: list[str] = []
        for i, msg in enumerate(messages, 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            lines.append(f"{i}. [{role}] {content}")
        return "\n".join(lines)

    def _build_summary_message(self, summary_text: str) -> dict[str, Any]:
        """构建摘要消息.

        Args:
            summary_text: 摘要文本

        Returns:
            摘要消息字典
        """
        return {
            "role": "system",
            "content": f"[Previous Context Summary]\n{summary_text}",
        }


__all__ = [
    "CompressionResult",
    "ContextCompressor",
]
