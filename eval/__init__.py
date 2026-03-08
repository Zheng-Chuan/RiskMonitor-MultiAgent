"""评估流水线：与业务解耦，仅依赖「工作流执行 + 评估契约」."""

from eval.case_schema import BenchmarkCase
from eval.case_schema import load_benchmark_cases
from eval.gate import default_gate_thresholds
from eval.gate import evaluate_quality_gate
from eval.metrics import summarize_benchmark_records
from eval.runner import run_benchmark

__all__ = [
    "BenchmarkCase",
    "load_benchmark_cases",
    "run_benchmark",
    "summarize_benchmark_records",
    "default_gate_thresholds",
    "evaluate_quality_gate",
]
