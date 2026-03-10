from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


@pytest.mark.asyncio
async def test_llm_chat_completions_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from riskmonitor_multiagent.llm.llm_client import LlmClient
    from riskmonitor_multiagent.llm.llm_client import extract_first_text

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "qwen3-8b")

    captured: dict[str, Any] = {}

    # 创建 mock response
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
    })
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    # 创建 mock client session
    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    # 捕获调用参数
    def capture_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        return mock_response

    mock_session.post = capture_post

    client = LlmClient(http_client=mock_session, base_url="https://api.example.com/v1")
    resp = await client.chat_completions(messages=[{"role": "user", "content": "hi"}])

    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"].get("Authorization") == "Bearer test-key"
    assert captured["headers"].get("Content-Type") == "application/json"
    assert extract_first_text(resp) == "ok"


@pytest.mark.asyncio
async def test_llm_chat_completions_non_2xx(monkeypatch: pytest.MonkeyPatch) -> None:
    from riskmonitor_multiagent.llm.llm_client import LLMError
    from riskmonitor_multiagent.llm.llm_client import LlmClient

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "qwen3-8b")

    # 创建 mock response (非 2xx 状态)
    mock_response = MagicMock()
    mock_response.status = 429
    mock_response.text = AsyncMock(return_value="rate limited")
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    # 创建 mock client session
    mock_session = MagicMock()

    def mock_post(url, **kwargs):
        return mock_response

    mock_session.post = mock_post

    client = LlmClient(http_client=mock_session, base_url="https://api.example.com/v1")
    with pytest.raises(LLMError) as exc:
        await client.chat_completions(messages=[{"role": "user", "content": "hi"}])

    assert exc.value.code == "UPSTREAM_BAD_STATUS"
    assert exc.value.status_code == 429
