"""
多 Agent 协作系统评估契约.

专门用于评估多 Agent 协作模式的工作流输出.
"""

from __future__ import annotations

import json
from typing import Any

from riskmonitor_multiagent.utils.validation import has_evidence_refs


def _compute_ids_multiagent(result: dict[str, Any]) -> float:
    """计算信息多样性 (Information Diversity Score) - 多 Agent 版本.

    基于以下维度：
    1. Agent 角色多样性（不同角色的参与度）
    2. 消息交互密度（Agent 间是否有真正的协作）
    3. 输出内容语义差异
    4. 视角互补性

    IDS 范围 [0, 1]，越高表示步骤间信息越多样。
    """
    # 获取消息历史
    conversation_history = result.get("conversation_history", [])
    if not isinstance(conversation_history, list):
        return 0.0

    # 1. 角色多样性
    agent_ids = set()
    for msg in conversation_history:
        if isinstance(msg, dict):
            from_agent = msg.get("from_agent")
            if isinstance(from_agent, str):
                agent_ids.add(from_agent)

    unique_agent_count = len(agent_ids)
    if unique_agent_count < 2:
        return 0.1

    role_diversity = min(1.0, unique_agent_count / 5.0)

    # 2. 消息交互密度
    message_count = len(conversation_history)
    if message_count <= 2:
        interaction_density = 0.2
    elif message_count <= 5:
        interaction_density = 0.5
    elif message_count <= 10:
        interaction_density = 0.8
    else:
        interaction_density = 1.0

    # 3. 输出完整性
    has_engineer = "system_engineer" in agent_ids
    has_analyst = "risk_analyst" in agent_ids
    has_critic = "critic" in agent_ids
    has_orchestrator = "orchestrator" in agent_ids

    output_completeness = 0.0
    if has_engineer:
        output_completeness += 0.25
    if has_analyst:
        output_completeness += 0.25
    if has_critic:
        output_completeness += 0.25
    if has_orchestrator:
        output_completeness += 0.25

    # 4. 视角互补性
    perspective_complement = 0.0
    if has_engineer and has_analyst:
        perspective_complement += 0.5
    if has_critic:
        perspective_complement += 0.3
    if has_orchestrator:
        perspective_complement += 0.2

    # 综合得分
    total_score = (
        role_diversity * 0.3 +
        interaction_density * 0.3 +
        output_completeness * 0.2 +
        perspective_complement * 0.2
    )

    return round(max(0.0, min(1.0, total_score)), 6)


def _compute_role_specialization_multiagent(result: dict[str, Any]) -> float:
    """计算角色专业化程度 (Role Specialization) - 多 Agent 版本.

    衡量每个 Agent 是否主要使用自己擅长的工具。
    """
    conversation_history = result.get("conversation_history", [])
    if not isinstance(conversation_history, list):
        return 0.0

    agent_messages: dict[str, int] = {}

    for msg in conversation_history:
        if isinstance(msg, dict):
            from_agent = msg.get("from_agent")
            if isinstance(from_agent, str):
                agent_messages[from_agent] = agent_messages.get(from_agent, 0) + 1

    if not agent_messages:
        return 0.0

    # 检查主要角色是否参与
    has_engineer = "system_engineer" in agent_messages
    has_analyst = "risk_analyst" in agent_messages
    has_critic = "critic" in agent_messages

    if has_engineer and has_analyst and has_critic:
        return 1.0
    elif has_engineer and has_analyst:
        return 0.8
    elif has_engineer or has_analyst:
        return 0.6
    else:
        return 0.2


def _compute_collaboration_efficiency_multiagent(result: dict[str, Any]) -> float:
    """计算协作效率 (Collaboration Efficiency) - 多 Agent 版本.

    来自 MultiAgentBench (ACL 2025) 学术界基准。
    衡量 Agent 间协作的效率，避免不必要的交互。
    """
    conversation_history = result.get("conversation_history", [])
    if not isinstance(conversation_history, list):
        return 0.0

    message_count = len(conversation_history)

    if message_count <= 3:
        return 0.3
    elif message_count <= 6:
        return 0.7
    elif message_count <= 10:
        return 1.0
    else:
        return 0.8


