from __future__ import annotations

from typing import Any


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def summarize_benchmark_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总 benchmark 记录 供旧测试兼容使用."""
    total_cases = len(records)
    unique_cases = len(
        {
            record.get("case_id")
            for record in records
            if record.get("case_id") is not None
        }
    )
    pass_rate = _avg([1.0 if record.get("ok") else 0.0 for record in records])

    quality_records = [record.get("quality") or {} for record in records]
    aggregates = {
        "latency_ms_avg": _avg([float(record.get("latency_ms") or 0.0) for record in records]),
        "tokens_total": sum(int(record.get("tokens_total") or 0) for record in records),
        "step_reason_coverage": _avg(
            [float(quality.get("step_reason_coverage") or 0.0) for quality in quality_records]
        ),
        "evidence_missing_rate": _avg(
            [float(quality.get("evidence_missing_rate") or 0.0) for quality in quality_records]
        ),
        "receipt_binding_rate": _avg(
            [float(quality.get("receipt_binding_rate") or 0.0) for quality in quality_records]
        ),
        "contract_fail_rate": _avg(
            [float(quality.get("contract_fail_rate") or 0.0) for quality in quality_records]
        ),
        "explainability_score": _avg(
            [float(quality.get("explainability_score") or 0.0) for quality in quality_records]
        ),
        "approval_required_rate": _avg(
            [1.0 if record.get("approval_required") else 0.0 for record in records]
        ),
        "governance_blocked_avg": _avg(
            [float(record.get("governance_blocked_count") or 0.0) for record in records]
        ),
        "degraded_avg": _avg(
            [float(record.get("degraded_count") or 0.0) for record in records]
        ),
    }

    return {
        "total_cases": total_cases,
        "unique_cases": unique_cases,
        "pass_rate": pass_rate,
        "aggregates": aggregates,
    }


__all__ = ["summarize_benchmark_records"]
