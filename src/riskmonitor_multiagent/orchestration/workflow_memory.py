"""
工作流记忆持久化模块.

从 proactive_workflow.py 提取的异步函数，负责记忆写入.
"""

from __future__ import annotations

from typing import Any


async def persist_plan_memory(
    *,
    memory_store: Any,
    run_id: str,
    task: dict[str, Any],
    orchestrator_output: dict[str, Any],
) -> None:
    plan_steps = orchestrator_output.get("plan_steps") if isinstance(orchestrator_output.get("plan_steps"), list) else []
    plan_text = " ; ".join(
        str(step.get("reason") or step.get("instruction") or step.get("kind") or "")
        for step in plan_steps
        if isinstance(step, dict)
    )
    await memory_store.append(
        {
            "agent_id": "orchestrator",
            "scope": "shared",
            "kind": "plan",
            "memory_type": "episodic",
            "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
            "run_id": run_id,
            "source": "orchestrator_plan",
            "created_by": "orchestrator",
            "trace_ref": {"run_id": run_id},
            "content": {
                "text": plan_text or "plan generated",
                "plan_steps": plan_steps,
                "task_id": task.get("task_id"),
            },
            "tags": ["plan"],
        }
    )


async def persist_intent_memory(
    *,
    memory_store: Any,
    run_id: str,
    task: dict[str, Any],
    intent_output: dict[str, Any],
) -> None:
    disambiguation = intent_output.get("disambiguation")
    intents = intent_output.get("intents")
    if not isinstance(disambiguation, dict) or disambiguation.get("has_multiple") is not True:
        return
    if not isinstance(intents, list):
        intents = []
    await memory_store.append(
        {
            "agent_id": "intent",
            "scope": "shared",
            "kind": "intent_disambiguation",
            "memory_type": "episodic",
            "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
            "run_id": run_id,
            "source": "intent_agent",
            "created_by": "intent",
            "trace_ref": {"run_id": run_id},
            "content": {
                "text": str(disambiguation.get("explanation") or "multi intent detected"),
                "intents": intents,
                "primary_intent_type": intent_output.get("primary_intent_type"),
            },
            "tags": ["intent", "disambiguation"],
        }
    )
