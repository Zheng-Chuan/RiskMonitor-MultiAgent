#!/usr/bin/env python3
"""验证评估系统."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

print("Testing eval module imports...")

from eval.core.metrics import (
    TaskAccuracyMetrics,
    ComprehensionMetrics,
    CollaborationMetrics,
    EfficiencyMetrics,
    ReasoningMetrics,
    ToolRiskMetrics,
    OverallMetrics,
)
print("✅ Metrics imported")

from eval.core.evaluator import Evaluator, EvaluationResult, TestCase
print("✅ Evaluator imported")

from eval.core.llm_judge import LLMJudge
print("✅ LLMJudge imported")

from eval.core.report import ReportGenerator
print("✅ ReportGenerator imported")

from eval.comparison.benchmark import HistoryComparator, BenchmarkComparator
print("✅ Comparison modules imported")

print()
print("Testing metrics...")

task_acc = TaskAccuracyMetrics(
    intent_match_score=0.9,
    plan_correctness=0.85,
    execution_success_rate=0.88,
    answer_quality=0.82,
)
print(f"TaskAccuracy overall: {task_acc.overall_accuracy:.2%}")

collab = CollaborationMetrics(
    agent_participation_rate=0.8,
    information_diversity=0.6,
    message_exchange_depth=0.5,
    role_specialization=0.9,
    conflict_resolution_rate=0.7,
)
print(f"Collaboration overall: {collab.overall_collaboration:.2%}")

overall = OverallMetrics(
    task_accuracy=task_acc,
    collaboration=collab,
)
print(f"Overall score: {overall.overall_score:.2%}")

print()
print("Testing test case loading...")

import json

cases = []
for jsonl_file in Path("eval/benchmarks").rglob("*.jsonl"):
    with open(jsonl_file, "r") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line))

print(f"Total test cases: {len(cases)}")

categories = set(c.get("category", "unknown") for c in cases)
print(f"Categories: {categories}")

difficulties = set(c.get("difficulty", "unknown") for c in cases)
print(f"Difficulties: {difficulties}")

print()
print("=" * 60)
print("✅ All evaluation system components verified!")
print("=" * 60)
