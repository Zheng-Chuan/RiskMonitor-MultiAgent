"""Token 成本对比报告.

为 Phase 8 的 "token 成本下降 20%" 成功标准提供可验证的量化依据.

功能:
- 记录基线 (三层分离前) 与当前 (三层分离后) 的 token 用量
- 生成成本对比报告 (Markdown 格式)
- 计算缓存命中率、前缀缓存节省、各层 token 明细
- 量化成本优化百分比
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CostBaseline:
    """成本基线快照.

    Attributes:
        label: 基线标签 (如 "before_tiered", "after_tiered")
        timestamp: 记录时间戳
        total_tokens: 总 token 数
        prompt_tokens: prompt token 数
        completion_tokens: completion token 数
        calls: LLM 调用次数
        cached_calls: 缓存命中次数
        cache_hit_rate: 缓存命中率
        prefix_cache_savings: 前缀缓存节省的 token 数
        tier_breakdown: 各层 token 明细
        cost_estimate: 估算成本
        avg_tokens_per_call: 平均每次调用的 token 数
    """

    label: str
    timestamp: float = field(default_factory=time.time)
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    cached_calls: int = 0
    cache_hit_rate: float = 0.0
    prefix_cache_savings: int = 0
    tier_breakdown: dict[str, int] = field(default_factory=dict)
    cost_estimate: float = 0.0
    avg_tokens_per_call: float = 0.0


@dataclass
class CostComparisonResult:
    """成本对比结果.

    Attributes:
        baseline: 基线快照
        current: 当前快照
        token_reduction_pct: token 减少百分比
        cost_reduction_pct: 成本减少百分比
        cache_hit_rate_improvement: 缓存命中率提升
        avg_tokens_per_call_reduction_pct: 平均每次调用 token 减少百分比
    """

    baseline: CostBaseline
    current: CostBaseline
    token_reduction_pct: float = 0.0
    cost_reduction_pct: float = 0.0
    cache_hit_rate_improvement: float = 0.0
    avg_tokens_per_call_reduction_pct: float = 0.0


class CostReportGenerator:
    """Token 成本对比报告生成器.

    支持:
    1. 保存基线快照 (三层分离前的 token 用量)
    2. 保存当前快照 (三层分离后的 token 用量)
    3. 对比两个快照, 计算优化百分比
    4. 生成 Markdown 格式的成本报告
    """

    def __init__(self) -> None:
        """初始化报告生成器."""
        # label -> CostBaseline
        self._baselines: dict[str, CostBaseline] = {}

    def save_baseline(
        self,
        label: str,
        *,
        total_tokens: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        calls: int = 0,
        cached_calls: int = 0,
        cache_hit_rate: float = 0.0,
        prefix_cache_savings: int = 0,
        tier_breakdown: dict[str, int] | None = None,
        cost_estimate: float = 0.0,
    ) -> CostBaseline:
        """保存成本基线快照.

        Args:
            label: 基线标签
            total_tokens: 总 token 数
            prompt_tokens: prompt token 数
            completion_tokens: completion token 数
            calls: LLM 调用次数
            cached_calls: 缓存命中次数
            cache_hit_rate: 缓存命中率
            prefix_cache_savings: 前缀缓存节省 token 数
            tier_breakdown: 各层 token 明细
            cost_estimate: 估算成本

        Returns:
            创建的 CostBaseline
        """
        avg = total_tokens / calls if calls > 0 else 0.0
        baseline = CostBaseline(
            label=label,
            total_tokens=int(total_tokens),
            prompt_tokens=int(prompt_tokens),
            completion_tokens=int(completion_tokens),
            calls=int(calls),
            cached_calls=int(cached_calls),
            cache_hit_rate=float(cache_hit_rate),
            prefix_cache_savings=int(prefix_cache_savings),
            tier_breakdown=dict(tier_breakdown or {}),
            cost_estimate=float(cost_estimate),
            avg_tokens_per_call=avg,
        )
        self._baselines[label] = baseline
        logger.info("Saved cost baseline: %s (total_tokens=%d)", label, baseline.total_tokens)
        return baseline

    def save_baseline_from_tracker_summary(
        self,
        label: str,
        summary: dict[str, Any],
    ) -> CostBaseline:
        """从 TokenTracker.summary() 输出保存基线.

        Args:
            label: 基线标签
            summary: TokenTracker.summary() 返回的 dict

        Returns:
            创建的 CostBaseline
        """
        return self.save_baseline(
            label,
            total_tokens=summary.get("total_tokens", 0),
            prompt_tokens=summary.get("prompt_tokens", 0),
            completion_tokens=summary.get("completion_tokens", 0),
            calls=summary.get("calls", 0),
            cached_calls=summary.get("cached_calls", 0),
            cache_hit_rate=summary.get("cache_hit_rate", 0.0),
            prefix_cache_savings=summary.get("prefix_cache_savings", 0),
            tier_breakdown=summary.get("tier_breakdown"),
            cost_estimate=summary.get("cost_estimate", 0.0),
        )

    def compare(self, baseline_label: str, current_label: str) -> CostComparisonResult:
        """对比两个基线.

        Args:
            baseline_label: 基线标签 (如 "before_tiered")
            current_label: 当前标签 (如 "after_tiered")

        Returns:
            CostComparisonResult

        Raises:
            KeyError: 标签不存在
        """
        baseline = self._baselines.get(baseline_label)
        if baseline is None:
            raise KeyError(f"Baseline not found: {baseline_label}")
        current = self._baselines.get(current_label)
        if current is None:
            raise KeyError(f"Baseline not found: {current_label}")

        # token 减少百分比
        if baseline.total_tokens > 0:
            token_reduction_pct = (
                (baseline.total_tokens - current.total_tokens) / baseline.total_tokens
            ) * 100.0
        else:
            token_reduction_pct = 0.0

        # 成本减少百分比
        if baseline.cost_estimate > 0:
            cost_reduction_pct = (
                (baseline.cost_estimate - current.cost_estimate) / baseline.cost_estimate
            ) * 100.0
        else:
            cost_reduction_pct = 0.0

        # 缓存命中率提升
        cache_hit_rate_improvement = current.cache_hit_rate - baseline.cache_hit_rate

        # 平均每次调用 token 减少百分比
        if baseline.avg_tokens_per_call > 0:
            avg_reduction_pct = (
                (baseline.avg_tokens_per_call - current.avg_tokens_per_call)
                / baseline.avg_tokens_per_call
            ) * 100.0
        else:
            avg_reduction_pct = 0.0

        return CostComparisonResult(
            baseline=baseline,
            current=current,
            token_reduction_pct=round(token_reduction_pct, 2),
            cost_reduction_pct=round(cost_reduction_pct, 2),
            cache_hit_rate_improvement=round(cache_hit_rate_improvement, 4),
            avg_tokens_per_call_reduction_pct=round(avg_reduction_pct, 2),
        )

    def generate_report(
        self,
        baseline_label: str,
        current_label: str,
    ) -> str:
        """生成 Markdown 格式的成本对比报告.

        Args:
            baseline_label: 基线标签
            current_label: 当前标签

        Returns:
            Markdown 格式的报告文本
        """
        result = self.compare(baseline_label, current_label)
        b = result.baseline
        c = result.current

        lines: list[str] = []
        lines.append("# Token 成本对比报告")
        lines.append("")
        lines.append(f"- 基线: {b.label} (tokens={b.total_tokens})")
        lines.append(f"- 当前: {c.label} (tokens={c.total_tokens})")
        lines.append("")

        # 核心指标对比表
        lines.append("## 核心指标对比")
        lines.append("")
        lines.append("| 指标 | 基线 | 当前 | 变化 |")
        lines.append("|------|------|------|------|")
        lines.append(
            f"| 总 Token | {b.total_tokens:,} | {c.total_tokens:,} | "
            f"{result.token_reduction_pct:+.2f}% |"
        )
        lines.append(
            f"| Prompt Token | {b.prompt_tokens:,} | {c.prompt_tokens:,} | "
            f"{self._pct_change(b.prompt_tokens, c.prompt_tokens):+.2f}% |"
        )
        lines.append(
            f"| Completion Token | {b.completion_tokens:,} | {c.completion_tokens:,} | "
            f"{self._pct_change(b.completion_tokens, c.completion_tokens):+.2f}% |"
        )
        lines.append(
            f"| LLM 调用次数 | {b.calls:,} | {c.calls:,} | "
            f"{self._pct_change(b.calls, c.calls):+.2f}% |"
        )
        lines.append(
            f"| 缓存命中率 | {b.cache_hit_rate:.2%} | {c.cache_hit_rate:.2%} | "
            f"{result.cache_hit_rate_improvement:+.2%} |"
        )
        lines.append(
            f"| 前缀缓存节省 | {b.prefix_cache_savings:,} | {c.prefix_cache_savings:,} | "
            f"{self._pct_change(b.prefix_cache_savings, c.prefix_cache_savings):+.2f}% |"
        )
        lines.append(
            f"| 估算成本 | {b.cost_estimate:.4f} | {c.cost_estimate:.4f} | "
            f"{result.cost_reduction_pct:+.2f}% |"
        )
        lines.append(
            f"| 平均 Token/调用 | {b.avg_tokens_per_call:,.1f} | {c.avg_tokens_per_call:,.1f} | "
            f"{result.avg_tokens_per_call_reduction_pct:+.2f}% |"
        )
        lines.append("")

        # 层级明细
        if c.tier_breakdown:
            lines.append("## 层级 Token 明细 (当前)")
            lines.append("")
            for tier_name, tier_tokens in sorted(c.tier_breakdown.items()):
                lines.append(f"- **{tier_name}**: {tier_tokens:,} tokens")
            lines.append("")

        # 结论
        lines.append("## 结论")
        lines.append("")
        if result.token_reduction_pct >= 20.0:
            lines.append(
                f"> **达标**: Token 总消耗下降 {result.token_reduction_pct:.2f}%, "
                f"超过 20% 目标."
            )
        else:
            lines.append(
                f"> **未达标**: Token 总消耗下降 {result.token_reduction_pct:.2f}%, "
                f"未达到 20% 目标."
            )
        lines.append("")
        if result.cache_hit_rate_improvement > 0:
            lines.append(
                f"> 缓存命中率提升 {result.cache_hit_rate_improvement:.2%}, "
                f"前缀缓存额外节省 {c.prefix_cache_savings:,} tokens."
            )
        lines.append("")

        report_text = "\n".join(lines)
        logger.info(
            "Generated cost report: %s vs %s, token_reduction=%.2f%%",
            baseline_label,
            current_label,
            result.token_reduction_pct,
        )
        return report_text

    def get_baseline(self, label: str) -> CostBaseline:
        """获取已保存的基线.

        Args:
            label: 基线标签

        Returns:
            CostBaseline

        Raises:
            KeyError: 标签不存在
        """
        baseline = self._baselines.get(label)
        if baseline is None:
            raise KeyError(f"Baseline not found: {label}")
        return baseline

    def list_baselines(self) -> list[str]:
        """列出所有已保存的基线标签."""
        return list(self._baselines.keys())

    @staticmethod
    def _pct_change(old: int | float, new: int | float) -> float:
        """计算百分比变化."""
        if old > 0:
            return ((new - old) / old) * 100.0
        return 0.0


__all__ = [
    "CostBaseline",
    "CostComparisonResult",
    "CostReportGenerator",
]
