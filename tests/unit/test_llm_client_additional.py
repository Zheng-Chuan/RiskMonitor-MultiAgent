from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from riskmonitor_multiagent.llm.llm_client import (
    LLMError,
    LlmClient,
    _build_headers,
    _normalize_response_payload,
    extract_first_text,
)


def test_build_headers_includes_optional_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("LLM_HTTP_REFERER", "https://example.com")
    monkeypatch.setenv("LLM_APP_TITLE", "RiskMonitor")

    headers = _build_headers(host_header="openrouter.ai")

    assert headers["Authorization"] == "Bearer key"
    assert headers["Host"] == "openrouter.ai"
    assert headers["HTTP-Referer"] == "https://example.com"
    assert headers["X-Title"] == "RiskMonitor"


def test_extract_first_text_handles_invalid_shapes() -> None:
    assert extract_first_text({}) == ""
    assert extract_first_text({"choices": []}) == ""
    assert extract_first_text({"choices": ["bad"]}) == ""
    assert extract_first_text({"choices": [{"message": "bad"}]}) == ""
    assert extract_first_text({"choices": [{"message": {"content": 1}}]}) == ""


def test_normalize_response_payload_maps_reasoning_fields() -> None:
    payload = _normalize_response_payload(
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "reasoning": "first reasoning",
                    }
                },
                {
                    "message": {
                        "content": None,
                        "reasoning_details": [{"text": "detail-a"}, {"text": "detail-b"}],
                    }
                },
            ]
        }
    )

    assert payload["choices"][0]["message"]["reasoning_content"] == "first reasoning"
    assert payload["choices"][1]["message"]["reasoning_content"] == "detail-a\ndetail-b"


@pytest.mark.asyncio
async def test_chat_completions_rejects_invalid_input_and_empty_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr("riskmonitor_multiagent.llm.llm_client.config.get_llm_model", lambda: "")
    client = LlmClient(http_client=MagicMock(), base_url="https://api.example.com/v1")

    with pytest.raises(LLMError, match="messages 不能为空"):
        await client.chat_completions(messages=[])

    with pytest.raises(LLMError, match="LLM_MODEL 为空"):
        await client.chat_completions(messages=[{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_chat_completions_uses_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "deepseek/test")
    cached = {"choices": [{"message": {"content": "cached"}}]}
    fake_cache = MagicMock()
    fake_cache.get.return_value = cached
    monkeypatch.setattr("riskmonitor_multiagent.llm.llm_client.get_llm_cache", lambda: fake_cache)

    session = MagicMock()
    session.post = MagicMock(side_effect=AssertionError("post should not be called on cache hit"))
    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")

    response = await client.chat_completions(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.0,
    )

    assert response == cached


def _mock_response(*, status: int = 200, json_value=None, json_exc: Exception | None = None, text: str = ""):
    response = MagicMock()
    response.status = status
    response.text = AsyncMock(return_value=text)
    if json_exc is None:
        response.json = AsyncMock(return_value=json_value)
    else:
        response.json = AsyncMock(side_effect=json_exc)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    return response


@pytest.mark.asyncio
async def test_chat_completions_handles_bad_json_and_non_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "deepseek/test")

    session = MagicMock()
    session.post = MagicMock(return_value=_mock_response(status=200, json_exc=ValueError("bad json")))
    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    with pytest.raises(LLMError) as bad_json:
        await client.chat_completions(messages=[{"role": "user", "content": "hi"}])
    assert bad_json.value.code == "UPSTREAM_BAD_RESPONSE"

    session.post = MagicMock(return_value=_mock_response(status=200, json_value=["bad"]))
    with pytest.raises(LLMError) as non_dict:
        await client.chat_completions(messages=[{"role": "user", "content": "hi"}])
    assert non_dict.value.code == "UPSTREAM_BAD_RESPONSE"


@pytest.mark.asyncio
async def test_chat_completions_retries_client_errors_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "deepseek/test")
    monkeypatch.setattr("riskmonitor_multiagent.llm.llm_client.asyncio.sleep", AsyncMock())

    fake_cache = MagicMock()
    fake_cache.get.return_value = None
    monkeypatch.setattr("riskmonitor_multiagent.llm.llm_client.get_llm_cache", lambda: fake_cache)

    success_payload = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    }
    post = MagicMock(
        side_effect=[
            aiohttp.ClientError("network down"),
            _mock_response(status=200, json_value=success_payload),
        ]
    )
    session = MagicMock(post=post)
    record_usage = MagicMock()
    monkeypatch.setattr("riskmonitor_multiagent.llm.token_tracker.record_token_usage", record_usage)

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    response = await client.chat_completions(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.0,
    )

    assert response == success_payload
    assert fake_cache.set.called
    assert record_usage.called


@pytest.mark.asyncio
async def test_chat_completions_timeout_and_dns_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "deepseek/test")
    monkeypatch.setenv("LLM_RESOLVE_IP", "1.1.1.1")
    monkeypatch.setattr("riskmonitor_multiagent.llm.llm_client.asyncio.sleep", AsyncMock())

    original_getaddrinfo = socket.getaddrinfo
    session = MagicMock()
    session.post = MagicMock(side_effect=asyncio.TimeoutError())
    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")

    with pytest.raises(LLMError) as exc:
        await client.chat_completions(messages=[{"role": "user", "content": "hi"}], use_cache=False)

    assert exc.value.code == "UPSTREAM_TIMEOUT"
    assert socket.getaddrinfo is original_getaddrinfo
