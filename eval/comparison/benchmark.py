"""
对比分析模块.

提供两种对比:
1. 历史版本对比: 与上次评估结果对比
2. 业界基准对比: 与 GAIA、MultiAgentBench、PlanBench 等对比
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eval.core.evaluator import EvaluationResult

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkReference:
    """业界基准参考数据."""
    
    name: str
    source: str
    metrics: dict[str, float]
    description: str = ""


BENCHMARK_REFERENCES: list[BenchmarkReference] = [
    BenchmarkReference(
        name="GAIA",
        source="https://arxiv.org/abs/2311.12983",
        metrics={
            "task_accuracy": 0.45,
            "reasoning_quality": 0.52,
            "tool_usage": 0.48,
        },
        description="GPT-4 performance on GAIA benchmark",
    ),
    BenchmarkReference(
        name="MultiAgentBench",
        source="ACL 2025",
        metrics={
            "collaboration_score": 0.65,
            "information_diversity": 0.42,
            "role_specialization": 0.58,
        },
        description="Multi-agent collaboration benchmark",
    ),
    BenchmarkReference(
        name="PlanBench",
        source="https://arxiv.org/abs/2306.04836",
        metrics={
            "plan_correctness": 0.58,
            "execution_success": 0.61,
            "reasoning_depth": 0.55,
        },
        description="Planning and execution benchmark",
    ),
    BenchmarkReference(
        name="AgentBench",
        source="https://arxiv.org/abs/2308.03688",
        metrics={
            "task_completion": 0.52,
            "reasoning": 0.48,
            "tool_usage": 0.45,
        },
        description="Comprehensive agent benchmark",
    ),
]


class HistoryComparator:
    """历史版本对比器."""
    
    def __init__(self, history_dir: str | Path = "eval/results") -> None:
        """
        初始化历史对比器.
        
        Args:
            history_dir: 历史结果目录
        """
        self._history_dir = Path(history_dir)
    
    def load_history(self, run_id: str | None = None) -> EvaluationResult | None:
        """
        加载历史评估结果.
        
        Args:
            run_id: 运行 ID,如果为 None 则加载最新的
            
        Returns:
            历史评估结果
        """
        if run_id:
            path = self._history_dir / f"{run_id}.json"
            if path.exists():
                return self._load_result(path)
            return None
        
        json_files = sorted(self._history_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        
        for path in json_files[:5]:
            try:
                result = self._load_result(path)
                if result and result.run_id:
                    return result
            except Exception as e:
                logger.warning(f"Failed to load {path}: {e}")
        
        return None
    
    def _load_result(self, path: Path) -> EvaluationResult | None:
        """从文件加载评估结果."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            from eval.core.metrics import OverallMetrics
            from eval.core.evaluator import CaseResult
            
            metrics = OverallMetrics()
            if "metrics" in data:
                m = data["metrics"]
                metrics.task_accuracy.intent_match_score = m.get("task_accuracy", {}).get("intent_match_score", 0)
                metrics.task_accuracy.plan_correctness = m.get("task_accuracy", {}).get("plan_correctness", 0)
                metrics.task_accuracy.execution_success_rate = m.get("task_accuracy", {}).get("execution_success_rate", 0)
                metrics.task_accuracy.answer_quality = m.get("task_accuracy", {}).get("answer_quality", 0)
                
                metrics.collaboration.agent_participation_rate = m.get("collaboration", {}).get("agent_participation_rate", 0)
                metrics.collaboration.information_diversity = m.get("collaboration", {}).get("information_diversity", 0)
                metrics.collaboration.role_specialization = m.get("collaboration", {}).get("role_specialization", 0)
                
                metrics.efficiency.latency_ms = m.get("efficiency", {}).get("latency_ms", 0)
                metrics.efficiency.token_count = m.get("efficiency", {}).get("token_count", 0)
                
                metrics.reasoning.thought_relevance = m.get("reasoning", {}).get("thought_relevance", 0)
                metrics.reasoning.reasoning_validity = m.get("reasoning", {}).get("reasoning_validity", 0)
                metrics.reasoning.evidence_support = m.get("reasoning", {}).get("evidence_support", 0)
            
            return EvaluationResult(
                run_id=data.get("run_id", ""),
                timestamp=data.get("timestamp", ""),
                config=data.get("config", {}),
                total_cases=data.get("summary", {}).get("total_cases", 0),
                passed_cases=data.get("summary", {}).get("passed_cases", 0),
                failed_cases=data.get("summary", {}).get("failed_cases", 0),
                overall_metrics=metrics,
            )
        except Exception as e:
            logger.warning(f"Failed to parse result from {path}: {e}")
            return None
    
    def compare(
        self,
        current: EvaluationResult,
        history: EvaluationResult | None = None,
    ) -> dict[str, Any]:
        """
        对比当前结果与历史结果.
        
        Args:
            current: 当前评估结果
            history: 历史评估结果,如果为 None 则自动加载
            
        Returns:
            对比结果
        """
        if history is None:
            history = self.load_history()
        
        if history is None:
            return {
                "status": "no_history",
                "message": "No history result found for comparison",
            }
        
        comparison: dict[str, Any] = {
            "current_run_id": current.run_id,
            "history_run_id": history.run_id,
            "changes": {},
            "improvements": [],
            "regressions": [],
        }
        
        def compare_value(name: str, current_val: float, history_val: float, higher_better: bool = True) -> None:
            change = current_val - history_val
            comparison["changes"][name] = {
                "current": round(current_val, 4),
                "history": round(history_val, 4),
                "change": round(change, 4),
                "change_percent": round(change / history_val * 100, 2) if history_val != 0 else 0,
            }
            
            if abs(change) > 0.01:
                if (higher_better and change > 0) or (not higher_better and change < 0):
                    comparison["improvements"].append(f"{name}: +{change:.2%}")
                else:
                    comparison["regressions"].append(f"{name}: {change:.2%}")
        
        compare_value("pass_rate", current.pass_rate, history.pass_rate)
        compare_value("overall_score", current.overall_metrics.overall_score, history.overall_metrics.overall_score)
        compare_value("task_accuracy", current.overall_metrics.task_accuracy.overall_accuracy, history.overall_metrics.task_accuracy.overall_accuracy)
        compare_value("collaboration", current.overall_metrics.collaboration.overall_collaboration, history.overall_metrics.collaboration.overall_collaboration)
        compare_value("reasoning", current.overall_metrics.reasoning.overall_reasoning, history.overall_metrics.reasoning.overall_reasoning)
        
        compare_value("latency_ms", current.overall_metrics.efficiency.latency_ms, history.overall_metrics.efficiency.latency_ms, higher_better=False)
        compare_value("token_count", current.overall_metrics.efficiency.token_count, history.overall_metrics.efficiency.token_count, higher_better=False)
        
        return comparison


