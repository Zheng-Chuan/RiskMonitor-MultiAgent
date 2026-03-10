"""LLM 客户端（OpenAI 兼容）.

说明:
- 统一封装 Chat Completions 调用，可对接任意 OpenAI 兼容的 LLM 平台
- 仅负责 HTTP 调用与错误封装, 不包含业务逻辑
- 切换平台时只需更换 LLM_BASE_URL、LLM_API_KEY、LLM_MODEL
- 支持固定 IP 解析（绕过 DNS 故障节点）
"""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp

from riskmonitor_multiagent import config


@dataclass
class LLMError(RuntimeError):
    """LLM 调用异常."""

    code: str
    message: str
    status_code: Optional[int] = None
    cause: Optional[BaseException] = None

    def __str__(self) -> str:
        sc = f" status={self.status_code}" if self.status_code is not None else ""
        return f"{self.code}{sc}: {self.message}"


def _build_headers(host_header: Optional[str] = None) -> dict[str, str]:
    api_key = config.get_llm_api_key()
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if host_header:
        headers["Host"] = host_header
    http_referer = config.get_llm_http_referer()
    if http_referer:
        headers["HTTP-Referer"] = http_referer
    app_title = config.get_llm_app_title()
    if app_title:
        headers["X-Title"] = app_title
    return headers


class LlmClient:
    """LLM 异步客户端（OpenAI 兼容 API）."""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        timeout_s: float = 30.0,
        http_client: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self._base_url = (base_url or config.get_llm_base_url()).rstrip("/")
        self._timeout_s = float(timeout_s)
        self._http_client = http_client
        self._resolve_ip = config.get_llm_resolve_ip()
        self._original_getaddrinfo: Optional[Any] = None

    def _apply_dns_patch(self) -> None:
        """临时替换 socket.getaddrinfo 以支持固定 IP."""
        if self._resolve_ip and "api.n1n.ai" in self._base_url:
            self._original_getaddrinfo = socket.getaddrinfo

            def patched_getaddrinfo(host: str, port: Any, *args: Any, **kwargs: Any) -> Any:
                if host == "api.n1n.ai":
                    return [
                        (socket.AF_INET, socket.SOCK_STREAM, 0, "", (self._resolve_ip, port)),
                    ]
                return self._original_getaddrinfo(host, port, *args, **kwargs)

            socket.getaddrinfo = patched_getaddrinfo  # type: ignore[assignment]

    def _restore_dns(self) -> None:
        """恢复原始的 socket.getaddrinfo."""
        if self._original_getaddrinfo is not None:
            socket.getaddrinfo = self._original_getaddrinfo  # type: ignore[assignment]
            self._original_getaddrinfo = None

    async def chat_completions(
        self,
        *,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        调用 Chat Completions.

        参数:
            messages: 对话消息列表, 每个元素包含 role/content
            model: 可选, 覆盖默认模型
            temperature: 采样温度
            max_tokens: 可选, 最大输出 tokens

        返回:
            原始响应 JSON(dict)
        """
        if not isinstance(messages, list) or not messages:
            raise LLMError(code="INVALID_INPUT", message="messages 不能为空")

        used_model = (model or config.get_llm_model()).strip()
        if not used_model:
            raise LLMError(code="INVALID_CONFIG", message="LLM_MODEL 为空")

        payload: dict[str, Any] = {
            "model": used_model,
            "messages": messages,
            "temperature": float(temperature),
            "enable_thinking": False,
        }
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)

        # 应用 DNS 补丁（固定 IP）
        self._apply_dns_patch()

        # 准备 URL 和 headers
        url = f"{self._base_url}/chat/completions"
        host_header = "api.n1n.ai" if self._resolve_ip and "api.n1n.ai" in self._base_url else None
        headers = _build_headers(host_header=host_header)

        client = self._http_client
        should_close = False
        if client is None:
            # 增加超时：连接5秒，总时间120秒（大模型响应需要更长时间）
            timeout = aiohttp.ClientTimeout(
                total=120.0,
                connect=10.0,
                sock_read=90.0,
            )
            client = aiohttp.ClientSession(timeout=timeout)
            should_close = True

        max_attempts = 3
        last_error: Optional[LLMError] = None

        try:
            for attempt in range(max_attempts):
                try:
                    async with client.post(url, headers=headers, json=payload) as resp:
                        if resp.status < 200 or resp.status >= 300:
                            text = await resp.text()
                            err = LLMError(
                                code="UPSTREAM_BAD_STATUS",
                                message=text,
                                status_code=int(resp.status),
                            )
                            # 5xx 或 429 可重试
                            if (resp.status >= 500 or resp.status == 429) and attempt < max_attempts - 1:
                                last_error = err
                                await asyncio.sleep(1.0 * (attempt + 1))
                                continue
                            raise err

                        try:
                            data = await resp.json()
                        except Exception as e:
                            raise LLMError(
                                code="UPSTREAM_BAD_RESPONSE",
                                message="响应不是合法 JSON",
                                status_code=int(resp.status),
                                cause=e,
                            ) from e

                        if not isinstance(data, dict):
                            raise LLMError(
                                code="UPSTREAM_BAD_RESPONSE",
                                message="响应 JSON 不是对象",
                                status_code=int(resp.status),
                            )
                        return data

                except LLMError as e:
                    last_error = e
                    retryable = e.code in ("UPSTREAM_UNAVAILABLE", "UPSTREAM_TIMEOUT", "UPSTREAM_BAD_STATUS")
                    if retryable and attempt < max_attempts - 1:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    raise
                except aiohttp.ClientError as e:
                    last_error = LLMError(code="UPSTREAM_UNAVAILABLE", message=str(e), cause=e)
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    raise last_error
                except asyncio.TimeoutError as e:
                    last_error = LLMError(code="UPSTREAM_TIMEOUT", message=str(e), cause=e)
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    raise last_error

            if last_error is not None:
                raise last_error
            raise LLMError(code="UNKNOWN", message="max retries exceeded")
        finally:
            if should_close:
                await client.close()
            self._restore_dns()


def extract_first_text(response_json: dict[str, Any]) -> str:
    """
    从响应中提取第一条 assistant 文本.

    参数:
        response_json: chat/completions 返回

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
    except Exception:
        return ""
