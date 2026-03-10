"""Orchestration module using LangGraph."""

# 延迟导入以避免循环导入
def run_orchestrator_workflow(*, task):
    from riskmonitor_multiagent.orchestration.orchestrator_workflow import (
        run_orchestrator_workflow as _run,
    )
    return _run(task=task)


__all__ = ["run_orchestrator_workflow"]
