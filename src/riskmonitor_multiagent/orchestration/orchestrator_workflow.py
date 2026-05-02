"""Orchestration module using Proactive Multi-Agent System.

此文件使用具备 BDI + ReAct + 后台监控的主动 Agent 系统.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

from riskmonitor_multiagent.orchestration.proactive_workflow import (
    get_proactive_workflow,
    reset_proactive_workflow,
)
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms
from riskmonitor_multiagent.utils.ids import new_run_id


async def run_orchestrator_workflow(*, task: dict[str, Any]) -> dict[str, Any]:
    """运行统一主动工作流并补充最小观测字段."""
    inc_counter("orchestrator_runs_total")
    start_time = time.time()

    run_id = new_run_id("proactive")
    logger.info(f"Starting proactive multi-agent orchestration for task: {task.get('task_id') or run_id}")

    try:
        reset_proactive_workflow()
        
        workflow = get_proactive_workflow()
        
        result = await workflow.run(task)
        
        out = _build_workflow_output(
            task=task,
            run_id=run_id,
            result=result,
            start_time=start_time,
        )

        latency_ms = (time.time() - start_time) * 1000
        observe_ms("orchestrator_latency_ms", latency_ms)
        inc_counter("orchestrator_runs_success")

        return out

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        observe_ms("orchestrator_latency_ms", latency_ms)
        inc_counter("orchestrator_runs_error")
        logger.exception(f"Proactive orchestration failed for task {task.get('task_id') or run_id}")
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "result": {
                "run_id": run_id,
                "task_id": task.get("task_id"),
                "errors": [str(e)],
                "tokens_total": 0,
            },
        }


def _build_workflow_output(
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
        "message_trace_completeness": _compute_message_trace_completeness(
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


def _compute_message_trace_completeness(
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
        checks.append(1.0 if approval_count == len([item for item in result.get("approval_trace", []) or [] if isinstance(item, dict)]) else 0.0)
    if isinstance(result.get("run_trace"), dict):
        checks.append(1.0)
    return sum(checks) / len(checks) if checks else 0.0


__all__ = ["run_orchestrator_workflow"]
