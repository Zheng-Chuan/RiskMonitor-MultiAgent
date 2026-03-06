from __future__ import annotations

from typing import Any


def default_gate_thresholds() -> dict[str, float]:
    return {
        "min_step_reason_coverage": 0.95,
        "max_evidence_missing_rate": 0.05,
        "min_receipt_binding_rate": 0.95,
        "max_contract_fail_rate": 0.02,
        "max_latency_ms_p95": 8000.0,
        "max_tokens_total": 50000.0,
        "min_stability_ok_rate": 1.0,
    }


def evaluate_quality_gate(summary: dict[str, Any], thresholds: dict[str, Any] | None = None) -> dict[str, Any]:
    t = default_gate_thresholds()
    if isinstance(thresholds, dict):
        for k, v in thresholds.items():
            try:
                t[str(k)] = float(v)
            except Exception:
                continue

    agg = summary.get("aggregates") if isinstance(summary.get("aggregates"), dict) else {}
    reasons: list[str] = []

    step_reason_coverage = float(agg.get("step_reason_coverage") or 0.0)
    evidence_missing_rate = float(agg.get("evidence_missing_rate") or 0.0)
    receipt_binding_rate = float(agg.get("receipt_binding_rate") or 0.0)
    contract_fail_rate = float(agg.get("contract_fail_rate") or 0.0)
    latency_p95 = float(agg.get("latency_ms_p95") or 0.0)
    tokens_total = float(agg.get("tokens_total") or 0.0)
    stability_ok_rate = float(agg.get("stability_ok_rate") or 0.0)

    if step_reason_coverage < float(t["min_step_reason_coverage"]):
        reasons.append("step_reason_coverage_below_threshold")
    if evidence_missing_rate > float(t["max_evidence_missing_rate"]):
        reasons.append("evidence_missing_rate_above_threshold")
    if receipt_binding_rate < float(t["min_receipt_binding_rate"]):
        reasons.append("receipt_binding_rate_below_threshold")
    if contract_fail_rate > float(t["max_contract_fail_rate"]):
        reasons.append("contract_fail_rate_above_threshold")
    if latency_p95 > float(t["max_latency_ms_p95"]):
        reasons.append("latency_ms_p95_above_threshold")
    if tokens_total > float(t["max_tokens_total"]):
        reasons.append("tokens_total_above_threshold")
    if stability_ok_rate < float(t["min_stability_ok_rate"]):
        reasons.append("stability_ok_rate_below_threshold")

    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
        "observed": {
            "step_reason_coverage": step_reason_coverage,
            "evidence_missing_rate": evidence_missing_rate,
            "receipt_binding_rate": receipt_binding_rate,
            "contract_fail_rate": contract_fail_rate,
            "latency_ms_p95": latency_p95,
            "tokens_total": tokens_total,
            "stability_ok_rate": stability_ok_rate,
        },
        "thresholds": t,
    }
