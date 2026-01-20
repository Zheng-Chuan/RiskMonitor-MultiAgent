"""HTTP 场景的鉴权辅助函数."""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional


def _expected_token() -> Optional[str]:
    token = os.getenv("RISKMONITOR_API_TOKEN")
    if token is None or not token.strip():
        return None
    return token.strip()


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if authorization is None:
        return None
    value = authorization.strip()
    if not value:
        return None
    if value.lower().startswith("bearer "):
        return value[7:].strip() or None
    return None


def is_authorized(headers: Mapping[str, Any]) -> bool:
    """基于 Bearer Token 的最小鉴权校验."""
    expected = _expected_token()
    if expected is None:
        return True
    auth = headers.get("authorization") or headers.get("Authorization")
    token = _extract_bearer(str(auth) if auth is not None else None)
    return token == expected


def get_headers_from_ctx(ctx: Any) -> dict[str, Any]:
    """从 FastMCP Context 中尽最大努力提取 HTTP headers."""
    request_context = getattr(ctx, "request_context", None)
    if request_context is None:
        return {}

    request = getattr(request_context, "request", None)
    headers = getattr(request, "headers", None)
    if headers is not None:
        try:
            return dict(headers)
        except Exception:  # pylint: disable=broad-except
            return {}

    headers = getattr(request_context, "headers", None)
    if headers is not None:
        try:
            return dict(headers)
        except Exception:  # pylint: disable=broad-except
            return {}

    return {}
