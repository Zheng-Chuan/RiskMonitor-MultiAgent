#!/usr/bin/env python3
"""手动测试质量门禁系统."""

import sys
from pathlib import Path

# 添加项目根目录和 src 目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from eval.gate import evaluate_quality_gate

# 测试用例 1: 所有指标都达标
print("=" * 60)
print("测试 1: 所有指标都达标")
print("=" * 60)

summary_good = {
    "aggregates": {
        "metrics": {
            "reasoning": {
                "evidence_support": 0.95,
                "reasoning_validity": 0.9,
            },
            "efficiency": {
                "latency_ms": 1500,
                "token_count": 4000,
                "tool_call_efficiency": 0.95,
            },
            "collaboration": {
                "information_diversity": 0.5,
                "role_specialization": 0.7,
            },
            "task_accuracy": {
                "execution_success_rate": 0.85,
            },
            "comprehension": {
                "intent_recognition_f1": 0.9,
            },
        }
    },
    "contract_fail_rate": 0.02,
}

result = evaluate_quality_gate(summary_good)
print(f"结果:{'✅ 通过' if result.passed else '❌ 失败'}")
print(f"指标摘要:{result.metrics_summary}")
if not result.passed:
    print(f"失败原因:{result.reasons}")

# 测试用例 2: 证据支持度太低
print("\n" + "=" * 60)
print("测试 2: 证据支持度太低")
print("=" * 60)

summary_bad = {
    "aggregates": {
        "metrics": {
            "reasoning": {
                "evidence_support": 0.7,  # < 0.9
                "reasoning_validity": 0.9,
            },
            "efficiency": {
                "latency_ms": 1500,
                "token_count": 4000,
                "tool_call_efficiency": 0.95,
            },
            "collaboration": {
                "information_diversity": 0.5,
                "role_specialization": 0.7,
            },
            "task_accuracy": {
                "execution_success_rate": 0.85,
            },
            "comprehension": {
                "intent_recognition_f1": 0.9,
            },
        }
    },
    "contract_fail_rate": 0.02,
}

result = evaluate_quality_gate(summary_bad)
print(f"结果:{'✅ 通过' if result.passed else '❌ 失败'}")
print(f"指标摘要:{result.metrics_summary}")
if not result.passed:
    print(f"失败原因:{result.reasons}")

print("\n" + "=" * 60)
print("✅ 质量门禁系统工作正常!")
print("=" * 60)
