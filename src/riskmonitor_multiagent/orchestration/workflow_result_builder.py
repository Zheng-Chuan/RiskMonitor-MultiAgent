"""
工作流结果构建模块.

从 proactive_workflow.py 提取的纯函数，负责构建各类运行结果字典.
"""

from __future__ import annotations

import os
import time
from typing import Any


def build_workflow_result(
    *,
    run_id: str,
    task: dict[str, Any],
    memory_enabled: bool,
    private_memory_enabled: bool,
    planning_memory: dict[str, Any],
    resume_request: dict[str, Any],
    persisted_memory: dict[str, Any],
    run_context: dict[str, Any],
    intent_result: Any,
    orchestrator_result: Any,
    critic_result: Any,
    critic_final_result: Any,
    engineer_result: Any,
    analyst_result: Any,
    execution_result: dict[str, Any],
    replan_details: dict[str, Any] | None,
    route_decision: dict[str, Any] | None,
    start_time: float,
) -> dict[str, Any]:
    """构建结果."""
    latency_ms = (time.time() - start_time) * 1000

    all_react_steps = []
    all_react_steps.extend(intent_result.react_steps)
    all_react_steps.extend(orchestrator_result.react_steps)
    all_react_steps.extend(critic_result.react_steps)
    all_react_steps.extend(critic_final_result.react_steps)
    all_react_steps.extend(engineer_result.react_steps)
    all_react_steps.extend(analyst_result.react_steps)

    all_llm_interactions = []
    all_llm_interactions.extend(intent_result.llm_interactions)
    all_llm_interactions.extend(orchestrator_result.llm_interactions)
    all_llm_interactions.extend(critic_result.llm_interactions)
    all_llm_interactions.extend(critic_final_result.llm_interactions)
    all_llm_interactions.extend(engineer_result.llm_interactions)
    all_llm_interactions.extend(analyst_result.llm_interactions)

    receipts = execution_result.get("receipts", [])
    approval_trace = build_approval_trace_items(
        approval_records=execution_result.get("approval_records", []),
        receipts=receipts,
    )

    result = {
        "status": execution_result.get("status", "completed"),
        "run_id": run_id,
        "entry_type": run_context.get("entry_type"),
        "run_context": run_context,
        "task_id": task.get("task_id"),
        "task": task,
        "route_decision": route_decision or {},
        "intent": intent_result.output,
        "task_graph": execution_result.get("task_graph", orchestrator_result.output.get("task_graph", {})),
        "task_graph_execution": execution_result.get("task_graph_execution", {}),
        "orchestrator_plan": orchestrator_result.output,
        "critic_plan": critic_result.output,
        "critic_final": critic_final_result.output,
        "replan": replan_details or {},
        "receipts": receipts,
        "approval_trace": approval_trace,
        "engineer": engineer_result.output,
        "analyst": analyst_result.output,
        "final_output": merge_final_with_critic(
            final_output=execution_result.get("final_output", {}),
            critic_final=critic_final_result.output,
        ),
        "react_steps": [
            {
                "step_id": s.step_id,
                "thought": s.thought,
                "reasoning": s.reasoning,
                "evidence": s.evidence,
                "action_type": s.action_type,
                "observation": s.observation,
            }
            for s in all_react_steps
        ],
        "bdi_states": {
            "intent": intent_result.bdi_state,
            "orchestrator": orchestrator_result.bdi_state,
            "critic": critic_result.bdi_state,
            "critic_final": critic_final_result.bdi_state,
            "engineer": engineer_result.bdi_state,
            "analyst": analyst_result.bdi_state,
        },
        "llm_interactions": all_llm_interactions,
        "latency_ms": latency_ms,
        "errors": execution_result.get("task_graph_execution", {}).get("errors", []),
    }
    if memory_enabled:
        result["memory_hits"] = planning_memory.get("hits", [])
        result["planning_memory"] = planning_memory.get("summary", {})
        result["resume_memory_state"] = resume_request.get("memory_state", [])
        result["shared_memory_board"] = planning_memory.get("shared_board", [])
        result["private_memory_state"] = (
            planning_memory.get("private_memory_state", {})
            if private_memory_enabled
            else {}
        )
        result["run_summary"] = persisted_memory.get("run_summary", {})
        result["procedural_lesson"] = (
            persisted_memory.get("lesson_entry")
            if isinstance(persisted_memory.get("lesson_entry"), dict)
            else {}
        )
        result["long_term_experience"] = (
            persisted_memory.get("long_term_experience")
            if isinstance(persisted_memory.get("long_term_experience"), dict)
            else {}
        )
        result["rejected_experience"] = (
            persisted_memory.get("rejected_experience")
            if isinstance(persisted_memory.get("rejected_experience"), dict)
            else {}
        )
        result["memory_policy"] = (
            persisted_memory.get("memory_policy")
            if isinstance(persisted_memory.get("memory_policy"), dict)
            else {}
        )
        result["approval_memory"] = []
    if isinstance(task.get("trigger_event_id"), str) and task.get("trigger_event_id"):
        result["trigger"] = {
            "event_id": task.get("trigger_event_id"),
            "reason": task.get("trigger_reason"),
            "evidence": task.get("trigger_evidence", {}),
        }
    return result


