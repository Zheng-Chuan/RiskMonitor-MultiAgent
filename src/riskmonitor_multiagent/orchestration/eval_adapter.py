"""评估契约：将工作流输出转换为评估流水线所需的记录格式.

业务侧唯一与「评估」相关的模块：仅负责从 run_orchestrator_workflow 的返回值
构造评估记录，不依赖 eval 包。评估流水线只依赖本函数，不感知工作流内部结构.

新增协作/过程指标（Industry Best Practice）:
- IDS (Information Diversity Score): 步骤间输出的语义差异度（高=协作好）
- UPR (Unnecessary Path Ratio): 冗余路径占比（低=效率高）
- Milestone (milestone_achieved_rate): 关键里程碑达成率
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


def _compute_ids(artifacts: dict[str, Any]) -> float:
    """计算信息多样性 (Information Diversity Score).

    基于各步骤输出的 key 集合差异度近似语义多样性。
    IDS = 1 - (平均 pairwise Jaccard 相似度)
    范围 [0, 1]，越高表示步骤间信息越多样。
    """
    if not artifacts:
        return 0.0
    outputs: list[set] = []
    for a in artifacts.values():
        if not isinstance(a, dict):
            continue
        out = a.get("output")
        if isinstance(out, dict):
            # 收集所有非空值的 key
            keys = {k for k, v in out.items() if v is not None and v != ""}
            if keys:
                outputs.append(keys)
    n = len(outputs)
    if n <= 1:
        return 0.0
    # 计算平均 Jaccard 相似度
    sims: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = outputs[i], outputs[j]
            inter = len(a & b)
            union = len(a | b)
            sim = inter / union if union > 0 else 1.0
            sims.append(sim)
    avg_sim = sum(sims) / len(sims) if sims else 1.0
    return round(1.0 - avg_sim, 6)


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
    3. execution 完成（engineer/analyst 至少一个有输出）
    4. finalize 完成（orchestrator_final 或 critic_final 有输出）
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
    # M3: Execution
    eng = result.get("engineer")
    ana = result.get("analyst")
    milestones.append(
        (isinstance(eng, dict) and bool(eng.get("output")))
        or (isinstance(ana, dict) and bool(ana.get("output")))
    )
    # M4: Finalize
    final = result.get("orchestrator_final") or result.get("critic_final")
    milestones.append(
        isinstance(final, dict) and bool(final.get("output") or final.get("conclusion"))
    )
    achieved = sum(1 for m in milestones if m)
    return round(achieved / len(milestones), 6) if milestones else 0.0


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
    ids_score = _compute_ids(artifacts)  # 信息多样性，越高越好
    upr = _compute_upr(result)  # 冗余路径比，越低越好
    milestone_rate = _compute_milestone_rate(result)  # 里程碑达成率，越高越好

    # 把协作/过程指标也写入 quality，便于 metrics.py 统一汇总
    quality_with_collab = dict(quality) if isinstance(quality, dict) else {}
    quality_with_collab["ids_score"] = ids_score
    quality_with_collab["upr"] = upr
    quality_with_collab["milestone_achieved_rate"] = milestone_rate

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
        "config": {
            "policy_version": config.get("policy_version"),
            "prompt_version": config.get("prompt_version"),
            "model": config.get("model"),
            "hitl_auto_approve": config.get("hitl_auto_approve"),
            "budget_profile": config.get("budget_profile"),
        },
    }
