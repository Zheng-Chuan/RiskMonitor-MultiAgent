"""评估契约：将工作流输出转换为评估流水线所需的记录格式.

业务侧唯一与「评估」相关的模块：仅负责从 run_orchestrator_workflow 的返回值
构造评估记录，不依赖 eval 包。评估流水线只依赖本函数，不感知工作流内部结构.

新增协作/过程指标（Industry Best Practice）:
- IDS (Information Diversity Score): 步骤间输出的语义差异度（高=协作好）
- UPR (Unnecessary Path Ratio): 冗余路径占比（低=效率高）
- Milestone (milestone_achieved_rate): 关键里程碑达成率

新增指标（Agent System Metrics）:
- Task Completion Score: 任务完成质量评分
- Hallucination Score: 幻觉检测评分（基于证据一致性）
- Tool Usage Efficiency: 工具使用效率
- Error Recovery Rate: 错误恢复率
- Plan Revision Count: Plan 修正次数
- Memory System Efficiency: 记忆系统效能（Redis命中率等）
"""

from __future__ import annotations

import json
from typing import Any


def _has_evidence_refs(evidence: Any) -> bool:
    if not isinstance(evidence, dict):
        return False
    for v in (
        evidence.get("fields"),
        evidence.get("receipt_command_ids"),
        evidence.get("rag_hit_ids"),
    ):
        if isinstance(v, list) and any(isinstance(x, str) and x.strip() for x in v):
            return True
    return False


def _compute_ids(result: dict[str, Any], artifacts: dict[str, Any]) -> float:
    """计算信息多样性 (Information Diversity Score).

    基于 Agent 角色和输出内容的语义差异度。
    考虑以下维度：
    1. Agent 类型差异（Orchestrator vs Critic vs Engineer vs Analyst）
    2. 输出内容的 key 集合差异
    3. 是否有明确的不同视角（技术 vs 业务）
    
    IDS 范围 [0, 1]，越高表示步骤间信息越多样。
    """
    # 收集各 Agent 的输出
    agent_outputs: dict[str, dict] = {}
    
    # 从 result 中提取主要 Agent 的输出
    agent_keys = ["intent", "orchestrator_plan", "orchestrator_final", 
                  "critic_plan", "critic_final", "engineer", "analyst"]
    for key in agent_keys:
        data = result.get(key)
        if isinstance(data, dict) and len(data) > 0:
            agent_outputs[key] = data
    
    # 如果没有足够的 Agent 输出，退回到基于 artifacts 的计算
    if len(agent_outputs) < 2:
        # 从 artifacts 补充
        for a in artifacts.values():
            if isinstance(a, dict):
                out = a.get("output")
                if isinstance(out, dict):
                    target = a.get("target_agent") or a.get("agent_id") or "unknown"
                    if target not in agent_outputs:
                        agent_outputs[target] = out
    
    if len(agent_outputs) < 2:
        return 0.0
    
    # 1. 基础差异：基于 key 集合的 Jaccard 相似度
    key_sets: list[set] = []
    for out in agent_outputs.values():
        keys = {k for k, v in out.items() if v is not None and v != ""}
        if keys:
            key_sets.append(keys)
    
    if len(key_sets) < 2:
        return 0.0
    
    # 计算平均 Jaccard 差异
    sims: list[float] = []
    for i in range(len(key_sets)):
        for j in range(i + 1, len(key_sets)):
            a, b = key_sets[i], key_sets[j]
            inter = len(a & b)
            union = len(a | b)
            sim = inter / union if union > 0 else 1.0
            sims.append(sim)
    
    base_diversity = 1.0 - (sum(sims) / len(sims) if sims else 1.0)
    
    # 2. 角色类型加成：如果有 Engineer 和 Analyst 同时存在，增加多样性分数
    has_engineer = "engineer" in agent_outputs or any("engineer" in k for k in agent_outputs.keys())
    has_analyst = "analyst" in agent_outputs or any("analyst" in k for k in agent_outputs.keys())
    
    if has_engineer and has_analyst:
        # 技术和业务双视角，多样性加分
        base_diversity = min(1.0, base_diversity * 1.5 + 0.1)
    
    # 3. 如果只有单一类型 Agent，降低多样性分数
    agent_types = set()
    for key in agent_outputs.keys():
        if "orchestrator" in key:
            agent_types.add("orchestrator")
        elif "critic" in key:
            agent_types.add("critic")
        elif "engineer" in key:
            agent_types.add("engineer")
        elif "analyst" in key:
            agent_types.add("analyst")
        elif "intent" in key:
            agent_types.add("intent")
    
    if len(agent_types) <= 2:
        # Agent 类型太少，降低多样性
        base_diversity = base_diversity * 0.5
    
    return round(max(0.0, min(1.0, base_diversity)), 6)


