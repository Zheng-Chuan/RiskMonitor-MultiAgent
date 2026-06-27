"""自我改进趋势追踪.

为 Phase 8 的 "7天连续运行自我改进趋势" 成功标准提供可验证的量化依据.

功能:
- 定期记录系统关键指标快照 (Skill 积累、记忆质量、规划效率、Token 成本)
- 分析各指标的趋势方向 (上升 / 下降 / 稳定)
- 生成趋势报告 (Markdown 格式)
"""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 趋势方向常量
TREND_UP = "up"
TREND_DOWN = "down"
TREND_STABLE = "stable"


@dataclass
class TrendSnapshot:
    """单次指标快照.

    Attributes:
        timestamp: 记录时间戳
        skill_count: Skill 库总数
        skill_avg_confidence: Skill 平均置信度
        skill_active_count: 活跃 Skill 数量
        memory_hit_rate: 记忆命中率
        memory_usefulness: 记忆有用性评分 (0-1)
        planning_success_rate: 规划成功率
        planning_avg_steps: 规划平均步骤数
        token_total: 总 token 消耗
        token_cost: token 成本
        token_cache_hit_rate: token 缓存命中率
        task_success_rate: 任务完成率
        custom_metrics: 自定义指标
    """

    timestamp: float = field(default_factory=time.time)
    skill_count: int = 0
    skill_avg_confidence: float = 0.0
    skill_active_count: int = 0
    memory_hit_rate: float = 0.0
    memory_usefulness: float = 0.0
    planning_success_rate: float = 0.0
    planning_avg_steps: float = 0.0
    token_total: int = 0
    token_cost: float = 0.0
    token_cache_hit_rate: float = 0.0
    task_success_rate: float = 0.0
    custom_metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class TrendAnalysis:
    """单个指标的趋势分析结果.

    Attributes:
        metric_name: 指标名称
        direction: 趋势方向 (up / down / stable)
        values: 历史值列表
        latest: 最新值
        change_pct: 变化百分比 (相对第一个值)
    """

    metric_name: str
    direction: str
    values: list[float]
    latest: float
    change_pct: float = 0.0


