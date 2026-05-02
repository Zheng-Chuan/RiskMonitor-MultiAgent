import asyncio
import sys
from unittest.mock import patch
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.proactive_agents import ProactiveAgentResult
from riskmonitor_multiagent.orchestration.proactive_workflow import ProactiveMultiAgentWorkflow


def test_proactive_workflow_replans_when_critic_rejects():
    workflow = ProactiveMultiAgentWorkflow()
    calls = {"orchestrate": 0}

    async def _noop():
        return None

    async def _fake_intent(*, task):
        return ProactiveAgentResult(
            ok=True,
            output={"primary_intent_type": "analyze_risk"},
        )

    async def _fake_orchestrate(*, task, context=None):
        calls["orchestrate"] += 1
        phase = context.get("phase") if isinstance(context, dict) else "plan"
        if phase == "replan":
            return ProactiveAgentResult(
                ok=True,
                output={
                    "plan_steps": [
                        {
                            "kind": "delegate",
                            "step_id": "s1",
                            "reason": "按 critic 建议改走业务分析",
                            "target_agent": "risk_analyst",
                            "instruction": "分析业务影响",
                        },
                        {
                            "kind": "finalize",
                            "step_id": "s2",
                            "reason": "重规划后汇总",
                            "instruction": "输出结论",
                        },
                    ],
                },
            )
        return ProactiveAgentResult(
            ok=True,
            output={
                "plan_steps": [
                    {
                        "kind": "delegate",
                        "step_id": "s1",
                        "reason": "先做系统分析",
                        "target_agent": "system_engineer",
                        "instruction": "分析系统影响",
                    },
                    {
                        "kind": "finalize",
                        "step_id": "s2",
                        "reason": "先给初版汇总",
                        "instruction": "输出初版结论",
                    },
                ],
            },
        )

    async def _fake_critic(*, task, orchestrator):
        return ProactiveAgentResult(
            ok=True,
            output={
                "ok": False,
                "issues": ["初版计划缺少业务影响分析"],
                "suggested_fixes": ["补一条 risk_analyst 分支"],
            },
        )

    async def _fake_engineer(*, task, context=None):
        return ProactiveAgentResult(
            ok=True,
            output={"summary": "系统侧初步判断正常"},
        )

    async def _fake_analyst(*, task, context=None):
        return ProactiveAgentResult(
            ok=True,
            output={"report": "业务侧确认存在中等风险敞口"},
        )

    workflow.start_agents = _noop
    workflow._intent_agent.recognize = _fake_intent
    workflow._orchestrator_agent.orchestrate = _fake_orchestrate
    workflow._critic_agent.review = _fake_critic
    workflow._engineer_agent.analyze_task = _fake_engineer
    workflow._analyst_agent.analyze_task = _fake_analyst

    result = asyncio.run(
        workflow.run(
            {
                "task_id": "replan-1",
                "source": "human",
                "payload": {"content": "分析风险并给出结论"},
            }
        )
    )

    assert result.get("status") == "completed"
    assert calls["orchestrate"] == 2
    replan = result.get("replan") or {}
    assert replan.get("trigger") == "critic_rejected"
    assert "业务影响分析" in replan.get("reason", "")

    task_graph = result.get("task_graph") or {}
    step_ids = {node.get("step_id") for node in task_graph.get("nodes", [])}
    assert "rp1" in step_ids
    assert "rp1_s1" in step_ids
    assert "rp1_s2" in step_ids

    final_output = result.get("final_output") or {}
    summary = final_output.get("summary", "")
    assert "业务侧确认存在中等风险敞口" in summary

    execution = result.get("task_graph_execution") or {}
    completed_steps = execution.get("completed_steps") or []
    assert "rp1" in completed_steps
    assert "rp1_s1" in completed_steps
    assert "rp1_s2" in completed_steps


