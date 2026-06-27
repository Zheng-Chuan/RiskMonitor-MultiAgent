"""CostReportGenerator 单元测试.

测试场景:
1. save_baseline → 正确保存基线
2. save_baseline_from_tracker_summary → 从 TokenTracker summary 保存
3. compare → 正确计算优化百分比
4. generate_report → 生成 Markdown 报告
5. 边界情况: 零值、缺失标签
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.prompts.cost_report import (
    CostBaseline,
    CostComparisonResult,
    CostReportGenerator,
)


# ---------------------------------------------------------------------------
# 1. save_baseline
# ---------------------------------------------------------------------------


class TestSaveBaseline:
    """测试 save_baseline."""

    def test_save_baseline_returns_correct_object(self):
        """保存基线返回正确的 CostBaseline."""
        gen = CostReportGenerator()
        baseline = gen.save_baseline(
            "before",
            total_tokens=100_000,
            prompt_tokens=70_000,
            completion_tokens=30_000,
            calls=50,
            cached_calls=10,
            cache_hit_rate=0.2,
            prefix_cache_savings=5_000,
            cost_estimate=1.5,
        )
        assert baseline.label == "before"
        assert baseline.total_tokens == 100_000
        assert baseline.prompt_tokens == 70_000
        assert baseline.completion_tokens == 30_000
        assert baseline.calls == 50
        assert baseline.cache_hit_rate == 0.2
        assert baseline.avg_tokens_per_call == 2000.0

    def test_save_baseline_stored_and_retrievable(self):
        """保存的基线可通过 get_baseline 获取."""
        gen = CostReportGenerator()
        gen.save_baseline("test_label", total_tokens=500)
        retrieved = gen.get_baseline("test_label")
        assert retrieved.label == "test_label"
        assert retrieved.total_tokens == 500

    def test_save_baseline_with_tier_breakdown(self):
        """保存基线时 tier_breakdown 正确存储."""
        gen = CostReportGenerator()
        tiers = {"stable": 1000, "context": 500, "volatile": 200}
        baseline = gen.save_baseline("tiered", tier_breakdown=tiers)
        assert baseline.tier_breakdown == tiers

    def test_list_baselines(self):
        """list_baselines 返回所有已保存的标签."""
        gen = CostReportGenerator()
        gen.save_baseline("a")
        gen.save_baseline("b")
        gen.save_baseline("c")
        labels = gen.list_baselines()
        assert labels == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# 2. save_baseline_from_tracker_summary
# ---------------------------------------------------------------------------


class TestSaveBaselineFromSummary:
    """测试 save_baseline_from_tracker_summary."""

    def test_from_tracker_summary(self):
        """从 TokenTracker summary dict 正确保存."""
        gen = CostReportGenerator()
        summary = {
            "total_tokens": 200_000,
            "prompt_tokens": 150_000,
            "completion_tokens": 50_000,
            "calls": 100,
            "cached_calls": 30,
            "cache_hit_rate": 0.3,
            "prefix_cache_savings": 10_000,
            "tier_breakdown": {"stable": 80_000, "context": 40_000, "volatile": 30_000},
            "cost_estimate": 3.0,
        }
        baseline = gen.save_baseline_from_tracker_summary("from_tracker", summary)
        assert baseline.total_tokens == 200_000
        assert baseline.calls == 100
        assert baseline.cache_hit_rate == 0.3
        assert baseline.avg_tokens_per_call == 2000.0


# ---------------------------------------------------------------------------
# 3. compare
# ---------------------------------------------------------------------------


class TestCompare:
    """测试 compare."""

    def test_compare_token_reduction(self):
        """对比正确计算 token 减少百分比."""
        gen = CostReportGenerator()
        gen.save_baseline("before", total_tokens=100_000, calls=50, cost_estimate=2.0)
        gen.save_baseline("after", total_tokens=75_000, calls=50, cost_estimate=1.5)
        result = gen.compare("before", "after")
        assert result.token_reduction_pct == 25.0
        assert result.cost_reduction_pct == 25.0

    def test_compare_cache_hit_rate_improvement(self):
        """对比正确计算缓存命中率提升."""
        gen = CostReportGenerator()
        gen.save_baseline("before", cache_hit_rate=0.1, total_tokens=100_000, calls=50)
        gen.save_baseline("after", cache_hit_rate=0.4, total_tokens=80_000, calls=50)
        result = gen.compare("before", "after")
        assert result.cache_hit_rate_improvement == pytest.approx(0.3, abs=1e-6)

    def test_compare_no_reduction(self):
        """token 增加时减少百分比为负."""
        gen = CostReportGenerator()
        gen.save_baseline("before", total_tokens=50_000, calls=50)
        gen.save_baseline("after", total_tokens=60_000, calls=50)
        result = gen.compare("before", "after")
        assert result.token_reduction_pct == -20.0

    def test_compare_missing_label_raises(self):
        """缺失标签抛出 KeyError."""
        gen = CostReportGenerator()
        gen.save_baseline("exists", total_tokens=100)
        with pytest.raises(KeyError):
            gen.compare("exists", "nonexistent")
        with pytest.raises(KeyError):
            gen.compare("nonexistent", "exists")

    def test_compare_zero_baseline(self):
        """基线为 0 时百分比变化为 0."""
        gen = CostReportGenerator()
        gen.save_baseline("zero", total_tokens=0, calls=0, cost_estimate=0.0)
        gen.save_baseline("after", total_tokens=100, calls=10, cost_estimate=0.5)
        result = gen.compare("zero", "after")
        assert result.token_reduction_pct == 0.0
        assert result.cost_reduction_pct == 0.0


# ---------------------------------------------------------------------------
# 4. generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    """测试 generate_report."""

    def test_report_contains_key_sections(self):
        """报告包含核心章节."""
        gen = CostReportGenerator()
        gen.save_baseline(
            "before",
            total_tokens=100_000,
            prompt_tokens=70_000,
            completion_tokens=30_000,
            calls=50,
            cached_calls=5,
            cache_hit_rate=0.1,
            prefix_cache_savings=2_000,
            cost_estimate=2.0,
        )
        gen.save_baseline(
            "after",
            total_tokens=75_000,
            prompt_tokens=50_000,
            completion_tokens=25_000,
            calls=50,
            cached_calls=20,
            cache_hit_rate=0.4,
            prefix_cache_savings=15_000,
            tier_breakdown={"stable": 30_000, "context": 15_000, "volatile": 5_000},
            cost_estimate=1.2,
        )
        report = gen.generate_report("before", "after")
        assert "# Token 成本对比报告" in report
        assert "## 核心指标对比" in report
        assert "## 层级 Token 明细" in report
        assert "## 结论" in report

    def test_report_shows_pass_when_20pct(self):
        """token 下降 >= 20% 时显示达标."""
        gen = CostReportGenerator()
        gen.save_baseline("before", total_tokens=100_000, calls=50, cost_estimate=2.0)
        gen.save_baseline("after", total_tokens=78_000, calls=50, cost_estimate=1.5)
        report = gen.generate_report("before", "after")
        assert "达标" in report

    def test_report_shows_fail_when_below_20pct(self):
        """token 下降 < 20% 时显示未达标."""
        gen = CostReportGenerator()
        gen.save_baseline("before", total_tokens=100_000, calls=50, cost_estimate=2.0)
        gen.save_baseline("after", total_tokens=85_000, calls=50, cost_estimate=1.8)
        report = gen.generate_report("before", "after")
        assert "未达标" in report
