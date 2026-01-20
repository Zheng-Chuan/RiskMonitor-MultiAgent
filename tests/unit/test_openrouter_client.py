from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

import httpx


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


@pytest.mark.asyncio
async def test_openrouter_chat_completions_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from riskmonitor_multiagent.llm.openrouter_client import OpenRouterClient, extract_first_text

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")

    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["content_type"] = request.headers.get("Content-Type")

        payload = await request.aread()
        captured["raw_body"] = payload.decode("utf-8")

        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OpenRouterClient(http_client=http_client, base_url="https://openrouter.ai/api/v1")
        resp = await client.chat_completions(messages=[{"role": "user", "content": "hi"}])

    assert captured["url"].endswith("/chat/completions")
    assert captured["auth"] == "Bearer test-key"
    assert captured["content_type"] == "application/json"
    assert extract_first_text(resp) == "ok"


@pytest.mark.asyncio
async def test_openrouter_chat_completions_non_2xx(monkeypatch: pytest.MonkeyPatch) -> None:
    from riskmonitor_multiagent.llm.openrouter_client import OpenRouterClient, OpenRouterError

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OpenRouterClient(http_client=http_client, base_url="https://openrouter.ai/api/v1")
        with pytest.raises(OpenRouterError) as exc:
            await client.chat_completions(messages=[{"role": "user", "content": "hi"}])

    assert exc.value.code == "UPSTREAM_BAD_STATUS"
    assert exc.value.status_code == 429


