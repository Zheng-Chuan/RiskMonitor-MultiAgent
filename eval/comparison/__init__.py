"""
对比分析模块.

提供历史版本对比和业界基准对比.
"""

from eval.comparison.benchmark import (
    BenchmarkComparator,
    HistoryComparator,
    BenchmarkReference,
    BENCHMARK_REFERENCES,
)

__all__ = [
    "BenchmarkComparator",
    "HistoryComparator",
    "BenchmarkReference",
    "BENCHMARK_REFERENCES",
]
