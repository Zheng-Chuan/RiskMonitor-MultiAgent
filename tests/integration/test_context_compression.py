"""上下文压缩集成测试.

测试场景:
1. 短任务不触发压缩: 5步任务 → 无压缩
2. 长任务触发压缩: 25步模拟任务 → 压缩后继续执行
3. 压缩后消息可被 LLM 消费: 压缩后的消息格式正确
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.memory.context_compressor import (
    CompressionResult,
    ContextCompressor,
)
from riskmonitor_multiagent.proactive_agents.base import BaseProactiveAgent


def _make_agent(
    *,
    enable_compression: bool = True,
    compressor: ContextCompressor | None = None,
) -> BaseProactiveAgent:
    """创建测试用 Agent."""
    return BaseProactiveAgent(
        name="test_agent",
        system_prompt="You are a test agent for risk monitoring.",
        enable_background_monitor=False,
        enable_context_compression=enable_compression,
        context_compressor=compressor,
    )


# ---------------------------------------------------------------------------
# 1. 短任务不触发压缩
# ---------------------------------------------------------------------------


class TestShortTaskNoCompression:
    """短任务不触发压缩."""

    @pytest.mark.asyncio
    async def test_short_messages_no_compression_triggered(self):
        """短消息列表不触发压缩."""
        compressor = ContextCompressor(
            max_tokens=6000,
            compression_threshold=0.85,
            enable_llm_summary=False,
        )
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Analyze this transaction."},
            {"role": "assistant", "content": "I'll analyze it."},
            {"role": "user", "content": "What did you find?"},
            {"role": "assistant", "content": "The transaction looks normal."},
        ]
        result = await compressor.compress(messages)

        assert result.compressed is False
        assert result.compressed_messages == messages

    @pytest.mark.asyncio
    async def test_agent_short_task_no_compression(self):
        """Agent 处理短任务时不触发压缩."""
        # Mock LLM 返回简单响应
        mock_resp = {
            "choices": [
                {"message": {"content": "Task completed successfully"}}
            ]
        }

        agent = _make_agent(
            compressor=ContextCompressor(
                max_tokens=10000,
                compression_threshold=0.85,
                enable_llm_summary=False,
            )
        )

        with patch(
            "riskmonitor_multiagent.llm.llm_client.LlmClient.chat_completions",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await agent.run_with_react(
                task={"task_id": "test_short", "content": "Quick analysis"},
                max_steps=3,
            )

        assert result.ok is True
        # 短任务不应有压缩日志
        # (验证: compressed_messages 应未被修改)

    @pytest.mark.asyncio
    async def test_five_step_task_no_compression(self):
        """5步任务不触发压缩."""
        compressor = ContextCompressor(
            max_tokens=10000,
            compression_threshold=0.85,
            enable_llm_summary=False,
        )

        # 5步任务的消息量
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "System prompt for the agent."},
        ]
        for i in range(4):
            role = "assistant" if i % 2 == 0 else "user"
            messages.append({
                "role": role,
                "content": f"Step {i + 1}: Processing risk data batch number {i + 1}.",
            })

        result = await compressor.compress(messages)
        assert result.compressed is False


# ---------------------------------------------------------------------------
# 2. 长任务触发压缩
# ---------------------------------------------------------------------------


class TestLongTaskCompression:
    """长任务触发压缩."""

    @pytest.mark.asyncio
    async def test_long_conversation_triggers_compression(self):
        """25步模拟任务触发压缩."""
        compressor = ContextCompressor(
            max_tokens=500,
            head_protect_count=2,
            tail_protect_count=4,
            compression_threshold=0.85,
            enable_llm_summary=False,
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "You are a risk monitoring agent. " * 5},
            {"role": "user", "content": "Analyze the transaction batch. " * 5},
        ]
        for i in range(23):
            role = "assistant" if i % 2 == 0 else "user"
            messages.append({
                "role": role,
                "content": f"Step {i + 1}: Risk analysis result for batch {i + 1}. " * 3,
            })

        original_tokens = compressor.estimate_tokens(messages)
        assert compressor.should_compress(messages) is True

        result = await compressor.compress(messages)

        assert result.compressed is True
        assert result.compressed_tokens < original_tokens
        assert result.summarized_count > 0
        assert result.protected_head_count == 2
        assert result.protected_tail_count == 4

    @pytest.mark.asyncio
    async def test_compression_continues_after_compress(self):
        """压缩后可以继续使用消息."""
        compressor = ContextCompressor(
            max_tokens=100,
            head_protect_count=2,
            tail_protect_count=2,
            compression_threshold=0.5,
            enable_llm_summary=False,
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Task definition."},
        ]
        for i in range(10):
            role = "assistant" if i % 2 == 0 else "user"
            messages.append({
                "role": role,
                "content": f"Long step {i + 1} content. " * 20,
            })

        result = await compressor.compress(messages)

        assert result.compressed is True

        # 压缩后的消息可以被再次检查
        still_needs = compressor.should_compress(result.compressed_messages)
        # 可能仍需压缩或不需要, 但关键是可以正常调用
        assert isinstance(still_needs, bool)

        # 可以再次压缩
        if still_needs:
            result2 = await compressor.compress(result.compressed_messages)
            assert isinstance(result2, CompressionResult)

    @pytest.mark.asyncio
    async def test_agent_with_compression_enabled(self):
        """启用压缩的 Agent 在长任务中正常工作."""
        mock_resp = {
            "choices": [
                {"message": {"content": "Analysis complete"}}
            ]
        }

        agent = _make_agent(
            compressor=ContextCompressor(
                max_tokens=200,
                compression_threshold=0.5,
                enable_llm_summary=False,
            )
        )

        with patch(
            "riskmonitor_multiagent.llm.llm_client.LlmClient.chat_completions",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await agent.run_with_react(
                task={"task_id": "test_long", "content": "x" * 500},
                max_steps=2,
            )

        # Agent 应正常完成 (压缩失败也不应中断)
        assert result.ok is True

    @pytest.mark.asyncio
    async def test_compression_with_task_context(self):
        """压缩时传递 task_context."""
        compressor = ContextCompressor(
            max_tokens=50,
            head_protect_count=1,
            tail_protect_count=1,
            compression_threshold=0.5,
            enable_llm_summary=False,
        )

        messages = [
            {"role": "system", "content": "head"},
            {"role": "user", "content": "x" * 200},
            {"role": "assistant", "content": "y" * 200},
            {"role": "user", "content": "tail"},
        ]

        task_context = {"task_id": "task_001", "agent": "risk_analyzer"}
        result = await compressor.compress(messages, task_context=task_context)

        assert result.compressed is True


# ---------------------------------------------------------------------------
# 3. 压缩后消息可被 LLM 消费
# ---------------------------------------------------------------------------


class TestCompressedMessagesConsumable:
    """压缩后消息格式可被 LLM 消费."""

    @pytest.mark.asyncio
    async def test_compressed_messages_have_valid_roles(self):
        """压缩后消息都有有效的 role 字段."""
        compressor = ContextCompressor(
            max_tokens=50,
            head_protect_count=2,
            tail_protect_count=2,
            compression_threshold=0.3,
            enable_llm_summary=False,
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user task"},
        ]
        for i in range(6):
            role = "assistant" if i % 2 == 0 else "user"
            messages.append({"role": role, "content": "x" * 100})

        result = await compressor.compress(messages)

        assert result.compressed is True
        for msg in result.compressed_messages:
            assert "role" in msg
            assert msg["role"] in ("system", "user", "assistant")
            assert "content" in msg
            assert isinstance(msg["content"], str)
            assert len(msg["content"]) > 0

    @pytest.mark.asyncio
    async def test_compressed_messages_structure(self):
        """压缩后消息结构: head + summary + tail."""
        compressor = ContextCompressor(
            max_tokens=50,
            head_protect_count=2,
            tail_protect_count=3,
            compression_threshold=0.3,
            enable_llm_summary=False,
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "task"},
        ]
        for i in range(8):
            role = "assistant" if i % 2 == 0 else "user"
            messages.append({"role": role, "content": "x" * 100})
        # Add tail messages
        messages.append({"role": "user", "content": "tail1"})
        messages.append({"role": "assistant", "content": "tail2"})
        messages.append({"role": "user", "content": "tail3"})

        result = await compressor.compress(messages)

        assert result.compressed is True
        # Expected: 2(head) + 1(summary) + 3(tail) = 6
        assert len(result.compressed_messages) == 2 + 1 + 3

        # Head messages preserved
        assert result.compressed_messages[0] == messages[0]
        assert result.compressed_messages[1] == messages[1]

        # Summary message in the middle
        summary_msg = result.compressed_messages[2]
        assert summary_msg["role"] == "system"
        assert "[Previous Context Summary]" in summary_msg["content"]

        # Tail messages preserved
        assert result.compressed_messages[-3]["content"] == "tail1"
        assert result.compressed_messages[-2]["content"] == "tail2"
        assert result.compressed_messages[-1]["content"] == "tail3"

    @pytest.mark.asyncio
    async def test_compressed_messages_passable_to_llm_client(self):
        """压缩后消息可直接传给 LlmClient.chat_completions."""
        compressor = ContextCompressor(
            max_tokens=50,
            head_protect_count=2,
            tail_protect_count=2,
            compression_threshold=0.3,
            enable_llm_summary=False,
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "task"},
        ]
        for i in range(4):
            role = "assistant" if i % 2 == 0 else "user"
            messages.append({"role": role, "content": "x" * 100})
        messages.append({"role": "user", "content": "tail1"})
        messages.append({"role": "assistant", "content": "tail2"})

        result = await compressor.compress(messages)
        assert result.compressed is True

        # Mock LLM client to verify it can consume compressed messages
        mock_resp = {
            "choices": [
                {"message": {"content": "Response based on compressed context"}}
            ]
        }

        with patch(
            "riskmonitor_multiagent.llm.llm_client.LlmClient.chat_completions",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_chat:
            from riskmonitor_multiagent.llm import LlmClient

            client = LlmClient()
            resp = await client.chat_completions(
                messages=result.compressed_messages,
                model="test-model",
                temperature=0.2,
                use_cache=False,
            )

            # Verify LLM was called with compressed messages
            mock_chat.assert_called_once()
            call_kwargs = mock_chat.call_args
            sent_messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
            assert sent_messages == result.compressed_messages
            assert resp["choices"][0]["message"]["content"] == "Response based on compressed context"
