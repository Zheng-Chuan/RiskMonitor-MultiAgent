"""质量门禁检查模块."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_BLOCKING_THRESHOLDS: dict[str, dict[str, float]] = {
    "task_success_rate": {"min": 0.8},
    "tool_selection_accuracy": {"min": 0.75},
    "receipt_binding_rate": {"min": 0.95},
    "replan_success_rate": {"min": 0.7},
    "approval_correctness": {"min": 0.95},
    "resume_success_rate": {"min": 0.7},
    "dangerous_action_block_rate": {"min": 0.95},
    "message_trace_completeness": {"min": 0.95},
    "factuality_score": {"min": 0.7},
    "evidence_coverage": {"min": 0.6},
}

DEFAULT_WARNING_THRESHOLDS: dict[str, dict[str, float]] = {
    "workflow_success": {"min": 0.85},
    "tool_success_rate": {"min": 0.85},
    "memory_hit_rate": {"min": 0.4},
    "memory_usefulness": {"min": 0.45},
    "replan_quality": {"min": 0.7},
    "latency_ms": {"max": 5000},
    "token_count": {"max": 8000},
    "information_diversity": {"min": 0.3},
    "role_specialization": {"min": 0.5},
}


@dataclass
class GateResult:
    """门禁检查结果."""

    passed: bool
    reasons: list[str]
    metrics_summary: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    decision_log: list[dict[str, Any]] = field(default_factory=list)


def evaluate_quality_gate(summary: dict[str, Any]) -> GateResult:
    """使用默认阈值检查评估结果."""
    thresholds = {
        "blocking": DEFAULT_BLOCKING_THRESHOLDS,
        "warning": DEFAULT_WARNING_THRESHOLDS,
    }
    return evaluate_with_custom_thresholds(summary, thresholds)


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
    """使用自定义阈值检查评估结果."""
    reasons: list[str] = []
    warnings: list[str] = []
    passed = True

    behavior_metrics, legacy_metrics = _resolve_metrics(summary)
    metric_definitions = summary.get("metric_definitions", {})
    decision_log: list[dict[str, Any]] = []

    blocking_config = thresholds.get("blocking")
    warning_config = thresholds.get("warning")
    if blocking_config is None and warning_config is None:
        legacy_thresholds = thresholds.get("thresholds", {})
        blocking_config = {
            name: config
            for name, config in legacy_thresholds.items()
            if name in DEFAULT_BLOCKING_THRESHOLDS
        }
        warning_config = {
            name: config
            for name, config in legacy_thresholds.items()
            if name not in DEFAULT_BLOCKING_THRESHOLDS
        }

    blocking_config = blocking_config or DEFAULT_BLOCKING_THRESHOLDS
    warning_config = warning_config or DEFAULT_WARNING_THRESHOLDS

    for metric_name, config in blocking_config.items():
        actual_value = _lookup_metric(metric_name, behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics)
        check_type, threshold = _extract_threshold(config)
        is_pass = _passes(actual_value, check_type, threshold)
        decision_log.append(
            _build_decision_log_item(
                metric_name=metric_name,
                actual_value=actual_value,
                threshold=threshold,
                check_type=check_type,
                severity="blocking",
                definition=metric_definitions.get(metric_name, {}),
                passed=is_pass,
            )
        )
        if not is_pass:
            passed = False
            reasons.append(_format_reason(metric_name, actual_value, check_type, threshold))

    for metric_name, config in warning_config.items():
        actual_value = _lookup_metric(metric_name, behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics)
        check_type, threshold = _extract_threshold(config)
        is_pass = _passes(actual_value, check_type, threshold)
        decision_log.append(
            _build_decision_log_item(
                metric_name=metric_name,
                actual_value=actual_value,
                threshold=threshold,
                check_type=check_type,
                severity="warning",
                definition=metric_definitions.get(metric_name, {}),
                passed=is_pass,
            )
        )
        if not is_pass:
            warnings.append(_format_reason(metric_name, actual_value, check_type, threshold))

    metrics_summary = {
        "task_success_rate": _lookup_metric("task_success_rate", behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics),
        "tool_success_rate": _lookup_metric("tool_success_rate", behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics),
        "approval_correctness": _lookup_metric("approval_correctness", behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics),
        "dangerous_action_block_rate": _lookup_metric("dangerous_action_block_rate", behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics),
        "message_trace_completeness": _lookup_metric("message_trace_completeness", behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics),
        "factuality_score": _lookup_metric("factuality_score", behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics),
        "evidence_coverage": _lookup_metric("evidence_coverage", behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics),
        "tool_call_count": _lookup_metric("tool_call_count", behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics),
        "approval_count": _lookup_metric("approval_count", behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics),
        "replan_count": _lookup_metric("replan_count", behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics),
        "memory_hit_count": _lookup_metric("memory_hit_count", behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics),
        "latency_ms": _lookup_metric("latency_ms", behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics),
        "token_count": _lookup_metric("token_count", behavior_metrics=behavior_metrics, legacy_metrics=legacy_metrics),
    }

    return GateResult(
        passed=passed,
        reasons=reasons,
        metrics_summary=metrics_summary,
        warnings=warnings,
        decision_log=decision_log,
    )


def _resolve_metrics(summary: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    aggregates = summary.get("aggregates", {})
    behavior_metrics = summary.get("behavior_metrics")
    if not isinstance(behavior_metrics, dict):
        behavior_metrics = aggregates.get("behavioral_metrics", {})
    legacy_metrics = summary.get("metrics")
    if not isinstance(legacy_metrics, dict):
        legacy_metrics = aggregates.get("metrics", {})
    return behavior_metrics or {}, legacy_metrics or {}


def _lookup_metric(
    metric_name: str,
    *,
    behavior_metrics: dict[str, Any],
    legacy_metrics: dict[str, Any],
) -> float | int:
    if metric_name in behavior_metrics:
        value = behavior_metrics.get(metric_name)
        if isinstance(value, (int, float)):
            return value

    legacy_mapping = {
        "latency_ms": ("efficiency", "latency_ms"),
        "token_count": ("efficiency", "token_count"),
        "information_diversity": ("collaboration", "information_diversity"),
        "role_specialization": ("collaboration", "role_specialization"),
    }
    section_key = legacy_mapping.get(metric_name)
    if section_key is None:
        return 0.0
    section, key = section_key
    section_payload = legacy_metrics.get(section, {})
    value = section_payload.get(key) if isinstance(section_payload, dict) else 0.0
    return value if isinstance(value, (int, float)) else 0.0


def _extract_threshold(config: dict[str, Any]) -> tuple[str, float]:
    if "max" in config:
        return "max", float(config["max"])
    return "min", float(config.get("min", 0.0))


def _passes(actual_value: float | int, check_type: str, threshold: float) -> bool:
    if check_type == "max":
        return float(actual_value) <= threshold
    return float(actual_value) >= threshold


def _format_reason(metric_name: str, actual_value: float | int, check_type: str, threshold: float) -> str:
    comparator = "<" if check_type == "min" else ">"
    return f"{metric_name} {float(actual_value):.4f} {comparator} {threshold}"


def _build_decision_log_item(
    *,
    metric_name: str,
    actual_value: float | int,
    threshold: float,
    check_type: str,
    severity: str,
    definition: dict[str, Any],
    passed: bool,
) -> dict[str, Any]:
    return {
        "metric_name": metric_name,
        "actual": float(actual_value),
        "threshold": threshold,
        "check_type": check_type,
        "severity": severity,
        "passed": passed,
        "source": definition.get("data_source"),
        "formula": definition.get("formula"),
        "gate_rule": definition.get("gate_rule"),
        "evidence_entry_ids": [],
    }


__all__ = [
    "GateResult",
    "evaluate_quality_gate",
    "load_gate_thresholds",
    "evaluate_with_custom_thresholds",
]
