"""Exposure 计算.

说明:
- 只包含纯计算逻辑
- 不涉及 IO, 便于单测
"""

from __future__ import annotations

from typing import Any, Optional


def to_float(value: Any) -> Optional[float]:
    """
    将任意输入安全转换为 float.
    如果转换失败或为 None, 返回 None.
    """
    # 将输入尽量转换为 float
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def compute_position_pv_usd(position: dict[str, Any], snapshot: dict[str, Any]) -> float:
    """
    计算单笔头寸的美元现值 (PV).
    公式: PV = quantity * price * fx_rate

    Args:
        position: 头寸字典 (需包含 quantity, security_id, currency)
        snapshot: 市场快照字典 (需包含 prices, fx_rates)

    Returns:
        计算出的 PV (USD)
    """
    # 简化 PV 计算: quantity * price * fx
    security_id = position.get("security_id")
    currency = position.get("currency") or "USD"
    quantity = to_float(position.get("quantity")) or 0.0

    prices = snapshot.get("prices") if isinstance(snapshot.get("prices"), dict) else {}
    fx_rates = snapshot.get("fx_rates") if isinstance(snapshot.get("fx_rates"), dict) else {}

    price = to_float(prices.get(security_id))
    if price is None:
        price = 0.0

    fx = to_float(fx_rates.get(currency))
    if fx is None:
        fx = 1.0

    return float(quantity * price * fx)
