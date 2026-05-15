import asyncio
import sys
from unittest.mock import patch
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.contracts.task_graph import build_task_graph_from_plan_steps
from riskmonitor_multiagent.orchestration.task_graph_executor import TaskGraphExecutor
from riskmonitor_multiagent.proactive_agents import ProactiveAgentResult


def test_build_task_graph_from_plan_steps_parallelizes_delegate_branches():
    graph = build_task_graph_from_plan_steps(
        [
            {
                "kind": "delegate",
                "step_id": "s1",
                "reason": "先分析系统侧",
                "target_agent": "system_engineer",
                "instruction": "分析系统",
            },
            {
                "kind": "delegate",
                "step_id": "s2",
                "reason": "再分析业务侧",
                "target_agent": "risk_analyst",
                "instruction": "分析业务",
            },
            {
                "kind": "finalize",
                "step_id": "s3",
                "reason": "最后汇总",
                "instruction": "输出结论",
            },
        ]
    )

    edges = graph.get("edges") or []
    refs = {(edge.get("from_step_id"), edge.get("to_step_id")) for edge in edges}
    assert ("s1", "s3") in refs
    assert ("s2", "s3") in refs
    assert ("s1", "s2") not in refs


def test_task_graph_executor_runs_delegate_and_finalize():
    async def _fake_engineer(*, task, context=None):
        return ProactiveAgentResult(
            ok=True,
            output={
                "summary": "系统侧未发现明显异常",
                "evidence": {"fields": ["task.payload.content"]},
            },
        )

    async def _fake_analyst(*, task, context=None):
        return ProactiveAgentResult(
            ok=True,
            output={
                "report": "业务侧影响可控",
                "evidence": {"fields": ["task.payload.content"]},
            },
        )

    executor = TaskGraphExecutor(
        delegate_handlers={
            "system_engineer": _fake_engineer,
            "risk_analyst": _fake_analyst,
        }
    )

    graph = build_task_graph_from_plan_steps(
        [
            {
                "kind": "delegate",
                "step_id": "s1",
                "reason": "先分析系统侧",
                "target_agent": "system_engineer",
                "instruction": "分析系统",
            },
            {
                "kind": "delegate",
                "step_id": "s2",
                "reason": "再分析业务侧",
                "target_agent": "risk_analyst",
                "instruction": "分析业务",
            },
            {
                "kind": "finalize",
                "step_id": "s3",
                "reason": "最后汇总",
                "instruction": "输出结论",
            },
        ]
    )

    result = asyncio.run(
        executor.execute(
            task={"task_id": "tg-1", "payload": {"content": "分析异常并输出结论"}},
            task_graph=graph,
        )
    )

    assert result.get("status") == "completed"
    final_output = result.get("final_output") or {}
    summary = final_output.get("summary")
    assert isinstance(summary, str) and "系统侧未发现明显异常" in summary
    assert "业务侧影响可控" in summary

    execution = result.get("task_graph_execution") or {}
    completed_steps = execution.get("completed_steps") or []
    assert completed_steps == ["s1", "s2", "s3"]
    trace = execution.get("trace") or []
    finalize_trace = next(item for item in trace if item.get("step_id") == "s3")
    assert set(finalize_trace.get("input_sources") or []) == {"s1", "s2"}


def test_task_graph_executor_records_parallel_timeline_for_delegate_branches():
    async def _fake_engineer(*, task, context=None):
        await asyncio.sleep(0.03)
        return ProactiveAgentResult(
            ok=True,
            output={"summary": "系统侧完成"},
        )

    async def _fake_analyst(*, task, context=None):
        await asyncio.sleep(0.03)
        return ProactiveAgentResult(
            ok=True,
            output={"report": "业务侧完成"},
        )

    executor = TaskGraphExecutor(
        delegate_handlers={
            "system_engineer": _fake_engineer,
            "risk_analyst": _fake_analyst,
        }
    )

    graph = build_task_graph_from_plan_steps(
        [
            {
                "kind": "delegate",
                "step_id": "s1",
                "reason": "系统侧并行分析",
                "target_agent": "system_engineer",
            },
            {
                "kind": "delegate",
                "step_id": "s2",
                "reason": "业务侧并行分析",
                "target_agent": "risk_analyst",
            },
            {
                "kind": "finalize",
                "step_id": "s3",
                "reason": "并行后汇总",
            },
        ]
    )

    result = asyncio.run(
        executor.execute(
            task={"task_id": "tg-parallel-1", "payload": {"content": "验证并行时间线"}},
            task_graph=graph,
        )
    )

    assert result.get("status") == "completed"
    trace = (result.get("task_graph_execution") or {}).get("trace") or []
    step_trace = {item.get("step_id"): item for item in trace}
    s1 = step_trace["s1"]
    s2 = step_trace["s2"]
    assert s1.get("started_at_ms") is not None
    assert s1.get("finished_at_ms") is not None
    assert s2.get("started_at_ms") is not None
    assert s2.get("finished_at_ms") is not None
    assert s1["started_at_ms"] <= s2["finished_at_ms"]
    assert s2["started_at_ms"] <= s1["finished_at_ms"]