def _compute_upr(result: dict[str, Any]) -> float:
    """计算冗余路径比 (Unnecessary Path Ratio).

    近似 = 实际执行的无产出步骤 / 总步骤数。
    当前用 "degraded 步骤占比" 近似冗余。
    范围 [0, 1]，越低越好。
    """
    total_steps = 6  # intent, orchestrator_plan, orchestrator_final, critic_plan, critic_final, engineer, analyst 中取主要
    degraded_count = sum(
        1
        for x in (
            result.get("intent"),
            result.get("orchestrator_plan"),
            result.get("orchestrator_final"),
            result.get("critic_plan"),
            result.get("critic_final"),
            result.get("engineer"),
            result.get("analyst"),
        )
        if isinstance(x, dict) and x.get("degraded") is True
    )
    return round(degraded_count / total_steps, 6) if total_steps > 0 else 0.0


def _compute_milestone_rate(result: dict[str, Any]) -> float:
    """计算里程碑达成率 (Milestone Achievement Rate).

    关键里程碑：
    1. intent 完成（有 primary_intent_type）
    2. plan 完成（有 plan_steps）
    3. execution 完成（engineer/analyst 至少一个有输出或有分析结果）
    4. finalize 完成（orchestrator_final 或 critic_final 有输出）
    
    注意：这里放宽了 execution 的判断标准，只要有 engineer/analyst 数据即认为达成，
    因为有些 read_only 任务可能不需要这两个 Agent 的深度分析。
    """
    milestones: list[bool] = []
    # M1: Intent
    intent = result.get("intent")
    milestones.append(
        isinstance(intent, dict) and bool(intent.get("primary_intent_type"))
    )
    # M2: Plan
    plan = result.get("orchestrator_plan")
    milestones.append(
        isinstance(plan, dict) and bool(plan.get("plan_steps"))
    )
    # M3: Execution - 放宽判断：只要有 engineer 或 analyst 数据就算达成
    eng = result.get("engineer")
    ana = result.get("analyst")
    # 只要有非空的字典就算有输出（不强制要求有 output 字段）
    has_eng = isinstance(eng, dict) and len(eng) > 0
    has_ana = isinstance(ana, dict) and len(ana) > 0
    milestones.append(has_eng or has_ana)
    # M4: Finalize
    final = result.get("orchestrator_final") or result.get("critic_final")
    has_final = isinstance(final, dict) and len(final) > 0
    milestones.append(has_final)
    achieved = sum(1 for m in milestones if m)
    return round(achieved / len(milestones), 6) if milestones else 0.0


