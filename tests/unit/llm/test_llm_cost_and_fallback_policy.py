import os
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


@pytest.mark.asyncio
async def test_rate_limit_blocks_llm_call(monkeypatch):
    monkeypatch.setenv("DISABLE_LLM", "0")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_RATE_LIMIT_TOKENS_PER_MIN_NON_CRITICAL", "1")
    monkeypatch.setenv("LLM_RATE_LIMIT_BURST_TOKENS_NON_CRITICAL", "1")

    from riskmonitor_multiagent.agents.base import BaseAgent
    from riskmonitor_multiagent.llm import llm_client

    async def _boom(*args, **kwargs):
        raise AssertionError("should not call upstream when rate limited")

    monkeypatch.setattr(llm_client.LlmClient, "chat_completions", _boom, raising=True)

    agent = BaseAgent(name="orchestrator", system_prompt="Return only valid JSON.")
    with pytest.raises(Exception):
        await agent.ask_json(
            user_prompt="Query: hello?",
            fallback={"schema_version": "x"},
            governance={"user_id": "u1", "priority": "non_critical"},
            max_tokens=512,
        )


@pytest.mark.asyncio
async def test_cost_accounting_emits_user_metrics(monkeypatch):
    monkeypatch.setenv("DISABLE_LLM", "0")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_RATE_LIMIT_TOKENS_PER_MIN_DEFAULT", "1000000")
    monkeypatch.setenv("LLM_RATE_LIMIT_BURST_TOKENS_DEFAULT", "1000000")

    from riskmonitor_multiagent.agents.base import BaseAgent
    from riskmonitor_multiagent.llm import llm_client
    from riskmonitor_multiagent.observability.metrics import render_prometheus_metrics, reset_observability_metrics

    reset_observability_metrics()

    async def _ok(*args, **kwargs):
        return {
            "choices": [{"message": {"content": "{\"schema_version\": \"ok\"}"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

    monkeypatch.setattr(llm_client.LlmClient, "chat_completions", _ok, raising=True)

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


@pytest.mark.asyncio
async def test_ask_json_falls_back_when_json_mode_is_unsupported(monkeypatch):
    monkeypatch.setenv("DISABLE_LLM", "0")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_RATE_LIMIT_TOKENS_PER_MIN_DEFAULT", "1000000")
    monkeypatch.setenv("LLM_RATE_LIMIT_BURST_TOKENS_DEFAULT", "1000000")

    from riskmonitor_multiagent.agents.base import BaseAgent
    from riskmonitor_multiagent.llm import LLMError
    from riskmonitor_multiagent.llm import llm_client

    calls = []

    async def _mock_chat_completions(*args, **kwargs):
        calls.append(kwargs.get("response_format"))
        if len(calls) == 1:
            raise LLMError(
                code="UPSTREAM_BAD_STATUS",
                message="response_format.type json_object is not supported by this model",
                status_code=400,
            )
        return {
            "choices": [{"message": {"content": "{\"schema_version\": \"ok\"}"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22},
        }

    monkeypatch.setattr(llm_client.LlmClient, "chat_completions", _mock_chat_completions, raising=True)

    agent = BaseAgent(name="critic", system_prompt="Return only valid JSON.")
    res = await agent.ask_json(
        user_prompt="hello",
        fallback={"schema_version": "x"},
        governance={"user_id": "u3", "priority": "default"},
        max_tokens=32,
    )

    assert res.ok is True
    assert res.output["schema_version"] == "ok"
    assert calls[0] == {"type": "json_object"}
    assert calls[1] is None


@pytest.mark.asyncio
async def test_ask_json_returns_fallback_on_bad_json_output(monkeypatch):
    monkeypatch.setenv("DISABLE_LLM", "0")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_RATE_LIMIT_TOKENS_PER_MIN_DEFAULT", "1000000")
    monkeypatch.setenv("LLM_RATE_LIMIT_BURST_TOKENS_DEFAULT", "1000000")

    from riskmonitor_multiagent.agents.base import BaseAgent
    from riskmonitor_multiagent.llm import llm_client

    async def _mock_chat_completions(*args, **kwargs):
        return {
            "choices": [{"message": {"content": "```json\n{\"broken\": true\n```"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22},
        }

    monkeypatch.setattr(llm_client.LlmClient, "chat_completions", _mock_chat_completions, raising=True)

    agent = BaseAgent(name="critic", system_prompt="Return only valid JSON.")
    res = await agent.ask_json(
        user_prompt="hello",
        fallback={"schema_version": "fallback"},
        governance={"user_id": "u4", "priority": "default"},
        max_tokens=32,
    )

    assert res.ok is True
    assert res.output == {"schema_version": "fallback"}
    assert (res.meta or {}).get("fallback_used") is True