def test_task_graph_executor_accepts_delegate_target_aliases():
    async def _fake_analyst(*, task, context=None):
        del task, context
        return ProactiveAgentResult(
            ok=True,
            output={"report": "别名角色已正确路由到风险分析"},
        )

    executor = TaskGraphExecutor(
        delegate_handlers={
            "risk_analyst": _fake_analyst,
        }
    )
    graph = build_task_graph_from_plan_steps(
        [
            {
                "kind": "delegate",
                "step_id": "s1",
                "reason": "先读取历史经验",
                "target_agent": "memory_agent",
            },
            {
                "kind": "delegate",
                "step_id": "s2",
                "reason": "再做业务分析",
                "target_agent": "analysis_agent",
            },
            {
                "kind": "finalize",
                "step_id": "s3",
                "reason": "最后汇总",
            },
        ]
    )

    result = asyncio.run(
        executor.execute(
            task={"task_id": "tg-alias-1", "payload": {"content": "验证 delegate 角色别名"}},
            task_graph=graph,
        )
    )

    assert result.get("status") == "completed"
    summary = (result.get("final_output") or {}).get("summary", "")
    assert "别名角色已正确路由到风险分析" in summary
    trace = ((result.get("task_graph_execution") or {}).get("trace") or [])
    delegate_steps = [item for item in trace if item.get("kind") == "delegate"]
    assert [item.get("target_agent") for item in delegate_steps] == ["risk_analyst", "risk_analyst"]


def test_task_graph_executor_runs_tool_call_via_tool_executor_and_emits_receipt():
    executor = TaskGraphExecutor(delegate_handlers={})
    graph = {
        "schema_version": "task_graph.v1",
        "nodes": [
            {
                "step_id": "s1",
                "kind": "tool_call",
                "reason": "先采集系统指标",
                "status": "pending",
                "tool_name": "collect_metrics",
                "target_agent": "system_engineer",
                "params": {},
                "evidence": {"fields": ["task.payload.content"]},
            },
            {
                "step_id": "s2",
                "parent_id": "s1",
                "kind": "finalize",
                "reason": "汇总工具结果",
                "status": "pending",
                "evidence": {"fields": ["task.payload.content"]},
            },
        ],
        "edges": [
            {"from_step_id": "s1", "to_step_id": "s2", "condition": "always"},
        ],
    }

    fake_receipt = {
        "schema_version": "agent_receipt.v1",
        "run_id": "tg-tool-1",
        "command_id": "cmd-tool-1",
        "target_agent": "system_engineer",
        "tool_name": "collect_metrics",
        "inputs": {},
        "outputs": {"action": "collect_metrics", "result": {"cpu": 0.7}},
        "status": "completed",
        "ok": True,
        "latency_ms": 8.5,
        "evidence": {"action": "collect_metrics"},
        "artifacts": [{"kind": "tool_result", "action": "collect_metrics"}],
        "error": None,
        "output": {"action": "collect_metrics", "result": {"cpu": 0.7}},
        "side_effect": False,
        "approval_state": "not_required",
        "approval_trace": {
            "required": False,
            "current_state": "not_required",
            "history": [{"state": "not_required", "ts_ms": 1, "reason": "read_only_tool"}],
        },
        "failure_classification": None,
        "retry_count": 0,
        "retry_budget": 0,
        "timeout_ms": 1000,
    }

    with patch(
        "riskmonitor_multiagent.orchestration.task_graph_executor.execute_agent_command",
        return_value=fake_receipt,
    ):
        result = asyncio.run(
            executor.execute(
                task={"task_id": "tg-tool-1", "payload": {"content": "采集系统指标并汇总"}},
                task_graph=graph,
            )
        )

    assert result.get("status") == "completed"
    receipts = result.get("receipts") or []
    assert len(receipts) == 1
    assert receipts[0].get("command_id") == "cmd-tool-1"
    assert receipts[0].get("tool_name") == "collect_metrics"
    final_output = result.get("final_output") or {}
    assert "cmd-tool-1" in (final_output.get("receipt_command_ids") or [])
    assert "tool collect_metrics completed cmd:cmd-tool-1" in final_output.get("summary", "")