def _compute_task_completion_score(result: dict[str, Any], task: dict[str, Any]) -> float:
    """计算任务完成度评分 (Task Completion Score).

    基于以下维度：
    1. 输出完整性 (是否有有效结论)
    2. 意图匹配度 (输出是否回应了任务)
    3. 质量指标 (schema 合规、证据完整)

    范围 [0, 1]，越高越好。
    """
    scores: list[float] = []

    # 1. 输出完整性
    final = result.get("orchestrator_final") or result.get("critic_final")
    if isinstance(final, dict):
        has_output = bool(final.get("output") or final.get("conclusion") or final.get("summary"))
        scores.append(1.0 if has_output else 0.0)
    else:
        scores.append(0.0)

    # 2. 质量指标综合
    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
    q_scores = [
        float(quality.get("step_reason_coverage") or 0.0),
        float(quality.get("receipt_binding_rate") or 0.0),
        1.0 - float(quality.get("evidence_missing_rate") or 1.0),
        1.0 - float(quality.get("contract_fail_rate") or 1.0),
    ]
    scores.append(sum(q_scores) / len(q_scores) if q_scores else 0.0)

    # 3. 里程碑达成加权
    milestone_rate = _compute_milestone_rate(result)
    scores.append(milestone_rate)

    return round(sum(scores) / len(scores), 6) if scores else 0.0


def _compute_hallucination_score(result: dict[str, Any]) -> float:
    """计算幻觉检测评分 (Hallucination Score).

    基于以下信号：
    1. 证据引用完整性 (evidence_missing_rate 越低越好)
    2. 契约合规性 (contract_fail_rate 越低越好)
    3. Receipt 绑定一致性 (receipt_binding_rate 越高越好)

    范围 [0, 1]，越高表示幻觉越少（越可信）。
    """
    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}

    # 证据完整性得分
    evidence_score = 1.0 - float(quality.get("evidence_missing_rate") or 1.0)

    # 契约合规得分
    contract_score = 1.0 - float(quality.get("contract_fail_rate") or 1.0)

    # Receipt 绑定得分
    binding_score = float(quality.get("receipt_binding_rate") or 0.0)

    # 综合得分
    return round((evidence_score + contract_score + binding_score) / 3.0, 6)


def _compute_tool_usage_efficiency(result: dict[str, Any]) -> dict[str, float]:
    """计算工具使用效率指标.

    Returns:
        - tool_call_success_rate: 工具调用成功率
        - tool_call_count: 工具调用次数
        - tool_efficiency_score: 综合效率得分（成功率高且次数适中得分高）
    """
    receipts = result.get("receipts") if isinstance(result.get("receipts"), list) else []

    if not receipts:
        return {
            "tool_call_success_rate": 0.0,
            "tool_call_count": 0.0,
            "tool_efficiency_score": 0.0,
        }

    total_calls = len(receipts)
    successful_calls = sum(
        1 for r in receipts
        if isinstance(r, dict) and r.get("ok") is True
    )

    success_rate = successful_calls / total_calls if total_calls > 0 else 0.0

    # 效率得分：成功率高得分高，但调用次数过多会略微扣分（避免滥用）
    # 理想调用次数为 1-3 次
    optimal_range = (1, 3)
    count_penalty = 0.0
    if total_calls < optimal_range[0]:
        count_penalty = 0.05  # 调用太少，可能没有充分利用工具
    elif total_calls > optimal_range[1]:
        count_penalty = min(0.2, (total_calls - optimal_range[1]) * 0.05)  # 调用过多

    efficiency_score = max(0.0, success_rate - count_penalty)

    return {
        "tool_call_success_rate": round(success_rate, 6),
        "tool_call_count": float(total_calls),
        "tool_efficiency_score": round(efficiency_score, 6),
    }


def _compute_error_recovery_rate(out: dict[str, Any], result: dict[str, Any]) -> float:
    """计算错误恢复率 (Error Recovery Rate).

    基于以下信号：
    1. 最终是否成功 (ok)
    2. 过程中是否有错误但最终恢复
    3. 降级模式触发但任务仍完成

    范围 [0, 1]，越高表示错误恢复能力越强。
    """
    # 最终成功 = 完美恢复（使用最外层的 ok，不是 result 内的）
    if out.get("ok") is True:
        return 1.0

    # 有错误但最终有输出（部分恢复）
    errors = result.get("errors") if isinstance(result.get("errors"), list) else []
    has_errors = len(errors) > 0

    final = result.get("orchestrator_final") or result.get("critic_final")
    has_partial_output = isinstance(final, dict) and bool(final.get("output"))

    if has_errors and has_partial_output:
        return 0.5  # 部分恢复

    return 0.0  # 完全失败


