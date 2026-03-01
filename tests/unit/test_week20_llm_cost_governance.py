import os
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


@pytest.mark.asyncio
async def test_week20_rate_limit_blocks_llm_call(monkeypatch):
    monkeypatch.setenv("DISABLE_LLM", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("LLM_RATE_LIMIT_TOKENS_PER_MIN_NON_CRITICAL", "1")
    monkeypatch.setenv("LLM_RATE_LIMIT_BURST_TOKENS_NON_CRITICAL", "1")

    from riskmonitor_multiagent.agents.base import BaseAgent
    from riskmonitor_multiagent.llm import openrouter_client

    async def _boom(*args, **kwargs):
        raise AssertionError("should not call upstream when rate limited")

    monkeypatch.setattr(openrouter_client.OpenRouterClient, "chat_completions", _boom, raising=True)

    agent = BaseAgent(name="orchestrator", system_prompt="Return only valid JSON.")
    res = await agent.ask_json(
        user_prompt="Query: hello?",
        fallback={"schema_version": "x"},
        governance={"user_id": "u1", "priority": "non_critical"},
        max_tokens=512,
    )
    assert res.ok is False
    assert isinstance(res.output, dict) and res.output.get("schema_version") == "x"
    meta = res.meta or {}
    gov = meta.get("governance") if isinstance(meta.get("governance"), dict) else {}
    assert gov.get("blocked") is True


@pytest.mark.asyncio
async def test_week20_cost_accounting_emits_user_metrics(monkeypatch):
    monkeypatch.setenv("DISABLE_LLM", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("LLM_RATE_LIMIT_TOKENS_PER_MIN_DEFAULT", "1000000")
    monkeypatch.setenv("LLM_RATE_LIMIT_BURST_TOKENS_DEFAULT", "1000000")

    from riskmonitor_multiagent.agents.base import BaseAgent
    from riskmonitor_multiagent.llm import openrouter_client
    from riskmonitor_multiagent.observability.metrics import render_prometheus_metrics, reset_observability_metrics

    reset_observability_metrics()

    async def _ok(*args, **kwargs):
        return {
            "choices": [{"message": {"content": "{\"schema_version\": \"ok\"}"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

    monkeypatch.setattr(openrouter_client.OpenRouterClient, "chat_completions", _ok, raising=True)

    agent = BaseAgent(name="critic", system_prompt="Return only valid JSON.")
    res = await agent.ask_json(
        user_prompt="hello",
        fallback={"schema_version": "x"},
        governance={"user_id": "u2", "priority": "default"},
        max_tokens=32,
    )
    assert res.ok is True

    text = render_prometheus_metrics()
    assert "rm_llm_tokens_by_user_total" in text
    assert 'user="u2"' in text
    assert 'agent="critic"' in text

