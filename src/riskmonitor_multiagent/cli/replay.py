"""run replay CLI helper."""

from __future__ import annotations

from riskmonitor_multiagent.observability.run_trace import get_run_trace_store


def replay_run(run_id: str, *, output_format: str = "text") -> str:
    """按 run_id 渲染统一时间线.

    优先从内存读取 不存在时回退到磁盘快照.
    """
    store = get_run_trace_store()
    if output_format == "json":
        return store.render_replay_json(run_id)
    return store.render_replay(run_id)


__all__ = ["replay_run"]