def build_blocked_event_result(
    *,
    event: dict[str, Any],
    run_context: dict[str, Any],
    reason: str,
    budget_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "run_id": run_context.get("run_id"),
        "entry_type": run_context.get("entry_type"),
        "run_context": run_context,
        "task_id": run_context.get("task_id"),
        "task": {
            "task_id": run_context.get("task_id"),
            "source": "system_event",
            "payload": event.get("payload", {}),
        },
        "route_decision": {},
        "intent": {},
        "task_graph": {},
        "task_graph_execution": {},
        "orchestrator_plan": {},
        "critic_plan": {},
        "critic_final": {},
        "replan": {},
        "receipts": [],
        "approval_trace": [],
        "engineer": {},
        "analyst": {},
        "final_output": {},
        "react_steps": [],
        "bdi_states": {},
        "llm_interactions": [],
        "latency_ms": 0.0,
        "errors": [reason],
        "trigger": {
            "event_id": event.get("event_id"),
            "reason": reason,
            "evidence": budget_evidence,
        },
        "governance": {
            "proactive_budget": {
                "allowed": False,
                "reason": reason,
                "evidence": budget_evidence,
            }
        },
    }


def build_invalid_event_result(
    *,
    event: dict[str, Any],
    run_context: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "run_id": run_context.get("run_id"),
        "entry_type": run_context.get("entry_type"),
        "run_context": run_context,
        "task_id": run_context.get("task_id"),
        "task": {"task_id": run_context.get("task_id"), "source": "system_event", "payload": event.get("payload", {})},
        "route_decision": {},
        "intent": {},
        "task_graph": {},
        "task_graph_execution": {},
        "orchestrator_plan": {},
        "critic_plan": {},
        "critic_final": {},
        "replan": {},
        "receipts": [],
        "approval_trace": [],
        "engineer": {},
        "analyst": {},
        "final_output": {},
        "react_steps": [],
        "bdi_states": {},
        "llm_interactions": [],
        "latency_ms": 0.0,
        "errors": [reason],
        "trigger": {
            "event_id": event.get("event_id"),
            "reason": reason,
            "evidence": {"event_type": event.get("event_type")},
        },
    }