class BenchmarkComparator:
    """业界基准对比器."""
    
    def __init__(self) -> None:
        """初始化基准对比器."""
        self._benchmarks = BENCHMARK_REFERENCES
    
    def compare(self, result: EvaluationResult) -> dict[str, Any]:
        """
        对比评估结果与业界基准.
        
        Args:
            result: 评估结果
            
        Returns:
            对比结果
        """
        comparison: dict[str, Any] = {
            "comparisons": {},
            "summary": {},
        }
        
        for benchmark in self._benchmarks:
            comp = self._compare_to_benchmark(result, benchmark)
            comparison["comparisons"][benchmark.name] = comp
        
        better_count = sum(1 for c in comparison["comparisons"].values() if c.get("overall_better", False))
        comparison["summary"]["better_than_count"] = better_count
        comparison["summary"]["total_benchmarks"] = len(self._benchmarks)
        comparison["summary"]["performance_level"] = self._get_performance_level(better_count)
        
        return comparison
    
    def _compare_to_benchmark(self, result: EvaluationResult, benchmark: BenchmarkReference) -> dict[str, Any]:
        """对比单个基准."""
        comp: dict[str, Any] = {
            "benchmark_name": benchmark.name,
            "source": benchmark.source,
            "metrics_comparison": {},
        }
        
        our_metrics = {
            "task_accuracy": result.overall_metrics.task_accuracy.overall_accuracy,
            "reasoning_quality": result.overall_metrics.reasoning.overall_reasoning,
            "collaboration_score": result.overall_metrics.collaboration.overall_collaboration,
            "plan_correctness": result.overall_metrics.task_accuracy.plan_correctness,
            "execution_success": result.overall_metrics.task_accuracy.execution_success_rate,
            "information_diversity": result.overall_metrics.collaboration.information_diversity,
            "role_specialization": result.overall_metrics.collaboration.role_specialization,
            "reasoning_depth": result.overall_metrics.reasoning.reasoning_depth,
        }
        
        better_count = 0
        for key, their_value in benchmark.metrics.items():
            our_value = our_metrics.get(key, 0.0)
            diff = our_value - their_value
            comp["metrics_comparison"][key] = {
                "ours": round(our_value, 4),
                "theirs": round(their_value, 4),
                "diff": round(diff, 4),
                "better": diff > 0,
            }
            if diff > 0:
                better_count += 1
        
        comp["better_metrics_count"] = better_count
        comp["total_metrics"] = len(benchmark.metrics)
        comp["overall_better"] = better_count > len(benchmark.metrics) / 2
        
        return comp
    
    def _get_performance_level(self, better_than_count: int) -> str:
        """获取性能水平描述."""
        if better_than_count >= 3:
            return "Excellent - Better than most benchmarks"
        elif better_than_count >= 2:
            return "Good - Competitive with benchmarks"
        elif better_than_count >= 1:
            return "Fair - Below some benchmarks"
        else:
            return "Needs Improvement - Below all benchmarks"


__all__ = [
    "BenchmarkReference",
    "BENCHMARK_REFERENCES",
    "HistoryComparator",
    "BenchmarkComparator",
]
