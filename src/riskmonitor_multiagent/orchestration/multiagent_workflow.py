"""统一多 Agent 工作流门面.

该模块提供与文档口径一致的统一入口, 实际执行仍委托给 proactive workflow.
"""

from __future__ import annotations

from typing import Any


async def run_user_task(*, task: dict[str, Any]) -> dict[str, Any]:
    """执行用户任务入口."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import run_proactive_workflow

    return await run_proactive_workflow(task=task)


async def start_from_event(
    *,
    event: dict[str, Any],
    candidate_agents: list[str] | None = None,
) -> dict[str, Any]:
    """执行系统事件入口."""
    from riskmonitor_multiagent.orchestration.proactive_workflow import get_proactive_workflow

    workflow = get_proactive_workflow()
    return await workflow.start_from_event(
        event=event,
        candidate_agents=candidate_agents,
    )


__all__ = ["run_user_task", "start_from_event"]
