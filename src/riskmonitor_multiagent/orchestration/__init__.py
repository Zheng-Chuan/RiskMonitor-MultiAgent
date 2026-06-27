"""Orchestration module using proactive workflow."""

# 延迟导入以避免循环导入
def run_proactive_workflow(*, task):
    from riskmonitor_multiagent.orchestration.proactive_workflow import (
        run_proactive_workflow as _run,
    )
    return _run(task=task)


def run_user_task(*, task):
    from riskmonitor_multiagent.orchestration.multiagent_workflow import (
        run_user_task as _run_user_task,
    )

    return _run_user_task(task=task)


def start_from_event(*, event, candidate_agents=None):
    from riskmonitor_multiagent.orchestration.multiagent_workflow import (
        start_from_event as _start_from_event,
    )

    return _start_from_event(event=event, candidate_agents=candidate_agents)


__all__ = ["run_proactive_workflow", "run_user_task", "start_from_event"]