def test_proactive_workflow_can_resume_from_failed_step():
    workflow = ProactiveMultiAgentWorkflow()
    calls = {"engineer": 0, "analyst": 0}

    async def _noop():
        return None

    async def _fake_intent(*, task):
        return ProactiveAgentResult(
            ok=True,
            output={"primary_intent_type": "resume_analysis"},
        )

    async def _fake_engineer(*, task, context=None):
        calls["engineer"] += 1
        return ProactiveAgentResult(
            ok=True,
            output={"summary": "系统侧已完成"},
        )

    async def _fake_analyst_bad(*, task, context=None):
        calls["analyst"] += 1
        raise ValueError("invalid param: severity")

    workflow.start_agents = _noop
    workflow._intent_agent.recognize = _fake_intent
    workflow._engineer_agent.analyze_task = _fake_engineer
    workflow._analyst_agent.analyze_task = _fake_analyst_bad

    first = asyncio.run(
        workflow.run(
            {
                "task_id": "resume-1",
                "source": "human",
                "payload": {"content": "先失败再恢复"},
                "resume": {
                    "task_graph": {
                        "schema_version": "task_graph.v1",
                        "nodes": [
                            {"step_id": "s1", "kind": "delegate", "reason": "系统分析", "status": "pending", "target_agent": "system_engineer", "evidence": {"fields": ["task.payload.content"]}},
                            {"step_id": "s2", "parent_id": "s1", "kind": "delegate", "reason": "业务分析", "status": "pending", "target_agent": "risk_analyst", "params": {"severity": ""}, "evidence": {"fields": ["task.payload.content"]}},
                            {"step_id": "s3", "parent_id": "s2", "kind": "finalize", "reason": "汇总", "status": "pending", "evidence": {"fields": ["task.payload.content"]}},
                        ],
                        "edges": [
                            {"from_step_id": "s1", "to_step_id": "s2", "condition": "always"},
                            {"from_step_id": "s2", "to_step_id": "s3", "condition": "always"},
                        ],
                    },
                    "execution_state": {},
                    "resume_from_step_id": "s1",
                },
            }
        )
    )

    first_exec = first.get("task_graph_execution") or {}
    assert first.get("status") == "failed"
    assert first_exec.get("status") == "failed"
    assert first_exec.get("failed_step_id") == "s2"
    assert calls["engineer"] == 1
    assert calls["analyst"] == 1

    fixed_task_graph = first.get("task_graph") or {}
    for node in fixed_task_graph.get("nodes", []):
        if node.get("step_id") == "s2":
            node["params"] = {"severity": "HIGH"}

    async def _fake_analyst_fixed(*, task, context=None):
        calls["analyst"] += 1
        return ProactiveAgentResult(
            ok=True,
            output={"report": "恢复后业务分析完成"},
        )

    workflow._analyst_agent.analyze_task = _fake_analyst_fixed
    second = asyncio.run(
        workflow.run(
            {
                "task_id": "resume-1",
                "source": "human",
                "payload": {"content": "先失败再恢复"},
                "resume": {
                    "task_graph": fixed_task_graph,
                    "execution_state": first_exec,
                    "resume_from_step_id": "s2",
                },
            }
        )
    )

    second_exec = second.get("task_graph_execution") or {}
    assert second.get("status") == "completed"
    assert second_exec.get("status") == "completed"
    assert calls["engineer"] == 1
    assert calls["analyst"] == 2
    assert (second.get("replan") or {}).get("trigger") == "manual_resume"
    assert second_exec.get("resume_history")[0].get("resume_from_step_id") == "s2"
    assert "恢复后业务分析完成" in (second.get("final_output") or {}).get("summary", "")


