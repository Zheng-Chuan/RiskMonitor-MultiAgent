"""
质量门禁检查模块.

检查评估结果是否达到质量要求,输出通过/失败结论及原因.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GateResult:
    """门禁检查结果."""
    passed: bool
    reasons: list[str]
    metrics_summary: dict[str, Any]


def evaluate_quality_gate(summary: dict[str, Any]) -> GateResult:
    """
    检查评估结果是否通过质量门禁.
    
    Args:
        summary: 评估摘要,包含 aggregates 字段
        
    Returns:
        GateResult 包含是否通过及原因
    """
    reasons: list[str] = []
    passed = True
    
    aggregates = summary.get("aggregates", {})
    metrics = aggregates.get("metrics", {})
    
    # === 传统指标阈值 ===
    
    # 1. 证据支持度 >= 0.9 (越低表示越缺少证据)
    evidence_support = metrics.get("reasoning", {}).get("evidence_support", 1.0)
    if evidence_support < 0.9:
        passed = False
        reasons.append(f"证据支持度 {evidence_support:.2f} < 0.9 (阈值)")
    
    # 2. P95 延迟 < 2000ms
    latency_p95 = metrics.get("efficiency", {}).get("latency_ms", 0)
    if latency_p95 > 2000:
        passed = False
        reasons.append(f"P95 延迟 {latency_p95}ms > 2000ms (阈值)")
    
    # 3. Token 使用 < 5000
    tokens = metrics.get("efficiency", {}).get("token_count", 0)
    if tokens > 5000:
        passed = False
        reasons.append(f"Token 使用 {tokens} > 5000 (阈值)")
    
    # 4. 合约失败率 < 5%
    contract_fail_rate = summary.get("contract_fail_rate", 0)
    if contract_fail_rate > 0.05:
        passed = False
        reasons.append(f"合约失败率 {contract_fail_rate:.2%} > 5% (阈值)")
    
    # === 协作指标阈值 ===
    
    # 5. 信息多样性 (IDS) > 0.3
    information_diversity = metrics.get("collaboration", {}).get("information_diversity", 0)
    if information_diversity < 0.3:
        passed = False
        reasons.append(f"信息多样性 {information_diversity:.2f} < 0.3 (阈值)")
    
    # 6. 角色专业化 > 0.5
    role_specialization = metrics.get("collaboration", {}).get("role_specialization", 0)
    if role_specialization < 0.5:
        passed = False
        reasons.append(f"角色专业化 {role_specialization:.2f} < 0.5 (阈值)")
    
    # === Agent System 指标阈值 ===
    
    # 7. 任务完成度 > 0.7
    task_completion = metrics.get("task_accuracy", {}).get("execution_success_rate", 0)
    if task_completion < 0.7:
        passed = False
        reasons.append(f"任务完成度 {task_completion:.2f} < 0.7 (阈值)")
    
    # 8. 工具调用成功率 > 0.9
    tool_success = metrics.get("efficiency", {}).get("tool_call_efficiency", 0)
    if tool_success < 0.9:
        passed = False
        reasons.append(f"工具成功率 {tool_success:.2f} < 0.9 (阈值)")
    
    # 9. 推理质量 > 0.8
    reasoning_quality = metrics.get("reasoning", {}).get("reasoning_validity", 0)
    if reasoning_quality < 0.8:
        passed = False
        reasons.append(f"推理质量 {reasoning_quality:.2f} < 0.8 (阈值)")
    
    # 10. 意图识别准确度 > 0.8
    intent_accuracy = metrics.get("comprehension", {}).get("intent_recognition_f1", 0)
    if intent_accuracy < 0.8:
        passed = False
        reasons.append(f"意图识别准确度 {intent_accuracy:.2f} < 0.8 (阈值)")
    
    return GateResult(
        passed=passed,
        reasons=reasons,
        metrics_summary={
            "evidence_support": evidence_support,
            "latency_p95": latency_p95,
            "token_count": tokens,
            "contract_fail_rate": contract_fail_rate,
            "information_diversity": information_diversity,
            "role_specialization": role_specialization,
            "task_completion": task_completion,
            "tool_success": tool_success,
            "reasoning_quality": reasoning_quality,
            "intent_accuracy": intent_accuracy,
        }
    )


def load_gate_thresholds(config_path: str) -> dict[str, Any]:
    """
    从配置文件加载门禁阈值.
    
    Args:
        config_path: 配置文件路径 (JSON)
        
    Returns:
        阈值配置字典
    """
    import json
    from pathlib import Path
    
    config_file = Path(config_path)
    if not config_file.exists():
        return {}
    
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_with_custom_thresholds(
    summary: dict[str, Any],
    thresholds: dict[str, Any],
) -> GateResult:
    """
    使用自定义阈值检查评估结果.
    
    Args:
        summary: 评估摘要
        thresholds: 自定义阈值配置
        
    Returns:
        GateResult 包含是否通过及原因
    """
    reasons: list[str] = []
    passed = True
    
    aggregates = summary.get("aggregates", {})
    metrics = aggregates.get("metrics", {})
    
    # 从配置获取阈值,如果没有配置则使用默认值
    threshold_config = thresholds.get("thresholds", {})
    
    # 检查每个指标
    checks = [
        ("evidence_support", metrics.get("reasoning", {}).get("evidence_support", 1.0), "min", 0.9),
        ("latency_p95", metrics.get("efficiency", {}).get("latency_ms", 0), "max", 2000),
        ("token_count", metrics.get("efficiency", {}).get("token_count", 0), "max", 5000),
        ("contract_fail_rate", summary.get("contract_fail_rate", 0), "max", 0.05),
        ("information_diversity", metrics.get("collaboration", {}).get("information_diversity", 0), "min", 0.3),
        ("role_specialization", metrics.get("collaboration", {}).get("role_specialization", 0), "min", 0.5),
        ("task_completion", metrics.get("task_accuracy", {}).get("execution_success_rate", 0), "min", 0.7),
        ("tool_success", metrics.get("efficiency", {}).get("tool_call_efficiency", 0), "min", 0.9),
        ("reasoning_quality", metrics.get("reasoning", {}).get("reasoning_validity", 0), "min", 0.8),
        ("intent_accuracy", metrics.get("comprehension", {}).get("intent_recognition_f1", 0), "min", 0.8),
    ]
    
    for metric_name, actual_value, check_type, default_threshold in checks:
        # 获取自定义阈值或默认值
        metric_config = threshold_config.get(metric_name, {})
        threshold = metric_config.get(check_type, default_threshold)
        
        # 检查是否通过
        if check_type == "min" and actual_value < threshold:
            passed = False
            reasons.append(f"{metric_name} {actual_value:.2f} < {threshold} (最小阈值)")
        elif check_type == "max" and actual_value > threshold:
            passed = False
            reasons.append(f"{metric_name} {actual_value:.2f} > {threshold} (最大阈值)")
    
    return GateResult(
        passed=passed,
        reasons=reasons,
        metrics_summary={name: value for name, value, _, _ in checks}
    )


__all__ = [
    "GateResult",
    "evaluate_quality_gate",
    "load_gate_thresholds",
    "evaluate_with_custom_thresholds",
]
