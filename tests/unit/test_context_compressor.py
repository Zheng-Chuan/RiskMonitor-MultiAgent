"""ContextCompressor 单元测试.

测试场景:
1. token 估算: 不同长度消息的 token 估算合理
2. should_compress 低于阈值不触发
3. should_compress 超过阈值触发
4. 保护头尾消息
5. 中间消息被摘要
6. compression_ratio 计算
7. 无需压缩时返回 compressed=False
8. 截断模式(无 LLM)
9. 长任务链模拟
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


# ---------------------------------------------------------------------------
# 1. Token 估算测试
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    """测试 token 估算逻辑."""

    def test_empty_messages(self):
        """空消息列表 token 数为 0."""
        compressor = ContextCompressor()
        assert compressor.estimate_tokens([]) == 0

    def test_short_english_message(self):
        """短英文消息 token 估算合理."""
        compressor = ContextCompressor()
        messages = [{"role": "user", "content": "Hello world"}]
        tokens = compressor.estimate_tokens(messages)
        # "Hello world" = 11 chars, 英文按 4 char/token = ~2.75 tokens + 4 overhead
        assert tokens > 0
        assert tokens < 10

    def test_chinese_message(self):
        """中文消息 token 估算合理."""
        compressor = ContextCompressor()
        messages = [{"role": "user", "content": "你好世界"}]
        tokens = compressor.estimate_tokens(messages)
        # 4 个中文字符, 1.5 字/token = ~2.67 tokens + 4 overhead
        assert tokens > 0
        assert tokens >= 6

    def test_mixed_content(self):
        """中英文混合内容 token 估算合理."""
        compressor = ContextCompressor()
        messages = [{"role": "user", "content": "Hello 你好 world 世界"}]
        tokens = compressor.estimate_tokens(messages)
        assert tokens > 0

    def test_multiple_messages(self):
        """多条消息 token 累加."""
        compressor = ContextCompressor()
        single = [{"role": "user", "content": "test"}]
        multi = [{"role": "user", "content": "test"}, {"role": "assistant", "content": "test"}]
        single_tokens = compressor.estimate_tokens(single)
        multi_tokens = compressor.estimate_tokens(multi)
        assert multi_tokens > single_tokens
        # 第二条消息增加至少 4 token overhead + content tokens
        assert multi_tokens >= single_tokens + 4

    def test_non_string_content(self):
        """非字符串 content 也能处理."""
        compressor = ContextCompressor()
        messages = [{"role": "user", "content": {"key": "value"}}]
        tokens = compressor.estimate_tokens(messages)
        assert tokens > 0

    def test_long_message_more_tokens(self):
        """长消息比短消息 token 数多."""
        compressor = ContextCompressor()
        short = [{"role": "user", "content": "short"}]
        long_msg = [{"role": "user", "content": "x" * 1000}]
        assert compressor.estimate_tokens(long_msg) > compressor.estimate_tokens(short)


# ---------------------------------------------------------------------------
# 2. should_compress 测试
# ---------------------------------------------------------------------------


class TestShouldCompress:
    """测试 should_compress 判断逻辑."""

    def test_short_messages_not_compress(self):
        """短消息不触发压缩."""
        compressor = ContextCompressor(max_tokens=6000, compression_threshold=0.85)
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ]
        assert compressor.should_compress(messages) is False

    def test_long_messages_trigger_compress(self):
        """长消息触发压缩."""
        compressor = ContextCompressor(max_tokens=100, compression_threshold=0.85)
        # 构造超过 85 tokens 的消息
        messages = [
            {"role": "system", "content": "x" * 500},
            {"role": "user", "content": "y" * 500},
        ]
        assert compressor.should_compress(messages) is True

    def test_threshold_boundary(self):
        """阈值边界测试."""
        compressor = ContextCompressor(max_tokens=1000, compression_threshold=0.85)
        # 85% of 1000 = 850 tokens
        # 构造恰好 850 token 的消息
        # 1 message with ~846 chars = ~211 tokens + 4 overhead = 215 tokens
        # 需要 ~4 条这样的消息
        messages = [
            {"role": "system", "content": "x" * 200},
            {"role": "user", "content": "y" * 200},
            {"role": "assistant", "content": "z" * 200},
            {"role": "user", "content": "w" * 200},
        ]
        # 200 chars * 4 messages / 4 chars_per_token = 200 tokens + 16 overhead = 216 tokens
        # 这远低于 850, 应该不触发
        assert compressor.should_compress(messages) is False

        # 降低 max_tokens 让它触发
        compressor_small = ContextCompressor(max_tokens=200, compression_threshold=0.85)
        assert compressor_small.should_compress(messages) is True


# ---------------------------------------------------------------------------
# 3 & 4 & 5. 压缩功能测试
# ---------------------------------------------------------------------------


class TestCompress:
    """测试压缩功能."""

    @pytest.mark.asyncio
    async def test_short_messages_return_not_compressed(self):
        """短消息列表不触发压缩, 返回 compressed=False."""
        compressor = ContextCompressor(
            max_tokens=6000, compression_threshold=0.85, enable_llm_summary=False,
        )
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = await compressor.compress(messages)

        assert result.compressed is False
        assert result.original_tokens == result.compressed_tokens
        assert result.compression_ratio == 1.0
        assert result.summarized_count == 0
        assert result.compressed_messages == messages

    @pytest.mark.asyncio
    async def test_protect_head_and_tail(self):
        """压缩后头尾消息保留完整."""
        compressor = ContextCompressor(
            max_tokens=50,
            head_protect_count=2,
            tail_protect_count=2,
            compression_threshold=0.5,
            enable_llm_summary=False,
        )
        long_content = "x" * 200
        messages = [
            {"role": "system", "content": "HEAD_SYSTEM_PROMPT"},
            {"role": "user", "content": "HEAD_USER_TASK"},
            {"role": "assistant", "content": long_content},
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": long_content},
            {"role": "user", "content": "TAIL_LAST_USER"},
            {"role": "assistant", "content": "TAIL_LAST_ASSISTANT"},
        ]
        result = await compressor.compress(messages)

        assert result.compressed is True
        assert result.protected_head_count == 2
        assert result.protected_tail_count == 2

        compressed = result.compressed_messages
        # 头部保留
        assert compressed[0]["content"] == "HEAD_SYSTEM_PROMPT"
        assert compressed[1]["content"] == "HEAD_USER_TASK"
        # 尾部保留
        assert compressed[-2]["content"] == "TAIL_LAST_USER"
        assert compressed[-1]["content"] == "TAIL_LAST_ASSISTANT"

    @pytest.mark.asyncio
    async def test_middle_messages_summarized(self):
        """中间消息被替换为摘要."""
        compressor = ContextCompressor(
            max_tokens=50,
            head_protect_count=2,
            tail_protect_count=2,
            compression_threshold=0.5,
            enable_llm_summary=False,
        )
        long_content = "x" * 200
        messages = [
            {"role": "system", "content": "head1"},
            {"role": "user", "content": "head2"},
            {"role": "assistant", "content": long_content},
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": long_content},
            {"role": "user", "content": "tail1"},
            {"role": "assistant", "content": "tail2"},
        ]
        result = await compressor.compress(messages)

        assert result.compressed is True
        assert result.summarized_count == 3

        # 压缩后: head(2) + summary(1) + tail(2) = 5
        assert len(result.compressed_messages) == 5

        # 摘要消息
        summary_msg = result.compressed_messages[2]
        assert summary_msg["role"] == "system"
        assert "[Previous Context Summary]" in summary_msg["content"]
        assert result.summary_text is not None

    @pytest.mark.asyncio
    async def test_compression_ratio_calculated(self):
        """压缩比正确计算."""
        compressor = ContextCompressor(
            max_tokens=50,
            head_protect_count=1,
            tail_protect_count=1,
            compression_threshold=0.5,
            enable_llm_summary=False,
        )
        messages = [
            {"role": "system", "content": "head"},
            {"role": "user", "content": "a" * 200},
            {"role": "assistant", "content": "b" * 200},
            {"role": "user", "content": "c" * 200},
            {"role": "assistant", "content": "tail"},
        ]
        result = await compressor.compress(messages)

        assert result.compressed is True
        assert result.original_tokens > result.compressed_tokens
        assert 0 < result.compression_ratio < 1.0

    @pytest.mark.asyncio
    async def test_truncation_mode_no_llm(self):
        """截断模式: enable_llm_summary=False 使用截断策略."""
        compressor = ContextCompressor(
            max_tokens=50,
            head_protect_count=1,
            tail_protect_count=1,
            compression_threshold=0.5,
            enable_llm_summary=False,
        )
        long_content = "This is a very long message that should be truncated. " * 10
        messages = [
            {"role": "system", "content": "head"},
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": long_content},
            {"role": "user", "content": "tail"},
        ]
        result = await compressor.compress(messages)

        assert result.compressed is True
        assert result.summary_text is not None
        # 截断摘要应包含 [role] 前缀
        assert "[user]" in result.summary_text or "[assistant]" in result.summary_text
        # 每条消息截断到 100 字
        for line in result.summary_text.split("\n"):
            # 检查截断后的内容长度 (排除 [role] 前缀和 ... 后缀)
            if "..." in line:
                # 有截断
                content_part = line.split("] ", 1)[-1] if "] " in line else line
                content_without_dots = content_part.rstrip(".")
                assert len(content_part) <= 103  # 100 chars + "..."

    @pytest.mark.asyncio
    async def test_llm_summary_mode_with_mock(self):
        """LLM 摘要模式: enable_llm_summary=True, mock LLM 返回."""
        compressor = ContextCompressor(
            max_tokens=50,
            head_protect_count=1,
            tail_protect_count=1,
            compression_threshold=0.5,
            enable_llm_summary=True,
        )
        messages = [
            {"role": "system", "content": "head"},
            {"role": "user", "content": "middle content 1"},
            {"role": "assistant", "content": "middle content 2"},
            {"role": "user", "content": "tail"},
        ]

        # Mock LLM client
        mock_resp = {
            "choices": [
                {"message": {"content": "这是LLM生成的摘要文本"}}
            ]
        }
        with patch(
            "riskmonitor_multiagent.llm.llm_client.LlmClient.chat_completions",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await compressor.compress(messages)

        assert result.compressed is True
        assert result.summary_text == "这是LLM生成的摘要文本"

    @pytest.mark.asyncio
    async def test_llm_summary_fallback_on_error(self):
        """LLM 摘要失败时回退到截断策略."""
        compressor = ContextCompressor(
            max_tokens=50,
            head_protect_count=1,
            tail_protect_count=1,
            compression_threshold=0.5,
            enable_llm_summary=True,
        )
        messages = [
            {"role": "system", "content": "head"},
            {"role": "user", "content": "middle content 1"},
            {"role": "assistant", "content": "middle content 2"},
            {"role": "user", "content": "tail"},
        ]

        with patch(
            "riskmonitor_multiagent.llm.llm_client.LlmClient.chat_completions",
            new_callable=AsyncMock,
            side_effect=Exception("LLM unavailable"),
        ):
            result = await compressor.compress(messages)

        assert result.compressed is True
        # 回退到截断, 摘要应包含截断内容
        assert result.summary_text is not None
        assert "[user]" in result.summary_text or "[assistant]" in result.summary_text

    @pytest.mark.asyncio
    async def test_too_few_messages_no_compression(self):
        """消息数少于 head+tail 时不压缩."""
        compressor = ContextCompressor(
            max_tokens=10,
            head_protect_count=2,
            tail_protect_count=2,
            compression_threshold=0.5,
            enable_llm_summary=False,
        )
        # 只有 3 条消息, 但 head(2) + tail(2) = 4 > 3
        messages = [
            {"role": "system", "content": "x" * 500},
            {"role": "user", "content": "y" * 500},
            {"role": "assistant", "content": "z" * 500},
        ]
        result = await compressor.compress(messages)

        assert result.compressed is False
        assert result.compressed_messages == messages

    @pytest.mark.asyncio
    async def test_compression_exception_isolation(self):
        """压缩异常时不中断, 返回原始消息."""
        compressor = ContextCompressor(
            max_tokens=10,
            head_protect_count=1,
            tail_protect_count=1,
            compression_threshold=0.1,
            enable_llm_summary=False,
        )
        messages = [
            {"role": "system", "content": "head"},
            {"role": "user", "content": "middle"},
            {"role": "assistant", "content": "tail"},
        ]

        # Mock estimate_tokens 抛异常
        with patch.object(
            compressor, "estimate_tokens", side_effect=Exception("unexpected error")
        ):
            result = await compressor.compress(messages)

        # should_compress 内部也调用 estimate_tokens, 所以会在 should_compress 阶段失败
        # compress 方法的 try/except 会捕获并返回未压缩结果
        assert result.compressed is False
        assert result.compressed_messages == messages


# ---------------------------------------------------------------------------
# 4. 长任务链模拟
# ---------------------------------------------------------------------------


class TestLongConversationChain:
    """模拟长任务链场景."""

    @pytest.mark.asyncio
    async def test_long_chain_compression(self):
        """20+ 条消息的长任务链压缩后 token 数在限制内."""
        max_tokens = 500
        compressor = ContextCompressor(
            max_tokens=max_tokens,
            head_protect_count=2,
            tail_protect_count=4,
            compression_threshold=0.85,
            enable_llm_summary=False,
        )

        # 构造 25 条消息, 模拟 ReAct 循环
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "You are a risk monitoring agent. " * 10},
            {"role": "user", "content": "Please analyze the transaction. " * 10},
        ]
        for i in range(23):
            role = "assistant" if i % 2 == 0 else "user"
            content = f"Step {i + 1}: Performing analysis on data batch {i + 1}. " * 5
            messages.append({"role": role, "content": content})

        original_tokens = compressor.estimate_tokens(messages)
        assert original_tokens > max_tokens * 0.85

        result = await compressor.compress(messages)

        assert result.compressed is True
        assert result.compressed_tokens < original_tokens
        assert result.summarized_count == 19  # 25 - 2(head) - 4(tail) = 19
        assert len(result.compressed_messages) == 2 + 1 + 4  # head + summary + tail

    @pytest.mark.asyncio
    async def test_compressed_messages_format_valid(self):
        """压缩后消息格式可被 LLM 消费."""
        compressor = ContextCompressor(
            max_tokens=50,
            head_protect_count=2,
            tail_protect_count=2,
            compression_threshold=0.5,
            enable_llm_summary=False,
        )
        messages = [
            {"role": "system", "content": "head1"},
            {"role": "user", "content": "head2"},
            {"role": "assistant", "content": "middle1"},
            {"role": "user", "content": "middle2"},
            {"role": "assistant", "content": "tail1"},
            {"role": "user", "content": "tail2"},
        ]
        result = await compressor.compress(messages)

        assert result.compressed is True
        for msg in result.compressed_messages:
            assert "role" in msg
            assert "content" in msg
            assert isinstance(msg["content"], str)
            assert msg["role"] in ("system", "user", "assistant")

    @pytest.mark.asyncio
    async def test_summary_message_format(self):
        """摘要消息格式正确."""
        compressor = ContextCompressor(enable_llm_summary=False)
        summary_msg = compressor._build_summary_message("test summary content")

        assert summary_msg["role"] == "system"
        assert "[Previous Context Summary]" in summary_msg["content"]
        assert "test summary content" in summary_msg["content"]


# ---------------------------------------------------------------------------
# 5. 配置参数测试
# ---------------------------------------------------------------------------


class TestConfiguration:
    """测试配置参数."""

    def test_custom_parameters(self):
        """自定义参数正确设置."""
        compressor = ContextCompressor(
            max_tokens=10000,
            head_protect_count=3,
            tail_protect_count=6,
            compression_threshold=0.7,
            enable_llm_summary=False,
        )
        assert compressor.max_tokens == 10000
        assert compressor.compression_threshold == 0.7

    @pytest.mark.asyncio
    async def test_different_head_tail_counts(self):
        """不同的 head/tail 保护数量."""
        compressor = ContextCompressor(
            max_tokens=50,
            head_protect_count=3,
            tail_protect_count=3,
            compression_threshold=0.3,
            enable_llm_summary=False,
        )
        messages = [
            {"role": "system", "content": "h1"},
            {"role": "user", "content": "h2"},
            {"role": "assistant", "content": "h3"},
            {"role": "user", "content": "m1"},
            {"role": "assistant", "content": "m2"},
            {"role": "user", "content": "t1"},
            {"role": "assistant", "content": "t2"},
            {"role": "user", "content": "t3"},
        ]
        # 注入足够长的内容以触发压缩
        for msg in messages:
            msg["content"] = msg["content"] + " " + "x" * 100

        result = await compressor.compress(messages)

        assert result.compressed is True
        assert result.protected_head_count == 3
        assert result.protected_tail_count == 3
        assert result.summarized_count == 2