class TrendTracker:
    """自我改进趋势追踪器.

    定期记录系统关键指标快照, 分析趋势方向, 生成趋势报告.
    数据存储在内存中, 按时间顺序排列.
    """

    def __init__(self) -> None:
        """初始化趋势追踪器."""
        self._snapshots: list[TrendSnapshot] = []

    def record_snapshot(
        self,
        *,
        timestamp: float | None = None,
        skill_count: int = 0,
        skill_avg_confidence: float = 0.0,
        skill_active_count: int = 0,
        memory_hit_rate: float = 0.0,
        memory_usefulness: float = 0.0,
        planning_success_rate: float = 0.0,
        planning_avg_steps: float = 0.0,
        token_total: int = 0,
        token_cost: float = 0.0,
        token_cache_hit_rate: float = 0.0,
        task_success_rate: float = 0.0,
        custom_metrics: dict[str, float] | None = None,
    ) -> TrendSnapshot:
        """记录一次指标快照.

        Args:
            timestamp: 时间戳 (默认当前时间)
            skill_count: Skill 库总数
            skill_avg_confidence: Skill 平均置信度
            skill_active_count: 活跃 Skill 数量
            memory_hit_rate: 记忆命中率
            memory_usefulness: 记忆有用性评分
            planning_success_rate: 规划成功率
            planning_avg_steps: 规划平均步骤数
            token_total: 总 token 消耗
            token_cost: token 成本
            token_cache_hit_rate: token 缓存命中率
            task_success_rate: 任务完成率
            custom_metrics: 自定义指标

        Returns:
            创建的 TrendSnapshot
        """
        snapshot = TrendSnapshot(
            timestamp=timestamp if timestamp is not None else time.time(),
            skill_count=int(skill_count),
            skill_avg_confidence=float(skill_avg_confidence),
            skill_active_count=int(skill_active_count),
            memory_hit_rate=float(memory_hit_rate),
            memory_usefulness=float(memory_usefulness),
            planning_success_rate=float(planning_success_rate),
            planning_avg_steps=float(planning_avg_steps),
            token_total=int(token_total),
            token_cost=float(token_cost),
            token_cache_hit_rate=float(token_cache_hit_rate),
            task_success_rate=float(task_success_rate),
            custom_metrics=dict(custom_metrics or {}),
        )
        self._snapshots.append(snapshot)
        logger.info(
            "Recorded trend snapshot #%d: skills=%d, memory_hit=%.2f%%, tokens=%d",
            len(self._snapshots),
            snapshot.skill_count,
            snapshot.memory_hit_rate * 100,
            snapshot.token_total,
        )
        return snapshot

    def record_snapshot_from_dict(self, data: dict[str, Any]) -> TrendSnapshot:
        """从 dict 记录快照 (便捷方法).

        支持从 TokenTracker.summary() 等返回的 dict 直接记录.

        Args:
            data: 指标数据 dict

        Returns:
            创建的 TrendSnapshot
        """
        return self.record_snapshot(
            timestamp=data.get("timestamp"),
            skill_count=data.get("skill_count", 0),
            skill_avg_confidence=data.get("skill_avg_confidence", 0.0),
            skill_active_count=data.get("skill_active_count", 0),
            memory_hit_rate=data.get("memory_hit_rate", 0.0),
            memory_usefulness=data.get("memory_usefulness", 0.0),
            planning_success_rate=data.get("planning_success_rate", 0.0),
            planning_avg_steps=data.get("planning_avg_steps", 0.0),
            token_total=data.get("token_total", 0),
            token_cost=data.get("token_cost", 0.0),
            token_cache_hit_rate=data.get("token_cache_hit_rate", 0.0),
            task_success_rate=data.get("task_success_rate", 0.0),
            custom_metrics=data.get("custom_metrics"),
        )

    @property
    def snapshot_count(self) -> int:
        """已记录的快照数量."""
        return len(self._snapshots)

    def get_snapshots(self) -> list[TrendSnapshot]:
        """获取所有快照 (按时间顺序)."""
        return list(self._snapshots)

    def analyze_metric(self, metric_name: str) -> TrendAnalysis:
        """分析单个指标的趋势.

        使用简单线性回归斜率判断趋势方向.
        变化百分比相对第一个数据点计算.

        Args:
            metric_name: 指标名称 (TrendSnapshot 的字段名)

        Returns:
            TrendAnalysis

        Raises:
            ValueError: 指标名称不存在或无数据
        """
        values = self._extract_metric_values(metric_name)
        if not values:
            raise ValueError(f"No data for metric: {metric_name}")

        direction = self._compute_direction(values)
        first_val = values[0]
        latest_val = values[-1]
        if first_val > 0:
            change_pct = ((latest_val - first_val) / first_val) * 100.0
        elif first_val == 0 and latest_val > 0:
            change_pct = 100.0
        else:
            change_pct = 0.0

        return TrendAnalysis(
            metric_name=metric_name,
            direction=direction,
            values=values,
            latest=latest_val,
            change_pct=round(change_pct, 2),
        )

    def analyze_all(self) -> dict[str, TrendAnalysis]:
        """分析所有核心指标的趋势.

        Returns:
            {metric_name: TrendAnalysis} 字典
        """
        core_metrics = [
            "skill_count",
            "skill_avg_confidence",
            "memory_hit_rate",
            "memory_usefulness",
            "planning_success_rate",
            "task_success_rate",
            "token_cache_hit_rate",
        ]
        results: dict[str, TrendAnalysis] = {}
        for metric in core_metrics:
            try:
                results[metric] = self.analyze_metric(metric)
            except ValueError:
                continue
        return results

    def generate_report(self) -> str:
        """生成 Markdown 格式的趋势报告.

        Returns:
            Markdown 格式的趋势报告文本
        """
        if not self._snapshots:
            return "# 趋势报告\n\n> 暂无数据.\n"

        lines: list[str] = []
        lines.append("# 自我改进趋势报告")
        lines.append("")
        lines.append(f"- 快照数量: {len(self._snapshots)}")
        if len(self._snapshots) >= 2:
            first_ts = self._snapshots[0].timestamp
            last_ts = self._snapshots[-1].timestamp
            duration_hours = (last_ts - first_ts) / 3600.0
            lines.append(f"- 时间跨度: {duration_hours:.1f} 小时")
        lines.append("")

        # 核心指标趋势表
        analyses = self.analyze_all()
        if analyses:
            lines.append("## 核心指标趋势")
            lines.append("")
            lines.append("| 指标 | 最新值 | 变化 | 趋势 |")
            lines.append("|------|--------|------|------|")
            for metric_name, analysis in analyses.items():
                display_name = self._metric_display_name(metric_name)
                if metric_name in ("skill_count",):
                    latest_str = f"{analysis.latest:.0f}"
                else:
                    latest_str = f"{analysis.latest:.2%}" if analysis.latest <= 1.0 else f"{analysis.latest:.2f}"
                change_str = f"{analysis.change_pct:+.2f}%"
                trend_icon = {
                    TREND_UP: "📈 上升",
                    TREND_DOWN: "📉 下降",
                    TREND_STABLE: "➡️ 稳定",
                }.get(analysis.direction, analysis.direction)
                lines.append(f"| {display_name} | {latest_str} | {change_str} | {trend_icon} |")
            lines.append("")

        # Skill 积累趋势
        skill_values = self._extract_metric_values("skill_count")
        if len(skill_values) >= 2:
            lines.append("## Skill 库增长曲线")
            lines.append("")
            for i, val in enumerate(skill_values):
                bar = "█" * max(1, int(val / max(skill_values) * 20)) if max(skill_values) > 0 else ""
                lines.append(f"- 快照 {i + 1}: {val} {bar}")
            lines.append("")

        # Token 成本趋势
        cost_values = self._extract_metric_values("token_cost")
        if len(cost_values) >= 2 and any(v > 0 for v in cost_values):
            lines.append("## Token 成本趋势")
            lines.append("")
            for i, val in enumerate(cost_values):
                lines.append(f"- 快照 {i + 1}: {val:.4f}")
            lines.append("")

        # 结论
        lines.append("## 结论")
        lines.append("")
        improving_count = sum(1 for a in analyses.values() if a.direction == TREND_UP)
        stable_count = sum(1 for a in analyses.values() if a.direction == TREND_STABLE)
        declining_count = sum(1 for a in analyses.values() if a.direction == TREND_DOWN)

        if improving_count > declining_count:
            lines.append(
                f"> **正向趋势**: {improving_count} 项指标上升, "
                f"{stable_count} 项稳定, {declining_count} 项下降. "
                f"系统呈现自我改进趋势."
            )
        elif improving_count == declining_count:
            lines.append(
                f"> **平稳趋势**: {improving_count} 项上升, "
                f"{stable_count} 项稳定, {declining_count} 项下降."
            )
        else:
            lines.append(
                f"> **需要关注**: {improving_count} 项上升, "
                f"{stable_count} 项稳定, {declining_count} 项下降."
            )
        lines.append("")

        report_text = "\n".join(lines)
        logger.info(
            "Generated trend report: %d snapshots, %d metrics analyzed",
            len(self._snapshots),
            len(analyses),
        )
        return report_text

    def reset(self) -> None:
        """重置所有快照数据 (测试用)."""
        self._snapshots.clear()
        logger.info("Trend tracker reset")

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #
    def _extract_metric_values(self, metric_name: str) -> list[float]:
        """从快照序列中提取指定指标的值."""
        values: list[float] = []
        for snapshot in self._snapshots:
            if hasattr(snapshot, metric_name):
                val = getattr(snapshot, metric_name)
                if isinstance(val, (int, float)):
                    values.append(float(val))
            elif metric_name in snapshot.custom_metrics:
                values.append(float(snapshot.custom_metrics[metric_name]))
        return values

    @staticmethod
    def _compute_direction(values: list[float]) -> str:
        """使用简单线性回归斜率判断趋势方向.

        斜率 > 5% 均值 → up
        斜率 < -5% 均值 → down
        否则 → stable
        """
        n = len(values)
        if n < 2:
            return TREND_STABLE

        # 简单线性回归: slope = (n*Σ(xy) - Σx*Σy) / (n*Σ(x²) - (Σx)²)
        xs = list(range(n))
        sum_x = sum(xs)
        sum_y = sum(values)
        sum_xy = sum(x * y for x, y in zip(xs, values))
        sum_x2 = sum(x * x for x in xs)

        denom = n * sum_x2 - sum_x * sum_x
        if denom == 0:
            return TREND_STABLE

        slope = (n * sum_xy - sum_x * sum_y) / denom

        # 用均值的 5% 作为阈值判断
        mean_val = statistics.mean(abs(v) for v in values) if values else 0.0
        if mean_val == 0:
            # 所有值都是 0, 看斜率本身
            if slope > 0:
                return TREND_UP
            elif slope < 0:
                return TREND_DOWN
            return TREND_STABLE

        relative_slope = slope / mean_val
        if relative_slope > 0.05:
            return TREND_UP
        elif relative_slope < -0.05:
            return TREND_DOWN
        return TREND_STABLE

    @staticmethod
    def _metric_display_name(metric_name: str) -> str:
        """指标名称的中文显示名."""
        names = {
            "skill_count": "Skill 总数",
            "skill_avg_confidence": "Skill 平均置信度",
            "memory_hit_rate": "记忆命中率",
            "memory_usefulness": "记忆有用性",
            "planning_success_rate": "规划成功率",
            "task_success_rate": "任务完成率",
            "token_cache_hit_rate": "Token 缓存命中率",
        }
        return names.get(metric_name, metric_name)


__all__ = [
    "TREND_UP",
    "TREND_DOWN",
    "TREND_STABLE",
    "TrendSnapshot",
    "TrendAnalysis",
    "TrendTracker",
]