def build_approval_trace_items(
    *,
    approval_records: list[dict[str, Any]] | None,
    receipts: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    trace_items: list[dict[str, Any]] = []
    if isinstance(approval_records, list):
        for record in approval_records:
            if not isinstance(record, dict):
                continue
            trace_items.append(
                {
                    "approval_id": record.get("approval_id"),
                    "level": record.get("level"),
                    "step_id": record.get("step_id"),
                    "command_id": record.get("command_id"),
                    "tool_name": record.get("tool_name"),
                    "approval_state": record.get("state"),
                    "required": record.get("required"),
                    "reason": record.get("reason"),
                    "risk_level": record.get("risk_level"),
                    "impact_scope": record.get("impact_scope", []),
                    "recommended_action": record.get("recommended_action"),
                    "actor": record.get("actor"),
                    "note": record.get("note"),
                    "approval_trace": {
                        "required": record.get("required"),
                        "current_state": record.get("state"),
                        "history": [{"state": record.get("state"), "reason": record.get("error") or record.get("reason")}],
                    },
                }
            )
    if trace_items:
        return trace_items
    if not isinstance(receipts, list):
        return []
    return [
        {
            "approval_id": f"command:{receipt.get('command_id')}",
            "level": "command",
            "step_id": receipt.get("step_id"),
            "command_id": receipt.get("command_id"),
            "tool_name": receipt.get("tool_name"),
            "approval_state": receipt.get("approval_state"),
            "required": (receipt.get("approval_trace") or {}).get("required"),
            "reason": ((receipt.get("evidence") or {}).get("reason") if isinstance(receipt.get("evidence"), dict) else None),
            "risk_level": ((((receipt.get("inputs") or {}).get("_event") or {}).get("severity")) if isinstance((receipt.get("inputs") or {}).get("_event"), dict) else None),
            "impact_scope": [],
            "recommended_action": None,
            "actor": ((receipt.get("inputs") or {}).get("approval") or {}).get("actor") if isinstance((receipt.get("inputs") or {}).get("approval"), dict) else None,
            "note": ((receipt.get("inputs") or {}).get("approval") or {}).get("note") if isinstance((receipt.get("inputs") or {}).get("approval"), dict) else None,
            "approval_trace": receipt.get("approval_trace"),
        }
        for receipt in receipts
        if isinstance(receipt, dict)
        and receipt.get("side_effect") is True
    ]


def normalize_critic_final_output(
    *,
    critic_output: dict[str, Any],
    receipts: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """确保最终审查结果总是带上可追溯的 receipt 证据链."""
    normalized = dict(critic_output) if isinstance(critic_output, dict) else {}
    receipt_command_ids = [
        receipt.get("command_id")
        for receipt in (receipts or [])
        if isinstance(receipt, dict) and isinstance(receipt.get("command_id"), str)
    ]

    evidence = normalized.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    evidence["receipt_command_ids"] = receipt_command_ids
    normalized["evidence"] = evidence

    run_summary = normalized.get("run_summary")
    if not isinstance(run_summary, dict):
        run_summary = {}
    run_summary["receipt_command_ids"] = receipt_command_ids
    normalized["run_summary"] = run_summary

    normalized.setdefault("ok", True)
    normalized.setdefault("issues", [])
    normalized.setdefault("suggested_fixes", [])
    return normalized


def merge_final_with_critic(
    *,
    final_output: dict[str, Any],
    critic_final: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(final_output) if isinstance(final_output, dict) else {}
    if isinstance(critic_final, dict):
        summary = critic_final.get("run_summary")
        if isinstance(summary, dict):
            merged["critic_run_summary"] = summary
        evidence = critic_final.get("evidence")
        if isinstance(evidence, dict) and isinstance(evidence.get("receipt_command_ids"), list):
            merged.setdefault("receipt_command_ids", evidence.get("receipt_command_ids"))
    return merged


def build_workflow_output(
    *,
    task: dict[str, Any],
    run_id: str,
    result: dict[str, Any],
    start_time: float,
) -> dict[str, Any]:
    """把 workflow 结果补成统一运行输出."""
    react_steps = result.get("react_steps", [])

    step_reason_coverage = 1.0
    evidence_missing_rate = 0.0

    if react_steps:
        steps_with_reason = sum(1 for s in react_steps if s.get("reasoning"))
        steps_with_evidence = sum(1 for s in react_steps if s.get("evidence"))
        step_reason_coverage = steps_with_reason / len(react_steps)
        evidence_missing_rate = 1.0 - (steps_with_evidence / len(react_steps))

    latency_ms = (time.time() - start_time) * 1000
    llm_interactions = result.get("llm_interactions", [])
    total_tokens = sum(i.get("tokens_used", 0) for i in llm_interactions)
    approval_trace = result.get("approval_trace", [])
    receipts = result.get("receipts", []) if isinstance(result.get("receipts"), list) else []
    task_graph_execution = (
        result.get("task_graph_execution")
        if isinstance(result.get("task_graph_execution"), dict)
        else {}
    )
    critic_plan = result.get("critic_plan", {}) if isinstance(result.get("critic_plan"), dict) else {}
    tool_steps = [
        item
        for item in task_graph_execution.get("trace", []) or []
        if isinstance(item, dict) and item.get("kind") == "tool_call"
    ]
    command_count = len(tool_steps)
    receipt_count = len([item for item in receipts if isinstance(item, dict)])
    receipt_binding_rate = 1.0 if command_count == 0 else min(1.0, receipt_count / command_count)
    contract_error_count = 0
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        schema_errors = receipt.get("schema_errors")
        if isinstance(schema_errors, list) and schema_errors:
            contract_error_count += 1
    contract_fail_rate = 0.0 if receipt_count == 0 else contract_error_count / receipt_count
    quality = {
        "evidence_missing_rate": evidence_missing_rate,
        "step_reason_coverage": step_reason_coverage,
        "receipt_binding_rate": receipt_binding_rate,
        "contract_fail_rate": contract_fail_rate,
        "tool_call_count": command_count,
        "receipt_count": receipt_count,
        "approval_count": len([item for item in approval_trace if isinstance(item, dict)]),
        "replan_count": 1 if isinstance(result.get("replan"), dict) and result.get("replan") else 0,
        "message_trace_completeness": compute_message_trace_completeness(
            result=result,
            command_count=command_count,
            receipt_count=receipt_count,
            approval_count=len([item for item in approval_trace if isinstance(item, dict)]),
        ),
    }
    approval_required = any(
        isinstance(item, dict)
        and (
            item.get("approval_state") in {"pending", "approved", "approved_but_failed", "rejected", "expired"}
            or (
                isinstance(item.get("approval_trace"), dict)
                and bool(item.get("approval_trace", {}).get("required"))
            )
        )
        for item in approval_trace
    ) or bool(critic_plan.get("require_human_approval"))
    approval_approved = not approval_required
    if approval_required and approval_trace:
        approval_approved = not any(
            isinstance(item, dict) and item.get("approval_state") in {"pending", "rejected", "expired"}
            for item in approval_trace
        )
    elif approval_required:
        approval_approved = os.getenv("HITL_AUTO_APPROVE", "1").strip() not in {"0", "false", "False"}

    effective_run_id = result.get("run_id") if isinstance(result.get("run_id"), str) and result.get("run_id") else run_id
    effective_status = result.get("status")
    if effective_status == "blocked" and approval_required:
        effective_status = "pending_approval"
    output = dict(result)
    output.update(
        {
            "ok": effective_status == "completed",
            "latency_ms": latency_ms,
            "run_id": effective_run_id,
            "task_id": task.get("task_id"),
            "task": task,
            "status": effective_status,
            "task_graph_execution": task_graph_execution,
            "critic_plan": critic_plan,
            "receipts": receipts,
            "approval_trace": approval_trace,
            "tokens_total": total_tokens,
            "quality": quality,
            "llm_interactions": llm_interactions,
            "approval": {"required": approval_required, "approved": approval_approved},
        }
    )
    return output


def compute_message_trace_completeness(
    *,
    result: dict[str, Any],
    command_count: int,
    receipt_count: int,
    approval_count: int,
) -> float:
    checks: list[float] = []
    checks.append(1.0 if isinstance(result.get("final_output"), dict) and result.get("final_output") else 0.0)
    if command_count > 0:
        checks.append(1.0 if receipt_count >= command_count else 0.0)
    if approval_count > 0:
        checks.append(
            1.0
            if approval_count == len([item for item in result.get("approval_trace", []) or [] if isinstance(item, dict)])
            else 0.0
        )
    if isinstance(result.get("run_trace"), dict):
        checks.append(1.0)
    return sum(checks) / len(checks) if checks else 0.0
