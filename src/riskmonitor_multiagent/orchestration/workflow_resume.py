"""
工作流恢复与重规划模块.

从 proactive_workflow.py 提取的纯函数，负责 resume/replan 相关逻辑.
"""

from __future__ import annotations

from typing import Any


def apply_resume_context(
    *,
    task: dict[str, Any],
    resume_request: dict[str, Any],
) -> dict[str, Any]:
    if not resume_request:
        return task
    enriched = dict(task)
    enriched["resume"] = dict(resume_request)
    enriched["resume_context"] = {
        "run_id": resume_request.get("run_id"),
        "resume_from_step_id": resume_request.get("resume_from_step_id"),
        "memory_state": list(resume_request.get("memory_state") or []),
        "run_summary": dict(resume_request.get("run_summary") or {}) if isinstance(resume_request.get("run_summary"), dict) else {},
        "approval_decision": dict(resume_request.get("approval_decision") or {}) if isinstance(resume_request.get("approval_decision"), dict) else {},
    }
    return enriched


def apply_approval_decision_to_resume_request(
    *,
    resume_request: dict[str, Any],
) -> dict[str, Any]:
    if not resume_request:
        return resume_request
    approval_decision = (
        dict(resume_request.get("approval_decision"))
        if isinstance(resume_request.get("approval_decision"), dict)
        else {}
    )
    task_graph = resume_request.get("task_graph")
    if not approval_decision or not isinstance(task_graph, dict):
        return resume_request

    execution_state = resume_request.get("execution_state") if isinstance(resume_request.get("execution_state"), dict) else {}
    target_step_id = (
        approval_decision.get("step_id")
        or resume_request.get("resume_from_step_id")
        or execution_state.get("blocked_step_id")
    )
    if not isinstance(target_step_id, str) or not target_step_id:
        return resume_request

    updated = dict(resume_request)
    cloned_graph = {
        "schema_version": task_graph.get("schema_version"),
        "nodes": [dict(node) for node in task_graph.get("nodes", []) if isinstance(node, dict)],
        "edges": [dict(edge) for edge in task_graph.get("edges", []) if isinstance(edge, dict)],
    }
    state = str(approval_decision.get("state") or "approved").strip().lower()
    for node in cloned_graph["nodes"]:
        if node.get("step_id") != target_step_id:
            continue
        if node.get("kind") == "tool_call":
            params = dict(node.get("params")) if isinstance(node.get("params"), dict) else {}
            existing = dict(params.get("approval")) if isinstance(params.get("approval"), dict) else {}
            existing.update(
                {
                    "approved": state in {"approved", "resumed"},
                    "state": state,
                    "actor": approval_decision.get("actor"),
                    "note": approval_decision.get("note"),
                    "reason": approval_decision.get("reason"),
                    "risk_level": approval_decision.get("risk_level"),
                    "impact_scope": approval_decision.get("impact_scope"),
                    "recommended_action": approval_decision.get("recommended_action"),
                }
            )
            params["approval"] = existing
            node["params"] = params
        node_approval = dict(node.get("approval")) if isinstance(node.get("approval"), dict) else {}
        if node_approval.get("required") is True:
            node_approval.update(
                {
                    "state": state,
                    "actor": approval_decision.get("actor"),
                    "note": approval_decision.get("note"),
                    "reason": approval_decision.get("reason") or node_approval.get("reason"),
                    "risk_level": approval_decision.get("risk_level") or node_approval.get("risk_level"),
                    "impact_scope": approval_decision.get("impact_scope") or node_approval.get("impact_scope"),
                    "recommended_action": approval_decision.get("recommended_action") or node_approval.get("recommended_action"),
                }
            )
            node["approval"] = node_approval
    updated["task_graph"] = cloned_graph
    updated["resume_from_step_id"] = target_step_id
    return updated


def merge_resume_memory_into_planning_memory(
    *,
    planning_memory: dict[str, Any],
    resume_request: dict[str, Any],
    private_memory_enabled: bool,
) -> dict[str, Any]:
    if not resume_request:
        return planning_memory
    merged = {
        "hits": list(planning_memory.get("hits", [])),
        "summary": dict(planning_memory.get("summary", {})),
        "shared_board": list(planning_memory.get("shared_board", [])),
        "private_memory_state": dict(planning_memory.get("private_memory_state", {})),
    }
    memory_state = resume_request.get("memory_state")
    if isinstance(memory_state, list) and memory_state:
        merged["hits"].extend([item for item in memory_state if isinstance(item, dict)])
        merged["summary"]["resume_memory_state_count"] = len(memory_state)
    shared_memory_board = resume_request.get("shared_memory_board")
    if isinstance(shared_memory_board, list) and shared_memory_board:
        merged["shared_board"] = [item for item in shared_memory_board if isinstance(item, dict)]
        merged["summary"]["resume_shared_board_count"] = len(merged["shared_board"])
    private_memory_state = resume_request.get("private_memory_state")
    if private_memory_enabled and isinstance(private_memory_state, dict) and private_memory_state:
        merged["private_memory_state"] = {
            str(agent_id): [item for item in entries if isinstance(item, dict)]
            for agent_id, entries in private_memory_state.items()
            if isinstance(entries, list)
        }
        merged["summary"]["resume_private_memory_agents"] = sorted(merged["private_memory_state"].keys())
    run_summary = resume_request.get("run_summary")
    if isinstance(run_summary, dict) and run_summary:
        merged["summary"]["resume_run_summary"] = dict(run_summary)
    return merged


def should_replan(critic_output: dict[str, Any]) -> bool:
    """判断是否需要重规划."""
    if not isinstance(critic_output, dict):
        return False
    if critic_output.get("ok") is False:
        return True
    return False


def build_replan_reason(critic_output: dict[str, Any]) -> str:
    """构造重规划原因."""
    if not isinstance(critic_output, dict):
        return "critic rejected previous plan"

    issues = critic_output.get("issues")
    if isinstance(issues, list) and issues:
        first_issue = issues[0]
        if isinstance(first_issue, str) and first_issue.strip():
            return first_issue.strip()

    fixes = critic_output.get("suggested_fixes")
    if isinstance(fixes, list) and fixes:
        first_fix = fixes[0]
        if isinstance(first_fix, str) and first_fix.strip():
            return first_fix.strip()

    return "critic rejected previous plan"


def should_runtime_replan(execution_result: dict[str, Any]) -> bool:
    if execution_result.get("status") != "failed":
        return False
    failure = extract_execution_failure(execution_result)
    classification = failure.get("failure_classification")
    return classification in {"runtime", "dependency", "timeout", "validation"}


def extract_execution_failure(execution_result: dict[str, Any]) -> dict[str, Any]:
    trace = (execution_result.get("task_graph_execution") or {}).get("trace") or []
    failed = {}
    for item in reversed(trace):
        if isinstance(item, dict) and item.get("status") == "failed":
            failed = dict(item)
            break
    failed_step_id = (execution_result.get("task_graph_execution") or {}).get("failed_step_id")
    if isinstance(failed_step_id, str) and failed_step_id:
        failed.setdefault("failed_step_id", failed_step_id)
    return failed


def build_runtime_replan_reason(execution_result: dict[str, Any]) -> str:
    failure = extract_execution_failure(execution_result)
    error = failure.get("error")
    classification = failure.get("failure_classification")
    step_id = failure.get("failed_step_id") or failure.get("step_id")
    pieces = [part for part in [str(classification or "").strip(), str(error or "").strip(), str(step_id or "").strip()] if part]
    if pieces:
        return " | ".join(pieces)
    return "execution_failed_runtime_replan"
