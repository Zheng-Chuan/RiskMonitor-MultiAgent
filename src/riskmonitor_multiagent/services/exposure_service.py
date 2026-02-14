"""敞口计算服务层.

说明:
- 聚合头寸与行情快照, 计算交易台敞口
- 只包含纯计算逻辑, 不做数据库或 HTTP IO
"""

from __future__ import annotations

from typing import Any

from riskmonitor_multiagent.services.exposure_compute import (
    compute_position_pv_usd,
    to_float,
)


def compute_exposure(
    positions: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> tuple[float, float, dict[str, dict[str, float]]]:
    """
    计算组合风险敞口.
    聚合所有头寸的 Delta 和 PV, 并按币种分组.

    参数:
        positions: 头寸列表
        snapshot: 市场快照

    返回:
        (total_delta, total_pv_usd, by_currency_map)
        - total_delta: 组合总 Delta
        - total_pv_usd: 组合总 PV(USD)
        - by_currency_map: 按币种聚合的 Delta 和 PV
    """
    # 聚合计算总 Delta,总 PV, 并按币种汇总
    total_delta = 0.0
    total_pv_usd = 0.0
    by_currency: dict[str, dict[str, float]] = {}

    for pos in positions:
        delta = to_float(pos.get("delta")) or 0.0
        currency = (pos.get("currency") or "USD").strip()
        pv_usd = compute_position_pv_usd(pos, snapshot)

        total_delta += float(delta)
        total_pv_usd += float(pv_usd)

        cur_item = by_currency.get(currency)
        if cur_item is None:
            cur_item = {"delta": 0.0, "pv_usd": 0.0}
            by_currency[currency] = cur_item
        cur_item["delta"] += float(delta)
        cur_item["pv_usd"] += float(pv_usd)

    return float(total_delta), float(total_pv_usd), by_currency