def test_task_graph_executor_preserves_blocked_status_for_approval():
    executor = TaskGraphExecutor(delegate_handlers={})
    graph = {
        "schema_version": "task_graph.v1",
        "nodes": [
            {
                "step_id": "s1",
                "kind": "tool_call",
                "reason": "等待审批后执行写操作",
                "status": "pending",
                "tool_name": "submit_alerts",
                "target_agent": "risk_analyst",
                "params": {},
                "evidence": {"fields": ["task.payload.content"]},
            },
            {
                "step_id": "s2",
                "parent_id": "s1",
                "kind": "finalize",
                "reason": "汇总结果",
                "status": "pending",
                "evidence": {"fields": ["task.payload.content"]},
            },
        ],
        "edges": [{"from_step_id": "s1", "to_step_id": "s2", "condition": "always"}],
    }
    blocked_receipt = {
        "schema_version": "agent_receipt.v1",
        "run_id": "tg-blocked-1",
        "command_id": "cmd-blocked-1",
        "target_agent": "risk_analyst",
        "tool_name": "submit_alerts",
        "inputs": {},
        "outputs": None,
        "status": "blocked",
        "ok": False,
        "latency_ms": 3.0,
        "evidence": {"reason": "approval_required"},
        "artifacts": [],
        "error": "approval_required",
        "output": None,
        "side_effect": True,
        "approval_state": "pending",
        "approval_trace": {"required": True, "current_state": "pending", "history": []},
        "failure_classification": "permission",
        "retry_count": 0,
        "retry_budget": 0,
        "timeout_ms": 1000,
    }

    with patch(
        "riskmonitor_multiagent.orchestration.task_graph_executor.execute_agent_command",
        return_value=blocked_receipt,
    ):
        result = asyncio.run(
            executor.execute(
                task={"task_id": "tg-blocked-1", "payload": {"content": "写入告警"}},
                task_graph=graph,
            )
        )

    execution = result.get("task_graph_execution") or {}
    assert result.get("status") == "blocked"
    assert execution.get("status") == "blocked"
    assert execution.get("blocked_step_id") == "s1"
    assert execution.get("failed_step_id") is None
    assert (result.get("receipts") or [])[0].get("approval_state") == "pending"


def test_task_graph_executor_supports_step_level_approval_and_resume_without_rerunning_upstream():
    calls = {"engineer": 0, "analyst": 0}

    async def _fake_engineer(*, task, context=None):
        calls["engineer"] += 1
        return ProactiveAgentResult(
            ok=True,
            output={"summary": "系统侧已完成"},
        )

    async def _fake_analyst(*, task, context=None):
        calls["analyst"] += 1
        return ProactiveAgentResult(
            ok=True,
            output={"report": "业务侧审批后执行完成"},
        )

    graph = {
        "schema_version": "task_graph.v1",
        "nodes": [
            {"step_id": "s1", "kind": "delegate", "reason": "先做系统分析", "status": "pending", "target_agent": "system_engineer"},
            {
                "step_id": "s2",
                "parent_id": "s1",
                "kind": "delegate",
                "reason": "高风险步骤需要审批",
                "status": "pending",
                "target_agent": "risk_analyst",
                "approval": {
                    "required": True,
                    "reason": "需要人工确认业务影响范围",
                    "risk_level": "HIGH",
                    "impact_scope": ["desk:eq"],
                    "recommended_action": "review_and_resume_step",
                },
            },
            {"step_id": "s3", "parent_id": "s2", "kind": "finalize", "reason": "汇总"},
        ],
        "edges": [
            {"from_step_id": "s1", "to_step_id": "s2", "condition": "always"},
            {"from_step_id": "s2", "to_step_id": "s3", "condition": "always"},
        ],
    }

    first = asyncio.run(
        TaskGraphExecutor(
            delegate_handlers={
                "system_engineer": _fake_engineer,
                "risk_analyst": _fake_analyst,
            }
        ).execute(
            task={"task_id": "tg-step-approval", "payload": {"content": "需要审批后再继续"}},
            task_graph=graph,
        )
    )

    first_exec = first.get("task_graph_execution") or {}
    first_record = (first.get("approval_records") or [])[0]
    assert first.get("status") == "blocked"
    assert first_exec.get("blocked_step_id") == "s2"
    assert first_record.get("level") == "step"
    assert first_record.get("state") == "pending"
    assert calls["engineer"] == 1
    assert calls["analyst"] == 0

    resumed_graph = first.get("task_graph") or {}
    for node in resumed_graph.get("nodes", []):
        if node.get("step_id") == "s2":
            node["approval"] = {
                "required": True,
                "state": "approved",
                "actor": "reviewer",
                "note": "影响范围已确认",
                "reason": "需要人工确认业务影响范围",
                "risk_level": "HIGH",
                "impact_scope": ["desk:eq"],
                "recommended_action": "review_and_resume_step",
            }

    second = asyncio.run(
        TaskGraphExecutor(
            delegate_handlers={
                "system_engineer": _fake_engineer,
                "risk_analyst": _fake_analyst,
            }
        ).execute(
            task={"task_id": "tg-step-approval", "payload": {"content": "需要审批后再继续"}},
            task_graph=resumed_graph,
            execution_state=first_exec,
            resume_from_step_id="s2",
        )
    )

    second_exec = second.get("task_graph_execution") or {}
    assert second.get("status") == "completed"
    assert second_exec.get("resume_history")[0].get("resume_from_step_id") == "s2"
    assert calls["engineer"] == 1
    assert calls["analyst"] == 1
    assert "业务侧审批后执行完成" in (second.get("final_output") or {}).get("summary", "")