def _compute_plan_revision_count(result: dict[str, Any]) -> float:
    """计算 Plan 修正次数 (Plan Revision Count).

    基于 Critic 评审后重新规划的次数信号。
    从 orchestrator_plan 和 critic_plan 的差异推断。

    返回实际修正次数的 float 表示。
    """
    # 检查是否有 Critic 要求重新规划的信号
    critic_plan = result.get("critic_plan")
    orchestrator_plan = result.get("orchestrator_plan")

    if not isinstance(critic_plan, dict) or not isinstance(orchestrator_plan, dict):
        return 0.0

    # 如果 Critic 提出了 issues 或 suggested_fixes，视为需要修正
    critic_ok = critic_plan.get("ok") is True
    has_issues = bool(critic_plan.get("issues"))
    has_suggestions = bool(critic_plan.get("suggested_fixes"))

    if not critic_ok or has_issues or has_suggestions:
        return 1.0  # 至少修正一次

    return 0.0


def _compute_memory_system_efficiency(result: dict[str, Any]) -> dict[str, float]:
    """计算记忆系统效能指标.

    基于以下维度：
    1. 短期记忆使用（是否有记忆条目）
    2. 上下文完整性（run_context 是否保存）
    3. 跨会话一致性（如果有 session_id）

    Returns:
        - memory_usage_rate: 记忆使用比例
        - context_completeness: 上下文完整度
        - memory_efficiency_score: 综合效能得分
    """
    # 短期记忆使用
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    has_artifacts = len(artifacts) > 0

    # 上下文完整性检查
    run_id = result.get("run_id")
    has_run_context = bool(run_id)

    # 记忆使用比例（基于 artifacts 数量 vs 预期步骤数）
    expected_steps = 4  # intent, plan, execution, finalize
    actual_steps = len([a for a in artifacts.values() if isinstance(a, dict)])
    memory_usage_rate = min(1.0, actual_steps / expected_steps) if expected_steps > 0 else 0.0

    # 上下文完整度
    context_completeness = 0.0
    if has_run_context:
        context_completeness += 0.5
    if has_artifacts:
        context_completeness += 0.5

    # 综合效能得分
    efficiency_score = (memory_usage_rate + context_completeness) / 2.0

    return {
        "memory_usage_rate": round(memory_usage_rate, 6),
        "context_completeness": round(context_completeness, 6),
        "memory_efficiency_score": round(efficiency_score, 6),
    }


