"""Market snapshot 数据访问.

说明:
- 封装 market snapshot 的 HTTP 获取
- 提供超时与重试
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

import httpx

from riskmonitor_mcp.data_access.errors import map_http_error

def get_market_snapshot_timeout_s() -> float:
    """从环境变量读取超时配置 (秒)."""
    # 从环境变量读取超时配置
    return float(os.getenv("MARKET_SNAPSHOT_TIMEOUT", "2"))


def get_market_snapshot_retries() -> int:
    """从环境变量读取重试次数."""
    # 从环境变量读取重试次数
    return int(os.getenv("MARKET_SNAPSHOT_RETRIES", "2"))


async def fetch_market_snapshot(url: str, request_id: str) -> dict[str, Any]:
    """
    获取市场快照 (Market Snapshot).
    支持超时和重试机制.

    Args:
        url: 市场快照服务的 URL
        request_id: 请求追踪 ID (未使用, 但保留接口兼容)

    Returns:
        快照数据字典

    Raises:
        DataAccessError: 如果请求失败或超时
    """
    # 获取 market snapshot, 并校验 JSON 结构为 dict
    del request_id
    timeout_s = get_market_snapshot_timeout_s()
    retries = get_market_snapshot_retries()

    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict):
                    raise ValueError("market snapshot response must be a JSON object")
                return data
        except Exception as e:  # pylint: disable=broad-except
            last_error = e
            await asyncio.sleep(min(0.2 * (attempt + 1), 1.0))

    raise map_http_error(last_error or RuntimeError("unknown"), operation="fetch_market_snapshot")