def test_task_graph_executor_supports_replan_marker_node():
    async def _fake_engineer(*, task, context=None):
        return ProactiveAgentResult(
            ok=True,
            output={"summary": "重规划后的系统分析完成"},
        )

    executor = TaskGraphExecutor(
        delegate_handlers={
            "system_engineer": _fake_engineer,
        }
    )

    result = asyncio.run(
        executor.execute(
            task={"task_id": "tg-2", "payload": {"content": "需要重规划"}},
            task_graph={
                "schema_version": "task_graph.v1",
                "nodes": [
                    {"step_id": "rp1", "kind": "replan", "reason": "critic rejected", "status": "pending", "evidence": {"fields": ["critic_plan.issues"]}},
                    {"step_id": "rp1_s1", "parent_id": "rp1", "kind": "delegate", "reason": "重规划后分析", "status": "pending", "target_agent": "system_engineer", "evidence": {"fields": ["task.payload.content"]}},
                    {"step_id": "rp1_s2", "parent_id": "rp1_s1", "kind": "finalize", "reason": "重规划后汇总", "status": "pending", "evidence": {"fields": ["task.payload.content"]}},
                ],
                "edges": [
                    {"from_step_id": "rp1", "to_step_id": "rp1_s1", "condition": "always"},
                    {"from_step_id": "rp1_s1", "to_step_id": "rp1_s2", "condition": "always"},
                ],
            },
        )
    )

    assert result.get("status") == "completed"
    completed_steps = (result.get("task_graph_execution") or {}).get("completed_steps") or []
    assert completed_steps == ["rp1", "rp1_s1", "rp1_s2"]
    assert "重规划后的系统分析完成" in (result.get("final_output") or {}).get("summary", "")


def test_task_graph_executor_retries_timeout_and_resumes_from_failed_step():
    calls = {"engineer": 0, "analyst": 0}

    async def _fake_engineer(*, task, context=None):
        calls["engineer"] += 1
        return ProactiveAgentResult(
            ok=True,
            output={"summary": "系统侧已经完成"},
        )

    async def _fake_analyst_slow(*, task, context=None):
        calls["analyst"] += 1
        await asyncio.sleep(0.03)
        return ProactiveAgentResult(
            ok=True,
            output={"report": "业务侧分析完成"},
        )

    executor = TaskGraphExecutor(
        delegate_handlers={
            "system_engineer": _fake_engineer,
            "risk_analyst": _fake_analyst_slow,
        }
    )
    graph = {
        "schema_version": "task_graph.v1",
        "nodes": [
            {"step_id": "s1", "kind": "delegate", "reason": "系统分析", "status": "pending", "target_agent": "system_engineer", "evidence": {"fields": ["task.payload.content"]}},
            {"step_id": "s2", "parent_id": "s1", "kind": "delegate", "reason": "业务分析", "status": "pending", "target_agent": "risk_analyst", "timeout_ms": 5, "retry_budget": 1, "evidence": {"fields": ["task.payload.content"]}},
            {"step_id": "s3", "parent_id": "s2", "kind": "finalize", "reason": "汇总", "status": "pending", "evidence": {"fields": ["task.payload.content"]}},
        ],
        "edges": [
            {"from_step_id": "s1", "to_step_id": "s2", "condition": "always"},
            {"from_step_id": "s2", "to_step_id": "s3", "condition": "always"},
        ],
    }

    first = asyncio.run(
        executor.execute(
            task={"task_id": "tg-retry-1", "payload": {"content": "测试 timeout 重试"}},
            task_graph=graph,
        )
    )
    first_exec = first.get("task_graph_execution") or {}
    assert first.get("status") == "failed"
    assert first_exec.get("failed_step_id") == "s2"
    retry_records = first_exec.get("retry_records") or []
    assert len(retry_records) == 2
    assert all(record.get("failure_classification") == "timeout" for record in retry_records)
    assert calls["engineer"] == 1
    assert calls["analyst"] == 2

    async def _fake_analyst_fast(*, task, context=None):
        calls["analyst"] += 1
        return ProactiveAgentResult(
            ok=True,
            output={"report": "业务侧恢复后分析完成"},
        )

    resumed_executor = TaskGraphExecutor(
        delegate_handlers={
            "system_engineer": _fake_engineer,
            "risk_analyst": _fake_analyst_fast,
        }
    )
    second = asyncio.run(
        resumed_executor.execute(
            task={"task_id": "tg-retry-1", "payload": {"content": "测试 timeout 重试"}},
            task_graph=first.get("task_graph") or {},
            execution_state=first_exec,
            resume_from_step_id="s2",
        )
    )
    second_exec = second.get("task_graph_execution") or {}
    assert second.get("status") == "completed"
    assert calls["engineer"] == 1
    assert calls["analyst"] == 3
    assert second_exec.get("resume_history")[0].get("resume_from_step_id") == "s2"
    assert "业务侧恢复后分析完成" in (second.get("final_output") or {}).get("summary", "")