def test_proactive_workflow_runs_parallel_delegate_branches_and_finalize():
    workflow = ProactiveMultiAgentWorkflow()

    async def _noop():
        return None

    async def _fake_intent(*, task):
        return ProactiveAgentResult(
            ok=True,
            output={"primary_intent_type": "parallel_analysis"},
        )

    async def _fake_orchestrate(*, task, context=None):
        return ProactiveAgentResult(
            ok=True,
            output={
                "plan_steps": [
                    {
                        "kind": "delegate",
                        "step_id": "s1",
                        "reason": "并行做系统侧分析",
                        "target_agent": "system_engineer",
                        "instruction": "分析系统影响",
                    },
                    {
                        "kind": "delegate",
                        "step_id": "s2",
                        "reason": "并行做业务侧分析",
                        "target_agent": "risk_analyst",
                        "instruction": "分析业务影响",
                    },
                    {
                        "kind": "finalize",
                        "step_id": "s3",
                        "reason": "汇总双分支结果",
                        "instruction": "输出结论",
                    },
                ],
            },
        )

    async def _fake_critic(*, task, orchestrator):
        return ProactiveAgentResult(
            ok=True,
            output={"ok": True, "issues": [], "suggested_fixes": []},
        )

    async def _fake_engineer(*, task, context=None):
        await asyncio.sleep(0.03)
        return ProactiveAgentResult(
            ok=True,
            output={"summary": "系统侧确认链路正常"},
        )

    async def _fake_analyst(*, task, context=None):
        await asyncio.sleep(0.03)
        return ProactiveAgentResult(
            ok=True,
            output={"report": "业务侧确认敞口可控"},
        )

    workflow.start_agents = _noop
    workflow._intent_agent.recognize = _fake_intent
    workflow._orchestrator_agent.orchestrate = _fake_orchestrate
    workflow._critic_agent.review = _fake_critic
    workflow._engineer_agent.analyze_task = _fake_engineer
    workflow._analyst_agent.analyze_task = _fake_analyst

    result = asyncio.run(
        workflow.run(
            {
                "task_id": "parallel-1",
                "source": "human",
                "payload": {"content": "需要系统侧和业务侧并行分析"},
            }
        )
    )

    assert result.get("status") == "completed"
    final_output = result.get("final_output") or {}
    assert "系统侧确认链路正常" in final_output.get("summary", "")
    assert "业务侧确认敞口可控" in final_output.get("summary", "")
    assert set(final_output.get("sources") or []) == {"s1", "s2"}

    trace = (result.get("task_graph_execution") or {}).get("trace") or []
    step_trace = {item.get("step_id"): item for item in trace}
    s1 = step_trace["s1"]
    s2 = step_trace["s2"]
    s3 = step_trace["s3"]
    assert s1["started_at_ms"] <= s2["finished_at_ms"]
    assert s2["started_at_ms"] <= s1["finished_at_ms"]
    assert set(s3.get("input_sources") or []) == {"s1", "s2"}


def test_proactive_workflow_surfaces_tool_receipts_from_task_graph():
    workflow = ProactiveMultiAgentWorkflow()

    async def _noop():
        return None

    async def _fake_intent(*, task):
        return ProactiveAgentResult(
            ok=True,
            output={"primary_intent_type": "tool_execution"},
        )

    async def _fake_orchestrate(*, task, context=None):
        return ProactiveAgentResult(
            ok=True,
            output={
                "plan_steps": [
                    {
                        "kind": "tool_call",
                        "step_id": "s1",
                        "reason": "采集系统指标",
                        "tool_name": "collect_metrics",
                        "target_agent": "system_engineer",
                        "params": {},
                    },
                    {
                        "kind": "finalize",
                        "step_id": "s2",
                        "reason": "汇总工具结果",
                        "instruction": "输出结论",
                    },
                ],
            },
        )

    async def _fake_critic(*, task, orchestrator):
        return ProactiveAgentResult(
            ok=True,
            output={"ok": True, "issues": [], "suggested_fixes": []},
        )

    fake_receipt = {
        "schema_version": "agent_receipt.v1",
        "run_id": "workflow-tool-1",
        "command_id": "cmd-tool-2",
        "target_agent": "system_engineer",
        "tool_name": "collect_metrics",
        "inputs": {},
        "outputs": {"action": "collect_metrics", "result": {"cpu": 0.5}},
        "status": "completed",
        "ok": True,
        "latency_ms": 5.0,
        "evidence": {"action": "collect_metrics"},
        "artifacts": [{"kind": "tool_result", "action": "collect_metrics"}],
        "error": None,
        "output": {"action": "collect_metrics", "result": {"cpu": 0.5}},
        "side_effect": False,
        "approval_state": "not_required",
    }

    workflow.start_agents = _noop
    workflow._intent_agent.recognize = _fake_intent
    workflow._orchestrator_agent.orchestrate = _fake_orchestrate
    workflow._critic_agent.review = _fake_critic

    with patch(
        "riskmonitor_multiagent.orchestration.task_graph_executor.execute_agent_command",
        return_value=fake_receipt,
    ):
        result = asyncio.run(
            workflow.run(
                {
                    "task_id": "workflow-tool-1",
                    "source": "human",
                    "payload": {"content": "采集系统指标并汇总"},
                }
            )
        )

    assert result.get("status") == "completed"
    receipts = result.get("receipts") or []
    assert len(receipts) == 1
    assert receipts[0].get("command_id") == "cmd-tool-2"
    assert "cmd-tool-2" in ((result.get("final_output") or {}).get("receipt_command_ids") or [])
