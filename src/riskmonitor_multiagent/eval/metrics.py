from __future__ import annotations

from typing import Any


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    idx = max(0, int(round(0.95 * (len(vs) - 1))))
    return float(vs[idx])


def summarize_benchmark_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    if total == 0:
        return {
            "total_cases": 0,
            "unique_cases": 0,
            "pass_rate": 0.0,
            "aggregates": {
                "latency_ms_avg": 0.0,
                "latency_ms_p95": 0.0,
                "step_reason_coverage": 0.0,
                "evidence_missing_rate": 1.0,
                "receipt_binding_rate": 0.0,
                "contract_fail_rate": 1.0,
                "explainability_score": 0.0,
                "tokens_total": 0,
                "approval_required_rate": 0.0,
                "governance_blocked_avg": 0.0,
                "degraded_avg": 0.0,
                "stability_ok_rate": 0.0,
            },
        }

    pass_count = sum(1 for r in records if bool(r.get("ok")))
    latencies = [_safe_float(r.get("latency_ms"), 0.0) for r in records]
    q = [r.get("quality") if isinstance(r.get("quality"), dict) else {} for r in records]
    step_reason = [_safe_float(x.get("step_reason_coverage"), 0.0) for x in q]
    evidence_missing = [_safe_float(x.get("evidence_missing_rate"), 1.0) for x in q]
    receipt_binding = [_safe_float(x.get("receipt_binding_rate"), 0.0) for x in q]
    contract_fail = [_safe_float(x.get("contract_fail_rate"), 1.0) for x in q]
    explainability = [_safe_float(x.get("explainability_score"), 0.0) for x in q]
    token_values = [_safe_float(r.get("tokens_total"), 0.0) for r in records]
    approvals = [1.0 if bool(r.get("approval_required")) else 0.0 for r in records]
    governance_blocked = [_safe_float(r.get("governance_blocked_count"), 0.0) for r in records]
    degraded = [_safe_float(r.get("degraded_count"), 0.0) for r in records]

    case_ok: dict[str, list[bool]] = {}
    for r in records:
        cid = str(r.get("case_id") or "")
        if not cid:
            continue
        case_ok.setdefault(cid, []).append(bool(r.get("ok")))
    stable_cases = 0
    for vals in case_ok.values():
        if vals and all(v is vals[0] for v in vals):
            stable_cases += 1
    unique_cases = len(case_ok)
    stability_ok_rate = float(stable_cases / unique_cases) if unique_cases > 0 else 0.0

    return {
        "total_cases": total,
        "unique_cases": unique_cases,
        "pass_rate": round(float(pass_count / total), 6),
        "aggregates": {
            "latency_ms_avg": round(float(sum(latencies) / total), 6),
            "latency_ms_p95": round(_p95(latencies), 6),
            "step_reason_coverage": round(float(sum(step_reason) / total), 6),
            "evidence_missing_rate": round(float(sum(evidence_missing) / total), 6),
            "receipt_binding_rate": round(float(sum(receipt_binding) / total), 6),
            "contract_fail_rate": round(float(sum(contract_fail) / total), 6),
            "explainability_score": round(float(sum(explainability) / total), 6),
            "tokens_total": int(round(sum(token_values))),
            "approval_required_rate": round(float(sum(approvals) / total), 6),
            "governance_blocked_avg": round(float(sum(governance_blocked) / total), 6),
            "degraded_avg": round(float(sum(degraded) / total), 6),
            "stability_ok_rate": round(stability_ok_rate, 6),
        },
    }