def workflow_output_to_eval_record(
    out: dict[str, Any],
    *,
    case_id: str,
    tags: list[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    """将 run_orchestrator_workflow 的返回转为评估流水线使用的单条 record."""
    result = out.get("result") if isinstance(out.get("result"), dict) else {}
    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
    receipts = result.get("receipts") if isinstance(result.get("receipts"), list) else []
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    approval = result.get("approval") if isinstance(result.get("approval"), dict) else {}
    task = result.get("task") if isinstance(result.get("task"), dict) else {}

    governance_blocked = sum(
        1
        for x in receipts
        if isinstance(x, dict)
        and isinstance(x.get("error"), str)
        and x.get("error") in {"approval_required", "rbac_denied"}
    )
    degraded_count = sum(
        1
        for x in (
            result.get("intent"),
            result.get("orchestrator_plan"),
            result.get("orchestrator_final"),
            result.get("critic_plan"),
            result.get("critic_final"),
            result.get("engineer"),
            result.get("analyst"),
        )
        if isinstance(x, dict) and x.get("degraded") is True
    )
    evidence_missing_steps: list[str] = []
    for sid, a in artifacts.items():
        if not isinstance(sid, str) or not isinstance(a, dict):
            continue
        step_output = a.get("output") if isinstance(a.get("output"), dict) else None
        if not isinstance(step_output, dict):
            continue
        ev = step_output.get("evidence")
        if isinstance(ev, dict) and not _has_evidence_refs(ev):
            evidence_missing_steps.append(sid)

    # 计算协作/过程指标 (Collaboration & Process Metrics)
    ids_score = _compute_ids(result, artifacts)  # 信息多样性，越高越好（传入 result 以获取 Agent 类型）
    upr = _compute_upr(result)  # 冗余路径比，越低越好
    milestone_rate = _compute_milestone_rate(result)  # 里程碑达成率，越高越好

    # 计算新增指标 (Agent System Metrics)
    task_completion_score = _compute_task_completion_score(result, task)
    hallucination_score = _compute_hallucination_score(result)
    tool_efficiency = _compute_tool_usage_efficiency(result)
    error_recovery_rate = _compute_error_recovery_rate(out, result)  # 传入 out 获取正确的 ok 字段
    plan_revision_count = _compute_plan_revision_count(result)
    memory_efficiency = _compute_memory_system_efficiency(result)

    # 把协作/过程指标也写入 quality，便于 metrics.py 统一汇总
    quality_with_collab = dict(quality) if isinstance(quality, dict) else {}
    quality_with_collab["ids_score"] = ids_score
    quality_with_collab["upr"] = upr
    quality_with_collab["milestone_achieved_rate"] = milestone_rate

    # 新增指标写入 quality
    quality_with_collab["task_completion_score"] = task_completion_score
    quality_with_collab["hallucination_score"] = hallucination_score
    quality_with_collab["tool_efficiency_score"] = tool_efficiency["tool_efficiency_score"]
    quality_with_collab["error_recovery_rate"] = error_recovery_rate
    quality_with_collab["plan_revision_count"] = plan_revision_count
    quality_with_collab["memory_efficiency_score"] = memory_efficiency["memory_efficiency_score"]

    return {
        "run_tag": "",  # 由 runner 填写
        "case_id": case_id,
        "repeat_index": 0,  # 由 runner 填写
        "tags": list(tags),
        "ok": bool(out.get("ok")),
        "latency_ms": float(out.get("latency_ms") or 0.0),
        "run_id": result.get("run_id"),
        "task_id": result.get("task_id"),
        "approval": approval,
        "quality": quality_with_collab,
        "errors": result.get("errors") if isinstance(result.get("errors"), list) else [],
        "tokens_total": int(result.get("tokens_total", 0) or 0),
        "governance_blocked_count": governance_blocked,
        "degraded_count": degraded_count,
        "approval_required": bool(approval.get("required")),
        "evidence_missing_steps": evidence_missing_steps,
        # 协作/过程指标（顶层也可直接访问）
        "ids_score": ids_score,
        "upr": upr,
        "milestone_achieved_rate": milestone_rate,
        # 新增 Agent System Metrics（顶层直接访问）
        "task_completion_score": task_completion_score,
        "hallucination_score": hallucination_score,
        "tool_call_success_rate": tool_efficiency["tool_call_success_rate"],
        "tool_call_count": tool_efficiency["tool_call_count"],
        "tool_efficiency_score": tool_efficiency["tool_efficiency_score"],
        "error_recovery_rate": error_recovery_rate,
        "plan_revision_count": plan_revision_count,
        "memory_usage_rate": memory_efficiency["memory_usage_rate"],
        "context_completeness": memory_efficiency["context_completeness"],
        "memory_efficiency_score": memory_efficiency["memory_efficiency_score"],
        "config": {
            "policy_version": config.get("policy_version"),
            "prompt_version": config.get("prompt_version"),
            "model": config.get("model"),
            "hitl_auto_approve": config.get("hitl_auto_approve"),
            "budget_profile": config.get("budget_profile"),
        },
    }
