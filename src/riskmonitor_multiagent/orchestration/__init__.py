"""Orchestration module using proactive workflow."""

# 延迟导入以避免循环导入
def run_proactive_workflow(*, task):
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        run_proactive_workflow as _run,
    )
    return _run(task=task)


__all__ = ["run_proactive_workflow"]