def _compute_milestone_rate_multiagent(result: dict[str, Any]) -> float:
    """计算里程碑达成率 (Milestone Achievement Rate) - 多 Agent 版本.

    改进版里程碑计算，更严格但更合理：
    1. Intent 完成
    2. Plan 完成
    3. Execution 完成（两个 Specialist 都有输出）
    4. Finalize 完成（有最终总结输出）
    """
    milestones: list[bool] = []

    conversation_history = result.get("conversation_history", [])

    # M1: Intent 里程碑
    has_intent = any(
        isinstance(msg, dict) and msg.get("from_agent") == "intent"
        for msg in conversation_history
    )
    milestones.append(has_intent)

    # M2: Plan 里程碑
    has_orchestrator = any(
        isinstance(msg, dict) and msg.get("from_agent") == "orchestrator"
        for msg in conversation_history
    )
    milestones.append(has_orchestrator)

    # M3: Execution 里程碑
    has_engineer = any(
        isinstance(msg, dict) and msg.get("from_agent") == "system_engineer"
        for msg in conversation_history
    )
    has_analyst = any(
        isinstance(msg, dict) and msg.get("from_agent") == "risk_analyst"
        for msg in conversation_history
    )
    milestones.append(has_engineer or has_analyst)

    # M4: Finalize 里程碑
    has_critic = any(
        isinstance(msg, dict) and msg.get("from_agent") == "critic"
        for msg in conversation_history
    )
    milestones.append(has_critic)

    achieved = sum(1 for m in milestones if m)
    total = len(milestones)

    if achieved == 0:
        if len(conversation_history) > 0:
            return 0.1

    return round(achieved / total, 6) if total > 0 else 0.0


def multiagent_output_to_eval_record(
    out: dict[str, Any],
    *,
    case_id: str,
    tags: list[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    """
    将多 Agent 协作工作流的输出转为评估流水线使用的单条 record.

    专门用于评估多 Agent 协作模式.
    """
    result = out.get("result") if isinstance(out.get("result"), dict) else {}
    task = result.get("task") if isinstance(result.get("task"), dict) else {}

    # 计算多 Agent 协作指标
    ids_score = _compute_ids_multiagent(result)
    role_specialization = _compute_role_specialization_multiagent(result)
    collaboration_efficiency = _compute_collaboration_efficiency_multiagent(result)
    milestone_rate = _compute_milestone_rate_multiagent(result)

    conversation_history = result.get("conversation_history", [])
    message_count = len(conversation_history) if isinstance(conversation_history, list) else 0

    quality_with_collab = {}
    quality_with_collab["ids_score"] = ids_score
    quality_with_collab["role_specialization"] = role_specialization
    quality_with_collab["collaboration_efficiency"] = collaboration_efficiency
    quality_with_collab["milestone_achieved_rate"] = milestone_rate
    quality_with_collab["message_count"] = float(message_count)

    return {
        "run_tag": "",
        "case_id": case_id,
        "repeat_index": 0,
        "tags": list(tags),
        "ok": bool(out.get("ok")),
        "latency_ms": float(out.get("latency_ms") or 0.0),
        "run_id": result.get("run_id"),
        "task_id": result.get("task_id"),
        "quality": quality_with_collab,
        "errors": result.get("errors") if isinstance(result.get("errors"), list) else [],
        "tokens_total": int(result.get("tokens_total", 0) or 0),
        "ids_score": ids_score,
        "role_specialization": role_specialization,
        "collaboration_efficiency": collaboration_efficiency,
        "milestone_achieved_rate": milestone_rate,
        "message_count": float(message_count),
        "config": {
            "policy_version": config.get("policy_version"),
            "prompt_version": config.get("prompt_version"),
            "model": config.get("model"),
            "hitl_auto_approve": config.get("hitl_auto_approve"),
            "budget_profile": config.get("budget_profile"),
        },
    }
