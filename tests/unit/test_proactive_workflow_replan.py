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


def test_proactive_workflow_runtime_replans_after_tool_failure():
    workflow = ProactiveMultiAgentWorkflow()
    calls = {"orchestrate": 0}

    async def _noop():
        return None

    async def _fake_intent(*, task):
        return ProactiveAgentResult(
            ok=True,
            output={"primary_intent_type": "runtime_replan"},
        )

    async def _fake_orchestrate(*, task, context=None):
        calls["orchestrate"] += 1
        phase = context.get("phase") if isinstance(context, dict) else "plan"
        if phase == "runtime_replan":
            failure = context.get("execution_failure") if isinstance(context, dict) else {}
            assert isinstance(failure, dict)
            assert failure.get("failure_classification") == "dependency"
            return ProactiveAgentResult(
                ok=True,
                output={
                    "plan_steps": [
                        {
                            "kind": "delegate",
                            "step_id": "r1",
                            "reason": "工具失败后改走业务分析",
                            "target_agent": "risk_analyst",
                            "instruction": "输出替代分析",
                        },
                        {
                            "kind": "finalize",
                            "step_id": "r2",
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
                        "kind": "tool_call",
                        "step_id": "s1",
                        "reason": "先调用一个不存在的工具",
                        "tool_name": "missing_tool",
                        "target_agent": "system_engineer",
                    },
                    {
                        "kind": "finalize",
                        "step_id": "s2",
                        "reason": "输出初版",
                        "instruction": "输出结论",
                    },
                ],
            },
        )

    async def _fake_critic(*, task, orchestrator, receipts=None, final_output=None, phase="plan_review"):
        return ProactiveAgentResult(
            ok=True,
            output={
                "ok": True,
                "issues": [],
                "suggested_fixes": [],
                "run_summary": {"text": f"critic_{phase}", "key_points": [], "receipt_command_ids": []},
            },
        )

    async def _fake_analyst(*, task, context=None):
        return ProactiveAgentResult(
            ok=True,
            output={"report": "重规划后业务分析完成"},
        )

    workflow.start_agents = _noop
    workflow._intent_agent.recognize = _fake_intent
    workflow._orchestrator_agent.orchestrate = _fake_orchestrate
    workflow._critic_agent.review = _fake_critic
    workflow._analyst_agent.analyze_task = _fake_analyst

    result = asyncio.run(
        workflow.run(
            {
                "task_id": "runtime-replan-1",
                "source": "human",
                "payload": {"content": "工具失败后继续完成"},
            }
        )
    )

    assert result.get("status") == "completed"
    assert calls["orchestrate"] == 2
    assert (result.get("replan") or {}).get("trigger") == "execution_failed"
    assert "重规划后业务分析完成" in (result.get("final_output") or {}).get("summary", "")


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

    async def _fake_critic(*, task, orchestrator, receipts=None, final_output=None, phase="plan_review"):
        return ProactiveAgentResult(
            ok=True,
            output={
                "ok": True,
                "issues": [],
                "suggested_fixes": [],
                "run_summary": {"text": f"critic_{phase}", "key_points": [], "receipt_command_ids": []},
            },
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

    async def _fake_critic(*, task, orchestrator, receipts=None, final_output=None, phase="plan_review"):
        return ProactiveAgentResult(
            ok=True,
            output={
                "ok": True,
                "issues": [],
                "suggested_fixes": [],
                "run_summary": {"text": f"critic_{phase}", "key_points": [], "receipt_command_ids": []},
            },
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
    assert isinstance(result.get("critic_final"), dict)
    assert "cmd-tool-2" in (((result.get("critic_final") or {}).get("evidence") or {}).get("receipt_command_ids") or [])


def test_proactive_workflow_persists_memory_and_supports_resume_from_run_id():
    class _FakeMemoryStore:
        def __init__(self) -> None:
            self.working_entries = []
            self.saved_contexts = {}
            self.persisted_runs = {}

        async def append(self, entry, **kwargs):
            del kwargs
            return dict(entry)

        async def retrieve_for_planning(self, *, task, intent=None, limit=5):
            return {
                "hits": [{"entry_id": "mem-1", "kind": "lesson", "memory_type": "procedural", "content": {"text": "先查持仓"}}],
                "summary": {"hit_count": 1, "texts": ["[procedural/lesson] 先查持仓"]},
            }

        async def record_working_memory(self, *, run_id, task, trace_entry, node=None, node_result=None, private_memory_enabled=True):
            self.working_entries.append(
                {
                    "run_id": run_id,
                    "trace_entry": trace_entry,
                    "node": node,
                    "node_result": node_result,
                    "private_memory_enabled": private_memory_enabled,
                }
            )
            return {"entry_id": f"wm-{len(self.working_entries)}"}

        async def persist_run_artifacts(self, *, run_id, task, final_output, critic_final):
            payload = {
                "run_summary": {"text": "完成总结", "key_points": ["先查持仓"], "receipt_command_ids": list(final_output.get("receipt_command_ids") or [])},
                "summary_entry": {"entry_id": "summary-1"},
                "lesson_entry": {"entry_id": "lesson-1", "kind": "lesson", "memory_type": "procedural", "content": {"text": "先查持仓再查风险"}},
                "long_term_experience": {"entry_id": "exp-1", "kind": "semantic_case", "memory_type": "semantic"},
                "rejected_experience": {},
                "memory_policy": {"accepted": True, "confidence": 0.95},
            }
            self.persisted_runs[run_id] = payload
            return payload

        async def save_run_context(self, *, run_id, event_id, data):
            self.saved_contexts[run_id] = {"run_id": run_id, "event_id": event_id, "data": data}

        async def get_run_summary(self, run_id):
            persisted = self.persisted_runs.get(run_id, {})
            return persisted.get("run_summary")

        async def list_recent(self, *, agent_id, scope, run_id=None, limit=50, **kwargs):
            if run_id is None:
                return []
            return [
                {
                    "entry_id": "wm-1",
                    "kind": "working_memory",
                    "memory_type": "episodic",
                    "run_id": run_id,
                    "content": {"text": "step s1 completed"},
                }
            ]

        async def build_resume_payload(self, *, run_id, resume_from_step_id=None):
            context = self.saved_contexts.get(run_id)
            if context is None:
                return None
            return {
                "run_id": run_id,
                "task_graph": context["data"]["task_graph"],
                "execution_state": context["data"]["task_graph_execution"],
                "resume_from_step_id": resume_from_step_id or context["data"]["task_graph_execution"].get("failed_step_id"),
                "memory_state": await self.list_recent(agent_id="orchestrator", scope="shared", run_id=run_id),
                "shared_memory_board": context["data"].get("shared_memory_board", []),
                "private_memory_state": context["data"].get("private_memory_state", {}),
                "run_summary": await self.get_run_summary(run_id),
            }

    fake_store = _FakeMemoryStore()
    workflow = ProactiveMultiAgentWorkflow()
    calls = {"engineer": 0, "analyst": 0}
    seen_resume_context: dict[str, object] = {}

    async def _noop():
        return None

    async def _fake_intent(*, task):
        return ProactiveAgentResult(ok=True, output={"primary_intent_type": "resume_analysis"})

    async def _fake_critic(*, task, orchestrator, receipts=None, final_output=None, phase="plan_review"):
        return ProactiveAgentResult(
            ok=True,
            output={
                "ok": True,
                "issues": [],
                "suggested_fixes": [],
                "run_summary": {"text": f"critic_{phase}", "key_points": ["先查持仓"], "receipt_command_ids": []},
            },
        )

    async def _fake_engineer(*, task, context=None):
        calls["engineer"] += 1
        return ProactiveAgentResult(ok=True, output={"summary": "系统侧完成"})

    async def _fake_analyst_bad(*, task, context=None):
        calls["analyst"] += 1
        raise ValueError("invalid param: severity")

    async def _fake_analyst_fixed(*, task, context=None):
        calls["analyst"] += 1
        seen_resume_context["resume_context"] = (context or {}).get("resume_context")
        return ProactiveAgentResult(ok=True, output={"report": "恢复后业务分析完成"})

    workflow.start_agents = _noop
    workflow._intent_agent.recognize = _fake_intent
    workflow._critic_agent.review = _fake_critic
    workflow._engineer_agent.analyze_task = _fake_engineer
    workflow._analyst_agent.analyze_task = _fake_analyst_bad

    with patch("riskmonitor_multiagent.orchestration.proactive_workflow.get_memory_store", return_value=fake_store):
        first = asyncio.run(
            workflow.run(
                {
                    "task_id": "resume-run-1",
                    "source": "human",
                    "payload": {"content": "先失败后从 run_id 恢复"},
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

        first_run_id = first.get("run_id")
        assert first.get("status") == "failed"
        assert len(fake_store.working_entries) >= 1
        assert isinstance(first.get("run_summary"), dict)
        assert (first.get("procedural_lesson") or {}).get("kind") == "lesson"

        saved_context = fake_store.saved_contexts[first_run_id]["data"]
        for node in (saved_context.get("task_graph") or {}).get("nodes", []):
            if node.get("step_id") == "s2":
                node["params"] = {"severity": "HIGH"}

        workflow._analyst_agent.analyze_task = _fake_analyst_fixed
        second = asyncio.run(
            workflow.run(
                {
                    "task_id": "resume-run-1",
                    "source": "human",
                    "payload": {"content": "先失败后从 run_id 恢复"},
                    "resume": {
                        "run_id": first_run_id,
                    },
                }
            )
        )

    second_exec = second.get("task_graph_execution") or {}
    assert second.get("status") == "completed"
    assert calls["engineer"] == 1
    assert calls["analyst"] == 2
    assert second_exec.get("resume_history")[0].get("resume_from_step_id") == "s2"
    assert len(second.get("resume_memory_state") or []) == 1
    assert len(second.get("memory_hits") or []) == 2
    assert (second.get("planning_memory") or {}).get("resume_memory_state_count") == 1
    assert (second.get("run_summary") or {}).get("text") == "完成总结"
    assert isinstance(seen_resume_context.get("resume_context"), dict)
    assert len((seen_resume_context.get("resume_context") or {}).get("memory_state") or []) == 1


def test_proactive_workflow_omits_memory_fields_when_memory_disabled():
    class _FailIfCalledStore:
        async def retrieve_for_planning(self, *args, **kwargs):
            raise AssertionError("memory store should not be used when memory is disabled")

    workflow = ProactiveMultiAgentWorkflow()

    async def _noop():
        return None

    async def _fake_intent(*, task):
        return ProactiveAgentResult(ok=True, output={"primary_intent_type": "parallel_analysis"})

    async def _fake_orchestrate(*, task, context=None):
        assert "memory" not in (context or {})
        return ProactiveAgentResult(
            ok=True,
            output={
                "plan_steps": [
                    {"kind": "finalize", "step_id": "s1", "reason": "直接结束", "instruction": "输出结论"},
                ],
            },
        )

    async def _fake_critic(*, task, orchestrator, receipts=None, final_output=None, phase="plan_review"):
        return ProactiveAgentResult(ok=True, output={"ok": True, "issues": [], "suggested_fixes": [], "run_summary": {"text": "ok", "key_points": [], "receipt_command_ids": []}})

    workflow.start_agents = _noop
    workflow._intent_agent.recognize = _fake_intent
    workflow._orchestrator_agent.orchestrate = _fake_orchestrate
    workflow._critic_agent.review = _fake_critic

    with patch("riskmonitor_multiagent.orchestration.proactive_workflow.get_memory_store", return_value=_FailIfCalledStore()):
        result = asyncio.run(
            workflow.run(
                {
                    "task_id": "memory-off-1",
                    "source": "human",
                    "payload": {"content": "关闭 memory 模式"},
                    "memory_enabled": False,
                }
            )
        )

    assert result.get("status") == "completed"
    assert "memory_hits" not in result
    assert "planning_memory" not in result


def test_proactive_workflow_disables_private_memory_only():
    class _FakeMemoryStore:
        def __init__(self) -> None:
            self.private_flags = []

        async def append(self, entry, **kwargs):
            del kwargs
            return dict(entry)

        async def retrieve_for_planning(self, *, task, intent=None, limit=5):
            del intent, limit
            assert task.get("private_memory_enabled") is False
            return {
                "hits": [{"entry_id": "mem-1", "kind": "lesson", "memory_type": "procedural", "content": {"text": "先查持仓"}}],
                "summary": {"hit_count": 1, "texts": ["[procedural/lesson] 先查持仓"]},
                "shared_board": [{"entry_id": "board-1", "agent_role": "orchestrator"}],
                "private_memory_state": {},
            }

        async def record_working_memory(self, *, run_id, task, trace_entry, node=None, node_result=None, private_memory_enabled=True):
            del run_id, task, trace_entry, node, node_result
            self.private_flags.append(private_memory_enabled)
            return {"entry_id": f"wm-{len(self.private_flags)}"}

        async def persist_run_artifacts(self, *, run_id, task, final_output, critic_final):
            del run_id, task, final_output, critic_final
            return {
                "run_summary": {"text": "done", "key_points": [], "receipt_command_ids": []},
                "summary_entry": {"entry_id": "summary-1"},
                "lesson_entry": {"entry_id": "lesson-1", "kind": "lesson", "memory_type": "procedural"},
                "long_term_experience": {"entry_id": "exp-1", "kind": "semantic_case", "memory_type": "semantic"},
                "memory_policy": {"accepted": True, "confidence": 0.9},
            }

        async def save_run_context(self, *, run_id, event_id, data):
            del run_id, event_id, data

        async def persist_approval_memory(self, *, run_id, task, approval_records):
            del run_id, task, approval_records
            return []

    fake_store = _FakeMemoryStore()
    workflow = ProactiveMultiAgentWorkflow()

    async def _noop():
        return None

    async def _fake_intent(*, task):
        return ProactiveAgentResult(ok=True, output={"primary_intent_type": "parallel_analysis"})

    async def _fake_orchestrate(*, task, context=None):
        return ProactiveAgentResult(
            ok=True,
            output={
                "plan_steps": [
                    {"kind": "delegate", "step_id": "s1", "reason": "系统分析", "target_agent": "system_engineer", "instruction": "分析系统影响"},
                    {"kind": "finalize", "step_id": "s2", "reason": "汇总", "instruction": "输出结论"},
                ],
            },
        )

    async def _fake_critic(*, task, orchestrator, receipts=None, final_output=None, phase="plan_review"):
        del task, orchestrator, receipts, final_output, phase
        return ProactiveAgentResult(ok=True, output={"ok": True, "issues": [], "suggested_fixes": [], "run_summary": {"text": "ok", "key_points": [], "receipt_command_ids": []}})

    async def _fake_engineer(*, task, context=None):
        del task, context
        return ProactiveAgentResult(ok=True, output={"summary": "系统侧完成"})

    workflow.start_agents = _noop
    workflow._intent_agent.recognize = _fake_intent
    workflow._orchestrator_agent.orchestrate = _fake_orchestrate
    workflow._critic_agent.review = _fake_critic
    workflow._engineer_agent.analyze_task = _fake_engineer

    with patch("riskmonitor_multiagent.orchestration.proactive_workflow.get_memory_store", return_value=fake_store):
        result = asyncio.run(
            workflow.run(
                {
                    "task_id": "private-disabled-1",
                    "source": "human",
                    "payload": {"content": "关闭 private memory 保留 shared memory"},
                    "memory_enabled": True,
                    "private_memory_enabled": False,
                }
            )
        )

    assert result.get("status") == "completed"
    assert result.get("shared_memory_board") == [{"entry_id": "board-1", "agent_role": "orchestrator"}]
    assert result.get("private_memory_state") == {}
    assert fake_store.private_flags and all(flag is False for flag in fake_store.private_flags)


def test_proactive_workflow_resumes_pending_approval_from_blocked_step():
    class _FakeMemoryStore:
        def __init__(self) -> None:
            self.working_entries = []
            self.approval_entries = []
            self.saved_contexts = {}
            self.persisted_runs = {}

        async def append(self, entry, **kwargs):
            del kwargs
            return dict(entry)

        async def retrieve_for_planning(self, *, task, intent=None, limit=5):
            return {"hits": [], "summary": {}}

        async def record_working_memory(self, *, run_id, task, trace_entry, node=None, node_result=None, private_memory_enabled=True):
            self.working_entries.append(
                {
                    "run_id": run_id,
                    "trace_entry": trace_entry,
                    "node": node,
                    "node_result": node_result,
                    "private_memory_enabled": private_memory_enabled,
                }
            )
            return {"entry_id": f"wm-{len(self.working_entries)}"}

        async def persist_run_artifacts(self, *, run_id, task, final_output, critic_final):
            payload = {
                "run_summary": {"text": "审批后完成", "key_points": ["resume"], "receipt_command_ids": []},
                "summary_entry": {"entry_id": "summary-approval"},
                "lesson_entry": {"entry_id": "lesson-approval", "kind": "lesson", "memory_type": "procedural"},
            }
            self.persisted_runs[run_id] = payload
            return payload

        async def persist_approval_memory(self, *, run_id, task, approval_records):
            self.approval_entries.extend(list(approval_records))
            return [{"entry_id": f"approval-{len(self.approval_entries)}"}]

        async def save_run_context(self, *, run_id, event_id, data):
            self.saved_contexts[run_id] = {"run_id": run_id, "event_id": event_id, "data": data}

        async def get_run_summary(self, run_id):
            persisted = self.persisted_runs.get(run_id, {})
            return persisted.get("run_summary")

        async def list_recent(self, *, agent_id, scope, run_id=None, limit=50, **kwargs):
            del agent_id, scope, limit, kwargs
            if run_id is None:
                return []
            return [
                {
                    "entry_id": "approval-mem-1",
                    "kind": "approval",
                    "memory_type": "episodic",
                    "run_id": run_id,
                    "content": {"text": "pending approval"},
                }
            ]

        async def build_resume_payload(self, *, run_id, resume_from_step_id=None):
            context = self.saved_contexts.get(run_id)
            if context is None:
                return None
            return {
                "run_id": run_id,
                "task_graph": context["data"]["task_graph"],
                "execution_state": context["data"]["task_graph_execution"],
                "resume_from_step_id": (
                    resume_from_step_id
                    or context["data"]["task_graph_execution"].get("blocked_step_id")
                    or context["data"]["task_graph_execution"].get("failed_step_id")
                ),
                "memory_state": await self.list_recent(agent_id="orchestrator", scope="shared", run_id=run_id),
                "run_summary": await self.get_run_summary(run_id),
            }

    fake_store = _FakeMemoryStore()
    workflow = ProactiveMultiAgentWorkflow()
    calls = {"engineer": 0, "analyst": 0}

    async def _noop():
        return None

    async def _fake_intent(*, task):
        return ProactiveAgentResult(ok=True, output={"primary_intent_type": "approval_resume"})

    async def _fake_critic(*, task, orchestrator, receipts=None, final_output=None, phase="plan_review"):
        del task, orchestrator, receipts, final_output
        return ProactiveAgentResult(
            ok=True,
            output={
                "ok": True,
                "issues": [],
                "suggested_fixes": [],
                "run_summary": {"text": f"critic_{phase}", "key_points": ["approval"], "receipt_command_ids": []},
            },
        )

    async def _fake_engineer(*, task, context=None):
        calls["engineer"] += 1
        return ProactiveAgentResult(ok=True, output={"summary": "系统侧已经执行"})

    async def _fake_analyst(*, task, context=None):
        calls["analyst"] += 1
        return ProactiveAgentResult(ok=True, output={"report": "审批后业务侧继续执行"})

    workflow.start_agents = _noop
    workflow._intent_agent.recognize = _fake_intent
    workflow._critic_agent.review = _fake_critic
    workflow._engineer_agent.analyze_task = _fake_engineer
    workflow._analyst_agent.analyze_task = _fake_analyst

    graph = {
        "schema_version": "task_graph.v1",
        "nodes": [
            {"step_id": "s1", "kind": "delegate", "reason": "系统分析", "status": "pending", "target_agent": "system_engineer"},
            {
                "step_id": "s2",
                "parent_id": "s1",
                "kind": "delegate",
                "reason": "高风险步骤等待审批",
                "status": "pending",
                "target_agent": "risk_analyst",
                "approval": {
                    "required": True,
                    "reason": "需要人工确认风险影响范围",
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

    with patch("riskmonitor_multiagent.orchestration.proactive_workflow.get_memory_store", return_value=fake_store):
        first = asyncio.run(
            workflow.run(
                {
                    "task_id": "approval-resume-1",
                    "source": "human",
                    "payload": {"content": "需要审批后继续"},
                    "resume": {
                        "task_graph": graph,
                        "execution_state": {},
                    },
                }
            )
        )

        first_run_id = first.get("run_id")
        assert first.get("status") == "blocked"
        assert first.get("approval_trace")[0].get("level") == "step"
        assert first.get("task_graph_execution", {}).get("blocked_step_id") == "s2"
        assert len(fake_store.approval_entries) == 1
        assert calls["engineer"] == 1
        assert calls["analyst"] == 0

        second = asyncio.run(
            workflow.run(
                {
                    "task_id": "approval-resume-1",
                    "source": "human",
                    "payload": {"content": "需要审批后继续"},
                    "resume": {
                        "run_id": first_run_id,
                        "approval_decision": {
                            "state": "approved",
                            "actor": "reviewer",
                            "note": "审批通过",
                            "reason": "风险影响已确认",
                            "risk_level": "HIGH",
                            "impact_scope": ["desk:eq"],
                            "recommended_action": "review_and_resume_step",
                        },
                    },
                }
            )
        )

    second_exec = second.get("task_graph_execution") or {}
    assert second.get("status") == "completed"
    assert second_exec.get("resume_history")[0].get("resume_from_step_id") == "s2"
    assert calls["engineer"] == 1
    assert calls["analyst"] == 1
    assert "审批后业务侧继续执行" in (second.get("final_output") or {}).get("summary", "")
