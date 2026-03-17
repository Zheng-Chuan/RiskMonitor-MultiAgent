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
                # 协作/过程指标 (Collaboration & Process Metrics)
                "ids_avg": 0.0,  # Information Diversity Score (越高越好)
                "upr_avg": 1.0,  # Unnecessary Path Ratio (越低越好)
                "milestone_achieved_rate_avg": 0.0,  # 里程碑达成率 (越高越好)
                # 新增 Agent System Metrics
                "task_completion_score_avg": 0.0,  # 任务完成度评分 (越高越好)
                "hallucination_score_avg": 0.0,  # 幻觉检测评分 (越高越好)
                "tool_call_success_rate_avg": 0.0,  # 工具调用成功率 (越高越好)
                "tool_call_count_avg": 0.0,  # 平均工具调用次数
                "tool_efficiency_score_avg": 0.0,  # 工具效率综合得分 (越高越好)
                "error_recovery_rate_avg": 0.0,  # 错误恢复率 (越高越好)
                "plan_revision_count_avg": 0.0,  # Plan 修正次数 (越低越好)
                "memory_usage_rate_avg": 0.0,  # 记忆使用比例 (越高越好)
                "context_completeness_avg": 0.0,  # 上下文完整度 (越高越好)
                "memory_efficiency_score_avg": 0.0,  # 记忆效能综合得分 (越高越好)
                # --- 新增 P0/P1 指标 (基于学术界 & 工业界最佳实践) ---
                "plan_execution_align_rate_avg": 0.0,  # P0: 计划执行一致性 (PlanBench)
                "tool_selection_accuracy_avg": 0.0,  # P0: 工具选择准确率 (GAIA)
                "collaboration_efficiency_avg": 0.0,  # P0: 协作效率 (MultiAgentBench)
                "role_specialization_avg": 0.0,  # P1: 角色专业化程度 (Industry)
                "factuality_score_avg": 0.0,  # P1: 事实准确性 (GAIA)
                "tool_result_utilization_avg": 0.0,  # 工具结果利用率
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

    # 协作/过程指标: IDS (越高越好，期望步骤间多样性)
    ids_scores = [_safe_float(x.get("ids_score"), 0.0) for x in q]
    # 协作/过程指标: UPR (越低越好，期望路径精简)
    uprs = [_safe_float(x.get("upr"), 1.0) for x in q]
    # 协作/过程指标: Milestone (越高越好，期望里程碑达成)
    milestones = [_safe_float(x.get("milestone_achieved_rate"), 0.0) for x in q]

    # 新增 Agent System Metrics
    task_completion_scores = [_safe_float(x.get("task_completion_score"), 0.0) for x in q]
    hallucination_scores = [_safe_float(x.get("hallucination_score"), 0.0) for x in q]
    tool_call_success_rates = [_safe_float(r.get("tool_call_success_rate"), 0.0) for r in records]
    tool_call_counts = [_safe_float(r.get("tool_call_count"), 0.0) for r in records]
    tool_efficiency_scores = [_safe_float(x.get("tool_efficiency_score"), 0.0) for x in q]
    error_recovery_rates = [_safe_float(r.get("error_recovery_rate"), 0.0) for r in records]
    plan_revision_counts = [_safe_float(r.get("plan_revision_count"), 0.0) for r in records]
    memory_usage_rates = [_safe_float(r.get("memory_usage_rate"), 0.0) for r in records]
    context_completenesses = [_safe_float(r.get("context_completeness"), 0.0) for r in records]
    memory_efficiency_scores = [_safe_float(x.get("memory_efficiency_score"), 0.0) for x in q]

    # --- 新增 P0/P1 指标 (基于学术界 & 工业界最佳实践) ---
    plan_execution_align_rates = [_safe_float(x.get("plan_execution_align_rate"), 0.0) for x in q]
    tool_selection_accuracies = [_safe_float(x.get("tool_selection_accuracy"), 0.0) for x in q]
    collaboration_efficiencies = [_safe_float(x.get("collaboration_efficiency"), 0.0) for x in q]
    role_specializations = [_safe_float(x.get("role_specialization"), 0.0) for x in q]
    factuality_scores = [_safe_float(x.get("factuality_score"), 0.0) for x in q]
    tool_result_utilizations = [_safe_float(x.get("tool_result_utilization"), 0.0) for x in q]

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
            # 协作/过程指标 (Collaboration & Process Metrics)
            "ids_avg": round(float(sum(ids_scores) / total), 6),
            "upr_avg": round(float(sum(uprs) / total), 6),
            "milestone_achieved_rate_avg": round(float(sum(milestones) / total), 6),
            # 新增 Agent System Metrics
            "task_completion_score_avg": round(float(sum(task_completion_scores) / total), 6),
            "hallucination_score_avg": round(float(sum(hallucination_scores) / total), 6),
            "tool_call_success_rate_avg": round(float(sum(tool_call_success_rates) / total), 6),
            "tool_call_count_avg": round(float(sum(tool_call_counts) / total), 6),
            "tool_efficiency_score_avg": round(float(sum(tool_efficiency_scores) / total), 6),
            "error_recovery_rate_avg": round(float(sum(error_recovery_rates) / total), 6),
            "plan_revision_count_avg": round(float(sum(plan_revision_counts) / total), 6),
            "memory_usage_rate_avg": round(float(sum(memory_usage_rates) / total), 6),
            "context_completeness_avg": round(float(sum(context_completenesses) / total), 6),
            "memory_efficiency_score_avg": round(float(sum(memory_efficiency_scores) / total), 6),
            # --- 新增 P0/P1 指标 (基于学术界 & 工业界最佳实践) ---
            "plan_execution_align_rate_avg": round(float(sum(plan_execution_align_rates) / total), 6),
            "tool_selection_accuracy_avg": round(float(sum(tool_selection_accuracies) / total), 6),
            "collaboration_efficiency_avg": round(float(sum(collaboration_efficiencies) / total), 6),
            "role_specialization_avg": round(float(sum(role_specializations) / total), 6),
            "factuality_score_avg": round(float(sum(factuality_scores) / total), 6),
            "tool_result_utilization_avg": round(float(sum(tool_result_utilizations) / total), 6),
        },
    }
