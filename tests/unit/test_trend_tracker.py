"""TrendTracker 单元测试.

测试场景:
1. record_snapshot → 正确记录快照
2. analyze_metric → 趋势方向判断正确
3. analyze_all → 分析所有核心指标
4. generate_report → 生成 Markdown 趋势报告
5. 边界情况: 空数据、单快照、自定义指标
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.prompts.trend_tracker import (
    TREND_DOWN,
    TREND_STABLE,
    TREND_UP,
    TrendAnalysis,
    TrendSnapshot,
    TrendTracker,
)


# ---------------------------------------------------------------------------
# 1. record_snapshot
# ---------------------------------------------------------------------------


class TestRecordSnapshot:
    """测试 record_snapshot."""

    def test_record_returns_snapshot(self):
        """记录快照返回 TrendSnapshot 对象."""
        tracker = TrendTracker()
        snapshot = tracker.record_snapshot(
            skill_count=10,
            memory_hit_rate=0.5,
            token_total=50_000,
        )
        assert isinstance(snapshot, TrendSnapshot)
        assert snapshot.skill_count == 10
        assert snapshot.memory_hit_rate == 0.5
        assert snapshot.token_total == 50_000

    def test_record_increments_count(self):
        """每次记录增加快照计数."""
        tracker = TrendTracker()
        tracker.record_snapshot(skill_count=1)
        tracker.record_snapshot(skill_count=2)
        tracker.record_snapshot(skill_count=3)
        assert tracker.snapshot_count == 3

    def test_record_from_dict(self):
        """从 dict 记录快照."""
        tracker = TrendTracker()
        data = {
            "skill_count": 5,
            "memory_hit_rate": 0.3,
            "token_total": 10_000,
            "token_cost": 0.5,
        }
        snapshot = tracker.record_snapshot_from_dict(data)
        assert snapshot.skill_count == 5
        assert snapshot.token_cost == 0.5

    def test_get_snapshots_returns_copy(self):
        """get_snapshots 返回列表副本."""
        tracker = TrendTracker()
        tracker.record_snapshot(skill_count=1)
        snapshots = tracker.get_snapshots()
        assert len(snapshots) == 1
        # 修改返回的列表不影响内部状态
        snapshots.clear()
        assert tracker.snapshot_count == 1


# ---------------------------------------------------------------------------
# 2. analyze_metric
# ---------------------------------------------------------------------------


class TestAnalyzeMetric:
    """测试 analyze_metric."""

    def test_upward_trend(self):
        """上升趋势正确识别."""
        tracker = TrendTracker()
        # 明显上升趋势: skill_count 从 5 增长到 25
        for i in range(7):
            tracker.record_snapshot(skill_count=5 + i * 3)
        analysis = tracker.analyze_metric("skill_count")
        assert analysis.direction == TREND_UP
        assert analysis.change_pct > 0

    def test_downward_trend(self):
        """下降趋势正确识别."""
        tracker = TrendTracker()
        # 明显下降趋势: token_total 从 100000 下降到 40000
        for i in range(7):
            tracker.record_snapshot(token_total=100_000 - i * 10_000)
        analysis = tracker.analyze_metric("token_total")
        assert analysis.direction == TREND_DOWN
        assert analysis.change_pct < 0

    def test_stable_trend(self):
        """稳定趋势正确识别."""
        tracker = TrendTracker()
        # 稳定: memory_hit_rate 在 0.5 附近小幅波动
        for _ in range(7):
            tracker.record_snapshot(memory_hit_rate=0.5)
        analysis = tracker.analyze_metric("memory_hit_rate")
        assert analysis.direction == TREND_STABLE
        assert analysis.change_pct == 0.0

    def test_analyze_nonexistent_metric_raises(self):
        """不存在的指标抛出 ValueError."""
        tracker = TrendTracker()
        tracker.record_snapshot(skill_count=1)
        with pytest.raises(ValueError, match="No data"):
            tracker.analyze_metric("nonexistent_metric_xyz")

    def test_analyze_with_custom_metrics(self):
        """自定义指标趋势分析."""
        tracker = TrendTracker()
        for i in range(5):
            tracker.record_snapshot(
                custom_metrics={"my_metric": float(10 + i * 5)}
            )
        analysis = tracker.analyze_metric("my_metric")
        assert analysis.direction == TREND_UP
        assert analysis.latest == 30.0

    def test_change_pct_calculation(self):
        """变化百分比计算正确."""
        tracker = TrendTracker()
        tracker.record_snapshot(skill_count=100)
        tracker.record_snapshot(skill_count=150)
        analysis = tracker.analyze_metric("skill_count")
        assert analysis.change_pct == 50.0


# ---------------------------------------------------------------------------
# 3. analyze_all
# ---------------------------------------------------------------------------


class TestAnalyzeAll:
    """测试 analyze_all."""

    def test_analyze_all_returns_core_metrics(self):
        """analyze_all 返回核心指标."""
        tracker = TrendTracker()
        for i in range(5):
            tracker.record_snapshot(
                skill_count=10 + i,
                memory_hit_rate=0.3 + i * 0.05,
                task_success_rate=0.5 + i * 0.1,
            )
        results = tracker.analyze_all()
        assert "skill_count" in results
        assert "memory_hit_rate" in results
        assert "task_success_rate" in results

    def test_analyze_all_empty_tracker(self):
        """空 tracker 返回空 dict."""
        tracker = TrendTracker()
        results = tracker.analyze_all()
        assert results == {}


# ---------------------------------------------------------------------------
# 4. generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    """测试 generate_report."""

    def test_report_with_no_data(self):
        """无数据时生成空报告."""
        tracker = TrendTracker()
        report = tracker.generate_report()
        assert "暂无数据" in report

    def test_report_contains_key_sections(self):
        """报告包含核心章节."""
        tracker = TrendTracker()
        for i in range(5):
            tracker.record_snapshot(
                skill_count=10 + i * 2,
                memory_hit_rate=0.3 + i * 0.1,
                token_total=100_000 - i * 10_000,
                token_cost=2.0 - i * 0.2,
                task_success_rate=0.5 + i * 0.1,
            )
        report = tracker.generate_report()
        assert "# 自我改进趋势报告" in report
        assert "## 核心指标趋势" in report
        assert "## 结论" in report

    def test_report_shows_positive_trend(self):
        """正向趋势时报告包含相应文字."""
        tracker = TrendTracker()
        for i in range(7):
            tracker.record_snapshot(
                skill_count=5 + i * 3,
                memory_hit_rate=0.2 + i * 0.1,
                task_success_rate=0.3 + i * 0.1,
            )
        report = tracker.generate_report()
        assert "正向趋势" in report

    def test_report_shows_skill_growth_curve(self):
        """报告包含 Skill 增长曲线."""
        tracker = TrendTracker()
        for i in range(5):
            tracker.record_snapshot(skill_count=10 + i * 5)
        report = tracker.generate_report()
        assert "## Skill 库增长曲线" in report

    def test_report_shows_token_cost_trend(self):
        """报告包含 Token 成本趋势."""
        tracker = TrendTracker()
        for i in range(5):
            tracker.record_snapshot(token_cost=2.0 - i * 0.3)
        report = tracker.generate_report()
        assert "## Token 成本趋势" in report


# ---------------------------------------------------------------------------
# 5. reset
# ---------------------------------------------------------------------------


class TestReset:
    """测试 reset."""

    def test_reset_clears_all_snapshots(self):
        """reset 清空所有快照."""
        tracker = TrendTracker()
        tracker.record_snapshot(skill_count=1)
        tracker.record_snapshot(skill_count=2)
        tracker.reset()
        assert tracker.snapshot_count == 0

    def test_reset_then_record(self):
        """reset 后可以继续记录."""
        tracker = TrendTracker()
        tracker.record_snapshot(skill_count=100)
        tracker.reset()
        tracker.record_snapshot(skill_count=1)
        assert tracker.snapshot_count == 1
        snapshots = tracker.get_snapshots()
        assert snapshots[0].skill_count == 1
