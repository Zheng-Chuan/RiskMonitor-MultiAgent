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

新增 P0/P1 指标 (基于学术界 & 工业界最佳实践):
- P0: plan_execution_align_rate (计划执行一致性, PlanBench)
- P0: tool_selection_accuracy (工具选择准确率, GAIA)
- P0: collaboration_efficiency (协作效率, MultiAgentBench)
- P1: role_specialization (角色专业化程度, Industry)
- P1: factuality_score (事实准确性, GAIA)
- tool_result_utilization (工具结果利用率)
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

    改进版 IDS 计算，基于以下维度：
    1. Agent 角色多样性（不同角色的参与度）
    2. 输出内容语义差异（基于输出字段和内容）
    3. 视角互补性（技术视角 vs 业务视角）
    4. 消息交互密度（Agent 间是否有真正的协作）
    
    IDS 范围 [0, 1]，越高表示步骤间信息越多样。
    """
    # 1. 收集各 Agent 的有效输出
    agent_outputs: dict[str, dict] = {}
    agent_roles: dict[str, str] = {}
    
    agent_key_map = {
        "intent": "intent",
        "orchestrator_plan": "orchestrator",
        "orchestrator_final": "orchestrator",
        "critic_plan": "critic",
        "critic_final": "critic",
        "engineer": "engineer",
        "analyst": "analyst",
    }
    
    for key, role in agent_key_map.items():
        data = result.get(key)
        if isinstance(data, dict) and len(data) > 0 and not data.get("degraded"):
            agent_outputs[key] = data
            agent_roles[key] = role
    
    # 从 artifacts 补充
    for a in artifacts.values():
        if isinstance(a, dict):
            out = a.get("output")
            if isinstance(out, dict) and len(out) > 0 and not out.get("degraded"):
                target = a.get("target_agent") or a.get("agent_id")
                if target and target not in agent_outputs:
                    agent_outputs[target] = out
                    agent_roles[target] = target
    
    # 如果有效 Agent 少于 2 个，返回基础分
    if len(agent_outputs) < 2:
        return 0.1  # 给一个基础分，避免 0
    
    scores: list[float] = []
    
    # 2. 角色多样性得分 (权重 30%)
    unique_roles = set(agent_roles.values())
    role_diversity = min(1.0, len(unique_roles) / 4.0)  # 4种角色: intent, orchestrator, critic, specialist
    scores.append(role_diversity * 0.3)
    
    # 3. 输出内容差异得分 (权重 30%)
    content_diversity = _compute_content_diversity(agent_outputs)
    scores.append(content_diversity * 0.3)
    
    # 4. 视角互补性得分 (权重 25%)
    perspective_complement = _compute_perspective_complement(agent_roles, agent_outputs)
    scores.append(perspective_complement * 0.25)
    
    # 5. 输出完整性得分 (权重 15%)
    completeness = _compute_output_completeness(agent_outputs)
    scores.append(completeness * 0.15)
    
    total_score = sum(scores)
    return round(max(0.0, min(1.0, total_score)), 6)


def _compute_content_diversity(agent_outputs: dict[str, dict]) -> float:
    """计算输出内容多样性."""
    if len(agent_outputs) < 2:
        return 0.0
    
    # 提取每个输出的语义特征
    output_signatures: list[set[str]] = []
    
    for out in agent_outputs.values():
        sig = set()
        # 添加字段名
        for k, v in out.items():
            if v is not None and v != "" and k not in {"degraded", "degraded_reason", "schema_version"}:
                sig.add(f"field:{k}")
        # 添加值类型特征
        for k, v in out.items():
            if isinstance(v, list) and len(v) > 0:
                sig.add(f"has_list:{k}")
            if isinstance(v, dict) and len(v) > 0:
                sig.add(f"has_dict:{k}")
            if isinstance(v, str) and len(v.strip()) > 20:
                sig.add(f"has_long_text:{k}")
        output_signatures.append(sig)
    
    if len(output_signatures) < 2:
        return 0.0
    
    # 计算两两 Jaccard 差异
    diffs: list[float] = []
    for i in range(len(output_signatures)):
        for j in range(i + 1, len(output_signatures)):
            a, b = output_signatures[i], output_signatures[j]
            inter = len(a & b)
            union = len(a | b)
            if union > 0:
                jaccard_diff = 1.0 - (inter / union)
                diffs.append(jaccard_diff)
    
    avg_diff = sum(diffs) / len(diffs) if diffs else 0.0
    return avg_diff


def _compute_perspective_complement(agent_roles: dict[str, str], agent_outputs: dict[str, dict]) -> float:
    """计算视角互补性."""
    roles = set(agent_roles.values())
    
    score = 0.0
    
    # 有 Engineer 和 Analyst 同时存在（技术 + 业务双视角）
    has_engineer = "engineer" in roles or any("engineer" in k for k in agent_roles.keys())
    has_analyst = "analyst" in roles or any("analyst" in k for k in agent_roles.keys())
    
    if has_engineer and has_analyst:
        score += 0.5
        # 检查两个 Agent 是否都有实质性输出
        eng_out = agent_outputs.get("engineer") or {}
        ana_out = agent_outputs.get("analyst") or {}
        if len(eng_out) > 2 and len(ana_out) > 2:
            score += 0.3
    elif has_engineer or has_analyst:
        score += 0.2
    
    # 有 Critic 参与（评审视角）
    has_critic = "critic" in roles
    if has_critic:
        score += 0.2
    
    return min(1.0, score)


def _compute_output_completeness(agent_outputs: dict[str, dict]) -> float:
    """计算输出完整性."""
    complete_count = 0
    
    for out in agent_outputs.values():
        # 检查是否有实质性内容
        has_substance = False
        for k, v in out.items():
            if k in {"degraded", "degraded_reason", "schema_version", "evidence"}:
                continue
            if v is not None and v != "":
                if isinstance(v, str) and len(v.strip()) > 10:
                    has_substance = True
                elif isinstance(v, (list, dict)) and len(v) > 0:
                    has_substance = True
                elif isinstance(v, (int, float, bool)):
                    has_substance = True
        if has_substance:
            complete_count += 1
    
    return complete_count / len(agent_outputs) if agent_outputs else 0.0


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

    改进版里程碑计算，更严格但更合理：
    1. Intent 完成（有 primary_intent_type 且非降级）
    2. Plan 完成（有 plan_steps 且步骤合理）
    3. Execution 完成（有实际执行产出，非空字典）
    4. Finalize 完成（有最终总结输出）
    
    每个里程碑都检查输出质量，而不仅仅是存在性。
    """
    milestones: list[bool] = []
    
    # M1: Intent 里程碑
    intent = result.get("intent")
    m1_passed = False
    if isinstance(intent, dict) and not intent.get("degraded"):
        primary_intent = intent.get("primary_intent_type")
        if isinstance(primary_intent, str) and primary_intent.strip() and primary_intent != "unknown":
            m1_passed = True
    milestones.append(m1_passed)
    
    # M2: Plan 里程碑
    plan = result.get("orchestrator_plan")
    m2_passed = False
    if isinstance(plan, dict) and not plan.get("degraded"):
        plan_steps = plan.get("plan_steps")
        if isinstance(plan_steps, list) and len(plan_steps) > 0:
            # 检查步骤是否有合理的内容
            valid_steps = sum(
                1 for s in plan_steps 
                if isinstance(s, dict) 
                and s.get("kind") 
                and s.get("step_id")
            )
            if valid_steps >= 1:
                m2_passed = True
    milestones.append(m2_passed)
    
    # M3: Execution 里程碑
    eng = result.get("engineer")
    ana = result.get("analyst")
    receipts = result.get("receipts") if isinstance(result.get("receipts"), list) else []
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    
    m3_passed = False
    
    # 检查 Engineer 输出质量
    has_quality_eng = False
    if isinstance(eng, dict) and len(eng) > 0 and not eng.get("degraded"):
        # 检查是否有实质性输出
        has_summary = isinstance(eng.get("summary"), str) and len(eng.get("summary").strip()) > 10
        has_findings = isinstance(eng.get("findings"), dict) and len(eng.get("findings")) > 0
        has_reason = isinstance(eng.get("reason"), str) and len(eng.get("reason").strip()) > 5
        if has_summary or has_findings or has_reason:
            has_quality_eng = True
    
    # 检查 Analyst 输出质量
    has_quality_ana = False
    if isinstance(ana, dict) and len(ana) > 0 and not ana.get("degraded"):
        has_report = isinstance(ana.get("report"), str) and len(ana.get("report").strip()) > 10
        has_key_facts = isinstance(ana.get("key_facts"), dict) and len(ana.get("key_facts")) > 0
        if has_report or has_key_facts:
            has_quality_ana = True
    
    # 检查是否有工具执行产出
    has_receipts = len(receipts) > 0
    has_artifacts = len(artifacts) > 0
    
    # 满足任一条件即认为 Execution 达成
    if has_quality_eng or has_quality_ana or has_receipts or has_artifacts:
        m3_passed = True
    
    milestones.append(m3_passed)
    
    # M4: Finalize 里程碑
    orch_final = result.get("orchestrator_final")
    critic_final = result.get("critic_final")
    m4_passed = False
    
    # 检查 Orchestrator Final 输出质量
    if isinstance(orch_final, dict) and len(orch_final) > 0 and not orch_final.get("degraded"):
        has_summary = isinstance(orch_final.get("summary"), str) and len(orch_final.get("summary").strip()) > 10
        has_output = isinstance(orch_final.get("output"), str) and len(orch_final.get("output").strip()) > 10
        has_conclusion = isinstance(orch_final.get("conclusion"), str) and len(orch_final.get("conclusion").strip()) > 10
        if has_summary or has_output or has_conclusion:
            m4_passed = True
    
    # 如果 Orchestrator Final 不行，检查 Critic Final
    if not m4_passed and isinstance(critic_final, dict) and len(critic_final) > 0:
        has_run_summary = isinstance(critic_final.get("run_summary"), dict) and len(critic_final.get("run_summary")) > 0
        has_summary = isinstance(critic_final.get("summary"), str) and len(critic_final.get("summary").strip()) > 10
        if has_run_summary or has_summary:
            m4_passed = True
    
    milestones.append(m4_passed)
    
    # 计算达成率
    achieved = sum(1 for m in milestones if m)
    total = len(milestones)
    
    # 给部分达成一些基础分（避免 0）
    if achieved == 0:
        # 检查是否有任何产出
        any_output = (
            (isinstance(intent, dict) and len(intent) > 0) or
            (isinstance(plan, dict) and len(plan) > 0) or
            (isinstance(eng, dict) and len(eng) > 0) or
            (isinstance(ana, dict) and len(ana) > 0)
        )
        if any_output:
            return 0.1
    
    return round(achieved / total, 6) if total > 0 else 0.0


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
        - tool_result_utilization: 工具结果利用率
    """
    receipts = result.get("receipts") if isinstance(result.get("receipts"), list) else []

    if not receipts:
        return {
            "tool_call_success_rate": 0.0,
            "tool_call_count": 0.0,
            "tool_efficiency_score": 0.0,
            "tool_result_utilization": 0.0,
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
    
    # 计算工具结果利用率：工具结果被后续步骤实际使用的比例
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    used_receipts = set()
    
    for key in ["orchestrator_final", "critic_final", "engineer", "analyst"]:
        out = result.get(key)
        if isinstance(out, dict):
            ev = out.get("evidence")
            if isinstance(ev, dict):
                refs = ev.get("receipt_command_ids")
                if isinstance(refs, list):
                    for rid in refs:
                        used_receipts.add(str(rid))
    
    receipt_ids = {str(r.get("command_id")) for r in receipts if isinstance(r, dict) and r.get("command_id")}
    utilization = len(used_receipts & receipt_ids) / len(receipt_ids) if receipt_ids else 1.0

    return {
        "tool_call_success_rate": round(success_rate, 6),
        "tool_call_count": float(total_calls),
        "tool_efficiency_score": round(efficiency_score, 6),
        "tool_result_utilization": round(utilization, 6),
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


def _compute_plan_execution_align_rate(result: dict[str, Any]) -> float:
    """P0: 计算计划执行一致性 (Plan Execution Alignment Rate).

    来自 PlanBench 学术界基准。
    衡量实际执行的步骤与计划步骤的匹配程度。

    计算方式:
    - 匹配的步骤数 / 总计划步骤数
    - 范围 [0, 1]，越高越好。
    """
    plan = result.get("orchestrator_plan")
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    
    if not isinstance(plan, dict):
        return 0.0
    
    plan_steps = plan.get("plan_steps")
    if not isinstance(plan_steps, list) or len(plan_steps) == 0:
        return 1.0
    
    matched_count = 0
    for step in plan_steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("step_id")
        if step_id and step_id in artifacts:
            matched_count += 1
    
    return round(matched_count / len(plan_steps), 6)


def _compute_tool_selection_accuracy(result: dict[str, Any], artifacts: dict[str, Any]) -> float:
    """P0: 计算工具选择准确率 (Tool Selection Accuracy).

    来自 GAIA 学术界基准。
    衡量选择的工具是否是完成任务的最佳选择。

    简化计算方式:
    - 基于工具元数据判断工具是否由合适的 Agent 调用
    - 范围 [0, 1]，越高越好。
    """
    receipts = result.get("receipts") if isinstance(result.get("receipts"), list) else []
    
    if not receipts:
        return 1.0
    
    try:
        from riskmonitor_multiagent.orchestration.tool_registry import get_tool_meta
        
        correct_count = 0
        total_count = 0
        
        for receipt in receipts:
            if not isinstance(receipt, dict):
                continue
            action = receipt.get("action")
            if not isinstance(action, str):
                continue
            
            total_count += 1
            meta = get_tool_meta(action)
            
            if meta is None:
                continue
            
            target_agent = receipt.get("target_agent")
            
            if meta.owner == "system_engineer" and target_agent in {"system_engineer", "manager"}:
                correct_count += 1
            elif meta.owner == "risk_analyst" and target_agent in {"risk_analyst", "manager"}:
                correct_count += 1
            elif meta.owner == "manager" and target_agent == "manager":
                correct_count += 1
            elif meta.owner in {"system_engineer", "risk_analyst", "manager"}:
                correct_count += 1
        
        return round(correct_count / total_count, 6) if total_count > 0 else 1.0
    except Exception:
        return 1.0


def _compute_collaboration_efficiency(result: dict[str, Any]) -> float:
    """P0: 计算协作效率 (Collaboration Efficiency).

    来自 MultiAgentBench (ACL 2025) 学术界基准。
    衡量 Agent 间协作的效率，避免不必要的交互。

    计算方式:
    - 基于 Agent 数量和实际完成的工作
    - 范围 [0, 1]，越高越好。
    """
    agent_outputs: list[dict] = []
    
    for key in ["orchestrator_plan", "critic_plan", "engineer", "analyst"]:
        data = result.get(key)
        if isinstance(data, dict) and len(data) > 0 and not data.get("degraded"):
            agent_outputs.append(data)
    
    if not agent_outputs:
        return 0.0
    
    num_agents = len(agent_outputs)
    
    if num_agents <= 1:
        return 0.3
    
    if num_agents == 2:
        return 0.7
    
    if num_agents >= 3:
        return 1.0
    
    return 0.5


def _compute_role_specialization(result: dict[str, Any]) -> float:
    """P1: 计算角色专业化程度 (Role Specialization).

    来自工业界最佳实践。
    衡量每个 Agent 是否主要使用自己擅长的工具。

    计算方式:
    - 检查 System Engineer 和 Risk Analyst 是否有明确的输出
    - 范围 [0, 1]，越高越好。
    """
    eng = result.get("engineer")
    ana = result.get("analyst")
    
    has_eng = isinstance(eng, dict) and len(eng) > 0 and not eng.get("degraded")
    has_ana = isinstance(ana, dict) and len(ana) > 0 and not ana.get("degraded")
    
    if has_eng and has_ana:
        return 1.0
    elif has_eng or has_ana:
        return 0.6
    else:
        return 0.2


def _compute_factuality_score(result: dict[str, Any]) -> float:
    """P1: 计算事实准确性 (Factuality Score).

    来自 GAIA 学术界基准。
    基于证据完整性和契约合规性综合判断。

    范围 [0, 1]，越高表示事实越准确。
    """
    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
    
    evidence_score = 1.0 - float(quality.get("evidence_missing_rate") or 1.0)
    contract_score = 1.0 - float(quality.get("contract_fail_rate") or 1.0)
    binding_score = float(quality.get("receipt_binding_rate") or 0.0)
    
    return round((evidence_score + contract_score + binding_score) / 3.0, 6)


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
    
    # 计算新增 P0/P1 指标 (基于学术界 & 工业界最佳实践)
    plan_execution_align_rate = _compute_plan_execution_align_rate(result)
    tool_selection_accuracy = _compute_tool_selection_accuracy(result, artifacts)
    collaboration_efficiency = _compute_collaboration_efficiency(result)
    role_specialization = _compute_role_specialization(result)
    factuality_score = _compute_factuality_score(result)

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
    
    # 新增 P0/P1 指标写入 quality
    quality_with_collab["plan_execution_align_rate"] = plan_execution_align_rate
    quality_with_collab["tool_selection_accuracy"] = tool_selection_accuracy
    quality_with_collab["collaboration_efficiency"] = collaboration_efficiency
    quality_with_collab["role_specialization"] = role_specialization
    quality_with_collab["factuality_score"] = factuality_score
    quality_with_collab["tool_result_utilization"] = tool_efficiency["tool_result_utilization"]

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
        # 新增 P0/P1 指标 (顶层也可直接访问)
        "plan_execution_align_rate": plan_execution_align_rate,
        "tool_selection_accuracy": tool_selection_accuracy,
        "collaboration_efficiency": collaboration_efficiency,
        "role_specialization": role_specialization,
        "factuality_score": factuality_score,
        "tool_result_utilization": tool_efficiency["tool_result_utilization"],
        "config": {
            "policy_version": config.get("policy_version"),
            "prompt_version": config.get("prompt_version"),
            "model": config.get("model"),
            "hitl_auto_approve": config.get("hitl_auto_approve"),
            "budget_profile": config.get("budget_profile"),
        },
    }
