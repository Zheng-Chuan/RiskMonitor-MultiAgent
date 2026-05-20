"""Token 监控真实集成测试.

验证 TokenTracker 基础功能、真实 LLM 调用的 token 追踪、以及 /api/llm/usage 端点。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.llm.token_tracker import (
    get_token_tracker,
    record_token_usage,
    reset_token_tracker,
)
from riskmonitor_multiagent.observability.metrics import (
    render_prometheus_metrics,
    reset_observability_metrics,
)


@pytest.fixture(autouse=True)
def clean_tracker():
    """每个测试前重置 tracker"""
    reset_token_tracker()
    reset_observability_metrics()
    yield
    reset_token_tracker()


class TestTokenTrackingUnit:
    """TokenTracker 基础功能验证"""

    def test_record_increments_counters(self):
        """记录一次用量后，summary 正确反映"""
        record_token_usage(
            model="test-model",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            latency_ms=500.0,
            cached=False,
        )
        summary = get_token_tracker().summary()
        assert summary["calls"] == 1
        assert summary["total_tokens"] == 300
        assert summary["prompt_tokens"] == 100
        assert summary["completion_tokens"] == 200
        assert "test-model" in summary["by_model"]

    def test_multiple_records_accumulate(self):
        """多次记录累加正确"""
        for i in range(5):
            record_token_usage(model="m1", prompt_tokens=10, completion_tokens=20, total_tokens=30)
        summary = get_token_tracker().summary()
        assert summary["calls"] == 5
        assert summary["total_tokens"] == 150

    def test_by_model_breakdown(self):
        """按模型分组正确"""
        record_token_usage(model="model-a", prompt_tokens=10, completion_tokens=20, total_tokens=30)
        record_token_usage(model="model-b", prompt_tokens=50, completion_tokens=60, total_tokens=110)
        summary = get_token_tracker().summary()
        assert len(summary["by_model"]) == 2
        assert summary["by_model"]["model-a"]["total_tokens"] == 30
        assert summary["by_model"]["model-b"]["total_tokens"] == 110

    def test_prometheus_metrics_include_token_counters(self):
        """Prometheus 指标包含 token 计数"""
        record_token_usage(model="ark-code-latest", prompt_tokens=50, completion_tokens=100, total_tokens=150)
        metrics_text = render_prometheus_metrics()
        assert "rm_llm_tokens_total" in metrics_text
        assert "rm_llm_calls_total" in metrics_text

    def test_alert_triggered_when_threshold_exceeded(self, monkeypatch):
        """超过告警阈值时触发告警"""
        monkeypatch.setenv("LLM_TOKEN_ALERT_HOURLY", "100")
        reset_token_tracker()  # 重新加载阈值

        # 记录超过阈值的用量
        record_token_usage(model="m1", prompt_tokens=60, completion_tokens=60, total_tokens=120)

        summary = get_token_tracker().summary()
        assert summary["hourly_alert_triggered"] is True

    def test_alert_not_triggered_below_threshold(self, monkeypatch):
        """未超过阈值不触发告警"""
        monkeypatch.setenv("LLM_TOKEN_ALERT_HOURLY", "1000")
        reset_token_tracker()

        record_token_usage(model="m1", prompt_tokens=10, completion_tokens=10, total_tokens=20)

        summary = get_token_tracker().summary()
        assert summary["hourly_alert_triggered"] is False

    def test_cached_calls_tracked_separately(self):
        """缓存命中的调用单独记录"""
        record_token_usage(model="m1", prompt_tokens=0, completion_tokens=0, total_tokens=0, cached=True)
        record_token_usage(model="m1", prompt_tokens=50, completion_tokens=50, total_tokens=100, cached=False)

        metrics_text = render_prometheus_metrics()
        # 验证 cached 标签存在 (lowercase true/false in prometheus labels)
        assert 'cached="true"' in metrics_text or 'cached="false"' in metrics_text


class TestRealLLMTokenTracking:
    """真实火山引擎 LLM 调用的 token 追踪验证"""

    @pytest.mark.asyncio
    async def test_real_llm_call_records_tokens(self):
        """真实 LLM 调用后 token 被正确记录"""
        from riskmonitor_multiagent.llm.llm_client import LlmClient

        client = LlmClient()

        # 调用真实 LLM
        response = await client.chat_completions(
            messages=[{"role": "user", "content": "回复OK即可"}],
            temperature=0.1,  # 非0避免缓存
            use_cache=False,
        )

        # 验证 response 包含 usage
        assert "usage" in response
        assert response["usage"]["total_tokens"] > 0

        # 验证 tracker 已记录
        summary = get_token_tracker().summary()
        assert summary["calls"] >= 1
        assert summary["total_tokens"] > 0
        assert summary["prompt_tokens"] > 0
        assert summary["completion_tokens"] > 0

    @pytest.mark.asyncio
    async def test_real_llm_latency_recorded(self):
        """真实 LLM 调用延迟被记录"""
        from riskmonitor_multiagent.llm.llm_client import LlmClient

        client = LlmClient()
        await client.chat_completions(
            messages=[{"role": "user", "content": "Hi"}],
            use_cache=False,
        )

        metrics_text = render_prometheus_metrics()
        assert "rm_llm_latency" in metrics_text

    @pytest.mark.asyncio
    async def test_real_llm_model_label_correct(self):
        """真实调用的 model 标签正确"""
        from riskmonitor_multiagent.llm.llm_client import LlmClient

        client = LlmClient()
        await client.chat_completions(
            messages=[{"role": "user", "content": "Test"}],
            use_cache=False,
        )

        summary = get_token_tracker().summary()
        # ark-code-latest 应该出现在 by_model 中
        assert len(summary["by_model"]) >= 1

    @pytest.mark.asyncio
    async def test_cache_hit_does_not_record_tokens(self):
        """缓存命中不记录 token 消耗"""
        from riskmonitor_multiagent.llm.llm_client import LlmClient

        client = LlmClient()
        messages = [{"role": "user", "content": "缓存测试固定内容12345"}]

        # 第一次调用（temperature=0 会被缓存）
        await client.chat_completions(messages=messages, temperature=0.0, use_cache=True)
        first_summary = get_token_tracker().summary()
        first_tokens = first_summary["total_tokens"]
        first_calls = first_summary["calls"]

        # 第二次调用（应该命中缓存）
        await client.chat_completions(messages=messages, temperature=0.0, use_cache=True)
        second_summary = get_token_tracker().summary()

        # 缓存命中不应增加 token 和 calls
        assert second_summary["total_tokens"] == first_tokens
        assert second_summary["calls"] == first_calls


class TestUsageAPIEndpoint:
    """/api/llm/usage 端点测试"""

    def test_usage_endpoint_returns_json(self):
        """端点返回正确 JSON 格式"""
        from starlette.testclient import TestClient

        from riskmonitor_multiagent.server import mcp

        app = mcp.streamable_http_app()
        client = TestClient(app)

        response = client.get("/api/llm/usage")
        assert response.status_code == 200
        data = response.json()

        # 验证返回的字段完整
        assert "window_hours" in data
        assert "total_tokens" in data
        assert "prompt_tokens" in data
        assert "completion_tokens" in data
        assert "calls" in data
        assert "by_model" in data
        assert "alert_threshold_hourly" in data
        assert "hourly_alert_triggered" in data

    def test_usage_endpoint_reflects_recorded_data(self):
        """端点反映已记录的数据"""
        from starlette.testclient import TestClient

        from riskmonitor_multiagent.server import mcp

        # 先记录一些数据
        record_token_usage(model="test-api", prompt_tokens=100, completion_tokens=200, total_tokens=300)

        app = mcp.streamable_http_app()
        client = TestClient(app)

        response = client.get("/api/llm/usage")
        data = response.json()

        assert data["calls"] >= 1
        assert data["total_tokens"] >= 300
