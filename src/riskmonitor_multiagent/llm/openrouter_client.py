"""OpenRouter LLM 客户端.

说明:
- 统一封装 OpenRouter Chat Completions 调用
- 仅负责 HTTP 调用与错误封装, 不包含业务逻辑
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx

from riskmonitor_multiagent import config


@dataclass
class OpenRouterError(RuntimeError):
    """OpenRouter 调用异常."""

    code: str
    message: str
    status_code: Optional[int] = None
    cause: Optional[BaseException] = None

    def __str__(self) -> str:
        sc = f" status={self.status_code}" if self.status_code is not None else ""
        return f"{self.code}{sc}: {self.message}"


def _build_headers() -> dict[str, str]:
    api_key = config.get_openrouter_api_key()
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    http_referer = config.get_openrouter_http_referer()
    if http_referer:
        headers["HTTP-Referer"] = http_referer
    app_title = config.get_openrouter_app_title()
    if app_title:
        headers["X-Title"] = app_title
    return headers


class OpenRouterClient:
    """OpenRouter 异步客户端."""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        timeout_s: float = 30.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = (base_url or config.get_openrouter_base_url()).rstrip("/")
        self._timeout_s = float(timeout_s)
        self._http_client = http_client

    async def chat_completions(
        self,
        *,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        调用 OpenRouter Chat Completions.

        参数:
            messages: 对话消息列表, 每个元素包含 role/content
            model: 可选, 覆盖默认模型
            temperature: 采样温度
            max_tokens: 可选, 最大输出 tokens

        返回:
            OpenRouter 原始响应 JSON(dict)
        """
        if not isinstance(messages, list) or not messages:
            raise OpenRouterError(code="INVALID_INPUT", message="messages 不能为空")

        used_model = (model or config.get_openrouter_model()).strip()
        if not used_model:
            raise OpenRouterError(code="INVALID_CONFIG", message="OPENROUTER_MODEL 为空")

        payload: dict[str, Any] = {
            "model": used_model,
            "messages": messages,
            "temperature": float(temperature),
        }
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)

        url = f"{self._base_url}/chat/completions"
        headers = _build_headers()

        client = self._http_client
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout_s)
            should_close = True

        try:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code < 200 or resp.status_code >= 300:
                raise OpenRouterError(
                    code="UPSTREAM_BAD_STATUS",
                    message=resp.text,
                    status_code=int(resp.status_code),
                )
            try:
                data = resp.json()
            except Exception as e:  # pylint: disable=broad-except
                raise OpenRouterError(
                    code="UPSTREAM_BAD_RESPONSE",
                    message="响应不是合法 JSON",
                    status_code=int(resp.status_code),
                    cause=e,
                ) from e
            if not isinstance(data, dict):
                raise OpenRouterError(
                    code="UPSTREAM_BAD_RESPONSE",
                    message="响应 JSON 不是对象",
                    status_code=int(resp.status_code),
                )
            return data
        except ValueError as e:
            raise OpenRouterError(code="INVALID_CONFIG", message=str(e), cause=e) from e
        except httpx.TimeoutException as e:
            raise OpenRouterError(code="UPSTREAM_TIMEOUT", message=str(e), cause=e) from e
        except httpx.RequestError as e:
            raise OpenRouterError(code="UPSTREAM_UNAVAILABLE", message=str(e), cause=e) from e
        finally:
            if should_close:
                await client.aclose()


def extract_first_text(response_json: dict[str, Any]) -> str:
    """
    从 OpenRouter 响应中提取第一条 assistant 文本.

    参数:
        response_json: OpenRouter chat/completions 返回

    返回:
        第一条 choice 的 message.content 文本; 若不存在返回空字符串
    """
    try:
        choices = response_json.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        message = first.get("message")
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        return content if isinstance(content, str) else ""
    except Exception:  # pylint: disable=broad-except
        return ""

