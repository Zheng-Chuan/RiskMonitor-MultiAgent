import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
for path in (_PROJECT_ROOT, _PROJECT_ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from eval.core.evaluator import Evaluator, EvaluationResult, ExecutionTrace, TestCase as EvalTestCase
from eval.core.metrics import EfficiencyMetrics, MemoryMetrics, OverallMetrics
from eval.core.report import ReportGenerator
from riskmonitor_multiagent.observability.run_trace import build_run_trace_snapshot


def test_evaluator_computes_tool_rates_from_real_receipts():
    evaluator = Evaluator(llm_judge_enabled=False)
    case = EvalTestCase(
        case_id="case-1",
        category="tool",
        difficulty="medium",
        task={},
        ground_truth={},
        evaluation={},
        risk_assessment={"requires_approval": True},
    )
    trace = ExecutionTrace(case_id="case-1")
    trace.tool_calls = [
        {
            "tool_name": "collect_metrics",
            "ok": True,
            "retry_count": 0,
            "failure_classification": None,
            "side_effect": False,
            "approval_state": "not_required",
            "approval_trace": {"required": False, "current_state": "not_required", "history": []},
        },
        {
            "tool_name": "collect_metrics",
            "ok": False,
            "retry_count": 1,
            "failure_classification": "timeout",
            "error": "tool_timeout",
            "side_effect": False,
            "approval_state": "not_required",
            "approval_trace": {"required": False, "current_state": "not_required", "history": []},
        },
        {
            "tool_name": "submit_alerts",
            "ok": False,
            "status": "blocked",
            "retry_count": 0,
            "failure_classification": "permission",
            "side_effect": True,
            "approval_state": "pending",
            "approval_trace": {"required": True, "current_state": "pending", "history": [{"state": "pending"}]},
        },
    ]

    efficiency = evaluator._compute_efficiency(case, trace)
    assert efficiency.tool_call_count == 3
    assert round(efficiency.tool_success_rate, 4) == round(1 / 3, 4)
    assert round(efficiency.tool_timeout_rate, 4) == round(1 / 3, 4)
    assert round(efficiency.tool_retry_rate, 4) == round(1 / 3, 4)

    tool_risk = evaluator._compute_tool_risk(case, trace, llm_scores={})
    assert tool_risk.approval_flow_compliance >= 0.9


def test_markdown_report_includes_real_tool_metrics():
    report = ReportGenerator().generate_markdown_report(
        EvaluationResult(
            run_id="eval-1",
            timestamp="2026-05-02T00:00:00Z",
            config={},
            total_cases=1,
            passed_cases=1,
            failed_cases=0,
            overall_metrics=OverallMetrics(
                efficiency=EfficiencyMetrics(
                    tool_call_count=3,
                    tool_call_efficiency=0.5,
                    tool_success_rate=1 / 3,
                    tool_timeout_rate=1 / 3,
                    tool_retry_rate=1 / 3,
                ),
                memory=MemoryMetrics(
                    memory_hit_rate=1.0,
                    memory_usefulness=0.4,
                    resume_success_rate=1.0,
                ),
            ),
        )
    )

    assert "Tool Success Rate: 33.33%" in report
    assert "Tool Timeout Rate: 33.33%" in report
    assert "Tool Retry Rate: 33.33%" in report
    assert "Memory Hit Rate: 100.00%" in report
    assert "Memory Usefulness: 40.00%" in report
    assert "Resume Success Rate: 100.00%" in report


def test_evaluator_computes_memory_metrics_from_real_trace():
    evaluator = Evaluator(llm_judge_enabled=False)
    case = EvalTestCase(
        case_id="case-memory-1",
        category="memory",
        difficulty="medium",
        task={},
        ground_truth={},
        evaluation={},
    )
    trace = ExecutionTrace(case_id="case-memory-1")
    trace.success = True
    trace.memory_hits = [{"entry_id": "mem-1"}]
    trace.planning_memory = {"hit_count": 1, "texts": ["[procedural/lesson] 先查持仓"]}
    trace.resume_memory_state = [{"entry_id": "wm-1"}]
    trace.final_output = {"summary": "done"}
    trace.agent_outputs = {"task_graph_execution": {"resume_history": [{"resume_from_step_id": "s2"}]}}

    metrics = evaluator._compute_memory(case, trace)
    assert metrics.memory_hit_rate == 1.0
    assert metrics.resume_success_rate == 1.0
    assert metrics.memory_usefulness > 0.0


def test_evaluator_consumes_run_trace_v2_directly():
    evaluator = Evaluator(llm_judge_enabled=False)
    case = EvalTestCase(
        case_id="case-trace-v2-1",
        category="trace",
        difficulty="medium",
        task={"task_id": "task-trace-1"},
        ground_truth={"intent": "investigate", "expected_steps": 1},
        evaluation={},
    )

    run_trace = build_run_trace_snapshot(
        result={
            "status": "completed",
            "run_id": "run-trace-v2-1",
            "entry_type": "user_task",
            "task_id": "task-trace-1",
            "run_context": {"entry_type": "user_task"},
            "intent": {"primary_intent_type": "investigate"},
            "orchestrator_plan": {"plan_steps": [{"step_id": "s1", "reason": "先查风险"}]},
            "task_graph": {"schema_version": "task_graph.v1", "nodes": [{"step_id": "s1"}], "edges": []},
            "task_graph_execution": {
                "trace": [
                    {"step_id": "s1", "kind": "tool_call", "status": "completed", "started_at_ms": 1, "finished_at_ms": 3, "target_agent": "system_engineer"}
                ],
                "resume_history": [],
            },
            "receipts": [
                {
                    "command_id": "cmd-1",
                    "tool_name": "query_alerts",
                    "ok": True,
                    "status": "completed",
                    "approval_state": "not_required",
                    "approval_trace": {"required": False, "current_state": "not_required", "history": []},
                }
            ],
            "memory_hits": [{"entry_id": "mem-1", "kind": "analysis", "memory_type": "episodic"}],
            "planning_memory": {"hit_count": 1},
            "run_summary": {"text": "done"},
            "final_output": {"summary": "完成"},
            "errors": [],
            "tokens_total": 12,
        }
    ).to_dict()

    async def _fake_runner(*, task):
        del task
        return {
            "ok": True,
            "result": {
                "run_id": "run-trace-v2-1",
                "run_trace": run_trace,
            },
        }

    case_result = asyncio.run(evaluator.evaluate_case(case, _fake_runner))

    assert case_result.success is True
    assert case_result.trace is not None
    assert case_result.trace.intent.get("primary_intent_type") == "investigate"
    assert len(case_result.trace.tool_calls) == 1
    assert len(case_result.trace.memory_hits) == 1
    assert case_result.trace.final_output.get("summary") == "完成"


def test_evaluator_computes_behavior_metrics_from_real_trace():
    evaluator = Evaluator(llm_judge_enabled=False)
    case = EvalTestCase(
        case_id="case-behavior-1",
        category="approval",
        difficulty="hard",
        task={"task_id": "task-behavior-1"},
        ground_truth={"intent": "investigate", "expected_tools": ["write_alert"], "expected_steps": 1},
        evaluation={},
        risk_assessment={"requires_approval": True},
        gold_facts={"required_terms": ["风险", "告警"]},
    )

    run_trace = build_run_trace_snapshot(
        result={
            "status": "completed",
            "run_id": "run-behavior-1",
            "entry_type": "user_task",
            "task_id": "task-behavior-1",
            "run_context": {"entry_type": "user_task"},
            "intent": {"primary_intent_type": "investigate"},
            "orchestrator_plan": {"plan_steps": [{"step_id": "s1", "reason": "先写告警"}]},
            "replan": {"phase": "runtime_replan", "reason": "tool failed"},
            "task_graph": {"schema_version": "task_graph.v1", "nodes": [{"step_id": "s1"}], "edges": []},
            "task_graph_execution": {
                "trace": [
                    {
                        "step_id": "s1",
                        "kind": "tool_call",
                        "status": "completed",
                        "started_at_ms": 1,
                        "finished_at_ms": 3,
                        "target_agent": "system_engineer",
                    }
                ],
                "resume_history": [{"resume_from_step_id": "s1"}],
            },
            "receipts": [
                {
                    "command_id": "cmd-1",
                    "tool_name": "write_alert",
                    "ok": True,
                    "status": "completed",
                    "approval_state": "resumed",
                    "approval_trace": {"required": True, "current_state": "resumed", "history": [{"state": "pending"}, {"state": "approved"}, {"state": "resumed"}]},
                }
            ],
            "approval_trace": [
                {"approval_id": "ap-1", "approval_state": "resumed", "level": "command", "command_id": "cmd-1"}
            ],
            "memory_hits": [{"entry_id": "mem-1", "kind": "analysis", "memory_type": "episodic"}],
            "planning_memory": {"hit_count": 1},
            "run_summary": {"text": "done"},
            "final_output": {"summary": "风险告警完成"},
            "errors": [],
            "tokens_total": 20,
        }
    ).to_dict()

    async def _fake_runner(*, task):
        del task
        return {"ok": True, "result": {"run_id": "run-behavior-1", "run_trace": run_trace}}

    case_result = asyncio.run(evaluator.evaluate_case(case, _fake_runner))
    behavior = case_result.behavior_metrics
    assert behavior.tool_call_count == 1
    assert behavior.approval_count == 1
    assert behavior.replan_count == 1
    assert behavior.memory_hit_count == 1
    assert behavior.receipt_binding_rate == 1.0
    assert behavior.approval_correctness == 1.0
    assert behavior.dangerous_action_block_rate == 1.0


def test_behavior_metrics_do_not_change_when_llm_scores_change():
    evaluator = Evaluator(llm_judge_enabled=False)
    case = EvalTestCase(
        case_id="case-judge-off-1",
        category="memory",
        difficulty="medium",
        task={},
        ground_truth={"intent": "query_positions", "expected_tools": ["query_all_positions"]},
        evaluation={},
        gold_facts={"required_terms": ["头寸"]},
    )
    trace = ExecutionTrace(case_id="case-judge-off-1")
    trace.success = True
    trace.intent = {"primary_intent_type": "query_positions"}
    trace.final_output = {"summary": "头寸汇总"}
    trace.tool_calls = [{"tool_name": "query_all_positions", "ok": True, "approval_state": "not_required"}]
    trace.memory_hits = [{"entry_id": "mem-1"}]

    baseline = evaluator._compute_behavior_metrics(case, trace).to_dict()
    noisy = evaluator._compute_behavior_metrics(case, trace).to_dict()
    assert baseline == noisy
