from __future__ import annotations

from typing import Any


def default_gate_thresholds() -> dict[str, float]:
    """默认质量门禁阈值.

    包含三大类指标:
    1. 传统指标 (Task Quality): step_reason, evidence, contract, latency, tokens, stability
    2. 协作/过程指标 (Collaboration & Process): IDS, UPR, Milestone
    3. Agent System Metrics: task_completion, hallucination, tool_efficiency, error_recovery, plan_revision, memory_efficiency
    """
    return {
        # --- 传统指标 ---
        "min_step_reason_coverage": 0.95,
        "max_evidence_missing_rate": 0.05,
        "min_receipt_binding_rate": 0.95,
        "max_contract_fail_rate": 0.02,
        "max_latency_ms_p95": 30000.0,  # 调整为 30s，金融风控场景需要更长时间
        "max_tokens_total": 300000.0,  # 调整为 300K，复杂分析需要更多 token
        "min_stability_ok_rate": 1.0,
        # --- 协作/过程指标 (Collaboration & Process Metrics) ---
        # IDS (Information Diversity Score): 越高越好，期望步骤间信息多样
        "min_ids_avg": 0.3,
        # UPR (Unnecessary Path Ratio): 越低越好，期望路径精简
        "max_upr_avg": 0.5,
        # Milestone (里程碑达成率): 越高越好，期望关键节点完成
        "min_milestone_achieved_rate_avg": 0.75,
        # --- 新增 Agent System Metrics ---
        # Task Completion Score: 越高越好，期望任务高质量完成
        "min_task_completion_score_avg": 0.7,
        # Hallucination Score: 越高越好，期望输出可信无幻觉
        "min_hallucination_score_avg": 0.8,
        # Tool Call Success Rate: 越高越好，期望工具调用成功
        "min_tool_call_success_rate_avg": 0.9,
        # Tool Efficiency Score: 越高越好，期望工具使用高效
        "min_tool_efficiency_score_avg": 0.7,
        # Error Recovery Rate: 越高越好，期望系统能从错误中恢复
        "min_error_recovery_rate_avg": 0.8,
        # Plan Revision Count: 越低越好，期望一次规划成功
        "max_plan_revision_count_avg": 1.0,
        # Memory Efficiency Score: 越高越好，期望记忆系统高效
        "min_memory_efficiency_score_avg": 0.6,
        # --- 新增 P0/P1 指标 (基于学术界 & 工业界最佳实践) ---
        # Plan Execution Alignment Rate: 越高越好，期望计划与执行一致 (PlanBench)
        "min_plan_execution_align_rate_avg": 0.8,
        # Tool Selection Accuracy: 越高越好，期望工具选择准确 (GAIA)
        "min_tool_selection_accuracy_avg": 0.8,
        # Collaboration Efficiency: 越高越好，期望 Agent 协作高效 (MultiAgentBench)
        "min_collaboration_efficiency_avg": 0.5,
        # Role Specialization: 越高越好，期望 Agent 角色专业化 (Industry)
        "min_role_specialization_avg": 0.5,
        # Factuality Score: 越高越好，期望事实准确 (GAIA)
        "min_factuality_score_avg": 0.7,
        # Tool Result Utilization: 越高越好，期望工具结果被充分利用
        "min_tool_result_utilization_avg": 0.7,
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

    # --- 新增 Agent System Metrics 观测 ---
    task_completion_score_avg = float(agg.get("task_completion_score_avg") or 0.0)
    hallucination_score_avg = float(agg.get("hallucination_score_avg") or 0.0)
    tool_call_success_rate_avg = float(agg.get("tool_call_success_rate_avg") or 0.0)
    tool_efficiency_score_avg = float(agg.get("tool_efficiency_score_avg") or 0.0)
    error_recovery_rate_avg = float(agg.get("error_recovery_rate_avg") or 0.0)
    plan_revision_count_avg = float(agg.get("plan_revision_count_avg") or 0.0)
    memory_efficiency_score_avg = float(agg.get("memory_efficiency_score_avg") or 0.0)

    # --- 新增 P0/P1 指标观测 (基于学术界 & 工业界最佳实践) ---
    plan_execution_align_rate_avg = float(agg.get("plan_execution_align_rate_avg") or 0.0)
    tool_selection_accuracy_avg = float(agg.get("tool_selection_accuracy_avg") or 0.0)
    collaboration_efficiency_avg = float(agg.get("collaboration_efficiency_avg") or 0.0)
    role_specialization_avg = float(agg.get("role_specialization_avg") or 0.0)
    factuality_score_avg = float(agg.get("factuality_score_avg") or 0.0)
    tool_result_utilization_avg = float(agg.get("tool_result_utilization_avg") or 0.0)

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

    # --- 新增 Agent System Metrics 门禁检查 ---
    if task_completion_score_avg < float(t["min_task_completion_score_avg"]):
        reasons.append("task_completion_score_avg_below_threshold")
    if hallucination_score_avg < float(t["min_hallucination_score_avg"]):
        reasons.append("hallucination_score_avg_below_threshold")
    if tool_call_success_rate_avg < float(t["min_tool_call_success_rate_avg"]):
        reasons.append("tool_call_success_rate_avg_below_threshold")
    if tool_efficiency_score_avg < float(t["min_tool_efficiency_score_avg"]):
        reasons.append("tool_efficiency_score_avg_below_threshold")
    if error_recovery_rate_avg < float(t["min_error_recovery_rate_avg"]):
        reasons.append("error_recovery_rate_avg_below_threshold")
    if plan_revision_count_avg > float(t["max_plan_revision_count_avg"]):
        reasons.append("plan_revision_count_avg_above_threshold")
    if memory_efficiency_score_avg < float(t["min_memory_efficiency_score_avg"]):
        reasons.append("memory_efficiency_score_avg_below_threshold")

    # --- 新增 P0/P1 指标门禁检查 (基于学术界 & 工业界最佳实践) ---
    if plan_execution_align_rate_avg < float(t["min_plan_execution_align_rate_avg"]):
        reasons.append("plan_execution_align_rate_avg_below_threshold")
    if tool_selection_accuracy_avg < float(t["min_tool_selection_accuracy_avg"]):
        reasons.append("tool_selection_accuracy_avg_below_threshold")
    if collaboration_efficiency_avg < float(t["min_collaboration_efficiency_avg"]):
        reasons.append("collaboration_efficiency_avg_below_threshold")
    if role_specialization_avg < float(t["min_role_specialization_avg"]):
        reasons.append("role_specialization_avg_below_threshold")
    if factuality_score_avg < float(t["min_factuality_score_avg"]):
        reasons.append("factuality_score_avg_below_threshold")
    if tool_result_utilization_avg < float(t["min_tool_result_utilization_avg"]):
        reasons.append("tool_result_utilization_avg_below_threshold")

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
            # 新增 Agent System Metrics
            "task_completion_score_avg": task_completion_score_avg,
            "hallucination_score_avg": hallucination_score_avg,
            "tool_call_success_rate_avg": tool_call_success_rate_avg,
            "tool_efficiency_score_avg": tool_efficiency_score_avg,
            "error_recovery_rate_avg": error_recovery_rate_avg,
            "plan_revision_count_avg": plan_revision_count_avg,
            "memory_efficiency_score_avg": memory_efficiency_score_avg,
            # --- 新增 P0/P1 指标 ---
            "plan_execution_align_rate_avg": plan_execution_align_rate_avg,
            "tool_selection_accuracy_avg": tool_selection_accuracy_avg,
            "collaboration_efficiency_avg": collaboration_efficiency_avg,
            "role_specialization_avg": role_specialization_avg,
            "factuality_score_avg": factuality_score_avg,
            "tool_result_utilization_avg": tool_result_utilization_avg,
        },
        "thresholds": t,
    }