def test_task_graph_executor_resumes_after_validation_fix_without_rerunning_upstream():
    calls = {"engineer": 0, "analyst": 0}

    async def _fake_engineer(*, task, context=None):
        calls["engineer"] += 1
        return ProactiveAgentResult(
            ok=True,
            output={"summary": "系统侧稳定"},
        )

    async def _fake_analyst_invalid(*, task, context=None):
        calls["analyst"] += 1
        raise ValueError("invalid param: severity")

    graph = {
        "schema_version": "task_graph.v1",
        "nodes": [
            {"step_id": "s1", "kind": "delegate", "reason": "系统分析", "status": "pending", "target_agent": "system_engineer", "evidence": {"fields": ["task.payload.content"]}},
            {"step_id": "s2", "parent_id": "s1", "kind": "delegate", "reason": "业务分析", "status": "pending", "target_agent": "risk_analyst", "retry_budget": 2, "params": {"severity": ""}, "evidence": {"fields": ["task.payload.content"]}},
            {"step_id": "s3", "parent_id": "s2", "kind": "finalize", "reason": "汇总", "status": "pending", "evidence": {"fields": ["task.payload.content"]}},
        ],
        "edges": [
            {"from_step_id": "s1", "to_step_id": "s2", "condition": "always"},
            {"from_step_id": "s2", "to_step_id": "s3", "condition": "always"},
        ],
    }

    first = asyncio.run(
        TaskGraphExecutor(
            delegate_handlers={
                "system_engineer": _fake_engineer,
                "risk_analyst": _fake_analyst_invalid,
            }
        ).execute(
            task={"task_id": "tg-validate-1", "payload": {"content": "修复参数后恢复"}},
            task_graph=graph,
        )
    )
    first_exec = first.get("task_graph_execution") or {}
    assert first.get("status") == "failed"
    assert first_exec.get("failed_step_id") == "s2"
    retry_records = first_exec.get("retry_records") or []
    assert len(retry_records) == 1
    assert retry_records[0].get("failure_classification") == "validation"
    assert calls["engineer"] == 1
    assert calls["analyst"] == 1

    fixed_graph = first.get("task_graph") or {}
    for node in fixed_graph.get("nodes", []):
        if node.get("step_id") == "s2":
            node["params"] = {"severity": "HIGH"}

    async def _fake_analyst_fixed(*, task, context=None):
        calls["analyst"] += 1
        return ProactiveAgentResult(
            ok=True,
            output={"report": "参数修复后业务分析完成"},
        )

    second = asyncio.run(
        TaskGraphExecutor(
            delegate_handlers={
                "system_engineer": _fake_engineer,
                "risk_analyst": _fake_analyst_fixed,
            }
        ).execute(
            task={"task_id": "tg-validate-1", "payload": {"content": "修复参数后恢复"}},
            task_graph=fixed_graph,
            execution_state=first_exec,
            resume_from_step_id="s2",
        )
    )
    assert second.get("status") == "completed"
    assert calls["engineer"] == 1
    assert calls["analyst"] == 2
    assert "参数修复后业务分析完成" in (second.get("final_output") or {}).get("summary", "")
