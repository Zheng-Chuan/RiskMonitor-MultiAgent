from __future__ import annotations

from typing import Any


def default_gate_thresholds() -> dict[str, float]:
    """默认质量门禁阈值.

    包含两大类指标:
    1. 传统指标 (Task Quality): step_reason, evidence, contract, latency, tokens, stability
    2. 协作/过程指标 (Collaboration & Process): IDS, UPR, Milestone
    """
    return {
        # --- 传统指标 ---
        "min_step_reason_coverage": 0.95,
        "max_evidence_missing_rate": 0.05,
        "min_receipt_binding_rate": 0.95,
        "max_contract_fail_rate": 0.02,
        "max_latency_ms_p95": 8000.0,
        "max_tokens_total": 50000.0,
        "min_stability_ok_rate": 1.0,
        # --- 协作/过程指标 (Collaboration & Process Metrics) ---
        # IDS (Information Diversity Score): 越高越好，期望步骤间信息多样
        "min_ids_avg": 0.3,
        # UPR (Unnecessary Path Ratio): 越低越好，期望路径精简
        "max_upr_avg": 0.5,
        # Milestone (里程碑达成率): 越高越好，期望关键节点完成
        "min_milestone_achieved_rate_avg": 0.75,
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

    # --- 传统指标观测 ---
    step_reason_coverage = float(agg.get("step_reason_coverage") or 0.0)
    evidence_missing_rate = float(agg.get("evidence_missing_rate") or 0.0)
    receipt_binding_rate = float(agg.get("receipt_binding_rate") or 0.0)
    contract_fail_rate = float(agg.get("contract_fail_rate") or 0.0)
    latency_p95 = float(agg.get("latency_ms_p95") or 0.0)
    tokens_total = float(agg.get("tokens_total") or 0.0)
    stability_ok_rate = float(agg.get("stability_ok_rate") or 0.0)

    # --- 协作/过程指标观测 ---
    ids_avg = float(agg.get("ids_avg") or 0.0)
    upr_avg = float(agg.get("upr_avg") or 1.0)
    milestone_achieved_rate_avg = float(agg.get("milestone_achieved_rate_avg") or 0.0)

    # --- 传统指标门禁检查 ---
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

    # --- 协作/过程指标门禁检查 ---
    if ids_avg < float(t["min_ids_avg"]):
        reasons.append("ids_avg_below_threshold")
    if upr_avg > float(t["max_upr_avg"]):
        reasons.append("upr_avg_above_threshold")
    if milestone_achieved_rate_avg < float(t["min_milestone_achieved_rate_avg"]):
        reasons.append("milestone_achieved_rate_avg_below_threshold")

    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
        "observed": {
            # 传统指标
            "step_reason_coverage": step_reason_coverage,
            "evidence_missing_rate": evidence_missing_rate,
            "receipt_binding_rate": receipt_binding_rate,
            "contract_fail_rate": contract_fail_rate,
            "latency_ms_p95": latency_p95,
            "tokens_total": tokens_total,
            "stability_ok_rate": stability_ok_rate,
            # 协作/过程指标
            "ids_avg": ids_avg,
            "upr_avg": upr_avg,
            "milestone_achieved_rate_avg": milestone_achieved_rate_avg,
        },
        "thresholds": t,
    }
