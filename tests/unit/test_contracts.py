import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.contracts.agent_outputs import (
    ORCHESTRATOR_OUTPUT_SCHEMA_VERSION,
    RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
    SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
    normalize_orchestrator_output,
    validate_orchestrator_output,
    validate_risk_analyst_output,
    validate_system_engineer_output,
)
from riskmonitor_multiagent.contracts.agent_messages import (
    AGENT_COMMAND_SCHEMA_VERSION,
    AGENT_RECEIPT_SCHEMA_VERSION,
    validate_agent_command,
    validate_agent_receipt,
)
from riskmonitor_multiagent.contracts.task_graph import (
    TASK_GRAPH_SCHEMA_VERSION,
    append_replan_subgraph,
    build_task_graph_from_plan_steps,
    validate_task_graph,
)
def test_agent_output_schemas_validate_minimal_outputs():
    syseng = {
        "schema_version": SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
        "system_issue": False,
        "reason": "ok",
        "latency_ms": None,
        "evidence": {"fields": ["task.payload.content"]},
    }
    ok, errors = validate_system_engineer_output(syseng)
    assert ok, errors

    analyst = {
        "schema_version": RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
        "report": "ok",
        "key_facts": {"desk": "x"},
        "confidence": 0.8,
        "evidence": {"fields": ["task.payload.content"]},
    }
    ok, errors = validate_risk_analyst_output(analyst)
    assert ok, errors


def test_agent_command_and_receipt_validate_minimal_messages():
    cmd = {
        "schema_version": AGENT_COMMAND_SCHEMA_VERSION,
        "run_id": "run-1",
        "command_id": "cmd-1",
        "target_agent": "system_engineer",
        "action": "collect_metrics",
        "params": {"tool": "get_service_metrics"},
        "timeout_ms": 5000,
        "expected_output_schema": "tool_result.v1",
    }
    ok, errors = validate_agent_command(cmd)
    assert ok, errors

    rcp = {
        "schema_version": AGENT_RECEIPT_SCHEMA_VERSION,
        "run_id": "run-1",
        "command_id": "cmd-1",
        "target_agent": "system_engineer",
        "tool_name": "collect_metrics",
        "inputs": {"tool": "get_service_metrics"},
        "outputs": {"ok": True},
        "status": "completed",
        "ok": True,
        "latency_ms": 12.3,
        "evidence": {"tool": "get_service_metrics"},
        "artifacts": [{"kind": "metrics_snapshot", "ref": "in_memory"}],
        "error": None,
        "side_effect": False,
        "approval_state": "not_required",
        "output": {"ok": True},
    }
    ok, errors = validate_agent_receipt(rcp)
    assert ok, errors


def test_orchestrator_plan_step_requires_reason():
    out = {
        "schema_version": ORCHESTRATOR_OUTPUT_SCHEMA_VERSION,
        "intent": {"type": "unknown", "confidence": 0.1, "slots": {}},
        "plan_steps": [
            {"kind": "delegate", "step_id": "s1", "target_agent": "system_engineer", "instruction": "检查系统"},
        ],
        "commands": None,
        "evidence": {"fields": ["task.payload.content"]},
        "degraded": False,
    }
    ok, errors = validate_orchestrator_output(out)
    assert ok is True


def test_orchestrator_normalize_backfills_step_reason():
    out = normalize_orchestrator_output(
        {
            "schema_version": ORCHESTRATOR_OUTPUT_SCHEMA_VERSION,
            "plan_steps": [
                {"kind": "delegate", "target_agent": "risk_analyst", "instruction": "分析业务影响"},
            ],
            "evidence": {"fields": ["task.payload.content"]},
            "degraded": False,
        }
    )
    steps = out.get("plan_steps")
    assert isinstance(steps, list) and steps
    assert isinstance(steps[0].get("reason"), str) and steps[0].get("reason")
    task_graph = out.get("task_graph")
    assert isinstance(task_graph, dict)
    assert task_graph.get("schema_version") == TASK_GRAPH_SCHEMA_VERSION
    nodes = task_graph.get("nodes")
    assert isinstance(nodes, list) and len(nodes) == 1
    assert nodes[0].get("step_id") == steps[0].get("step_id")


def test_task_graph_validate_minimal_graph():
    graph = {
        "schema_version": TASK_GRAPH_SCHEMA_VERSION,
        "nodes": [
            {
                "step_id": "s1",
                "parent_id": None,
                "kind": "delegate",
                "status": "pending",
                "reason": "需要专家分析",
                "evidence": {"fields": ["task.payload.content"]},
                "target_agent": "system_engineer",
            },
            {
                "step_id": "s2",
                "parent_id": "s1",
                "kind": "finalize",
                "status": "pending",
                "reason": "最后收敛输出",
                "evidence": {"fields": ["task.payload.content"]},
            },
        ],
        "edges": [{"from_step_id": "s1", "to_step_id": "s2", "condition": "always"}],
    }
    ok, errors = validate_task_graph(graph)
    assert ok, errors


def test_task_graph_tool_call_requires_tool_name():
    graph = {
        "schema_version": TASK_GRAPH_SCHEMA_VERSION,
        "nodes": [
            {
                "step_id": "s1",
                "kind": "tool_call",
                "status": "pending",
                "reason": "采集指标",
                "evidence": {"fields": ["task.payload.content"]},
                "params": {},
            }
        ],
        "edges": [],
    }
    ok, errors = validate_task_graph(graph)
    assert ok is False
    assert "bad_task_graph_tool_name" in errors


def test_task_graph_finalize_depends_on_all_prior_branches():
    graph = build_task_graph_from_plan_steps(
        [
            {"kind": "delegate", "step_id": "s1", "reason": "系统侧", "target_agent": "system_engineer"},
            {"kind": "delegate", "step_id": "s2", "reason": "业务侧", "target_agent": "risk_analyst"},
            {"kind": "finalize", "step_id": "s3", "reason": "汇总输出"},
        ]
    )
    edges = graph.get("edges") or []
    refs = {(edge.get("from_step_id"), edge.get("to_step_id")) for edge in edges}
    assert ("s1", "s3") in refs
    assert ("s2", "s3") in refs
    assert ("s1", "s2") not in refs


def test_append_replan_subgraph_inserts_replan_node_and_rewires_new_steps():
    base = build_task_graph_from_plan_steps(
        [
            {"kind": "delegate", "step_id": "s1", "reason": "系统侧", "target_agent": "system_engineer"},
            {"kind": "finalize", "step_id": "s2", "reason": "初版汇总"},
        ]
    )
    new = build_task_graph_from_plan_steps(
        [
            {"kind": "delegate", "step_id": "s1", "reason": "改走业务侧", "target_agent": "risk_analyst"},
            {"kind": "finalize", "step_id": "s2", "reason": "重规划后汇总"},
        ]
    )
    merged = append_replan_subgraph(base, new, reason="critic rejected", replan_index=1)

    ok, errors = validate_task_graph(merged)
    assert ok, errors

    nodes = merged.get("nodes") or []
    step_ids = {node.get("step_id") for node in nodes}
    assert "rp1" in step_ids
    assert "rp1_s1" in step_ids
    assert "rp1_s2" in step_ids

    edges = merged.get("edges") or []
    refs = {(edge.get("from_step_id"), edge.get("to_step_id")) for edge in edges}
    assert ("s2", "rp1") in refs
    assert ("rp1", "rp1_s1") in refs
    assert ("rp1_s1", "rp1_s2") in refs


def test_orchestrator_receipt_binding_mismatch_is_rejected():
    out = {
        "schema_version": ORCHESTRATOR_OUTPUT_SCHEMA_VERSION,
        "intent": {"type": "unknown", "confidence": 0.1, "slots": {}},
        "plan_steps": [{"kind": "finalize", "step_id": "s1", "reason": "完成总结", "instruction": "输出结论"}],
        "commands": [{"command_id": "cmd-ok", "target_agent": "system_engineer", "action": "collect_metrics", "params": {}}],
        "evidence": {"receipt_command_ids": ["cmd-missing"]},
        "degraded": False,
    }
    ok, errors = validate_orchestrator_output(out)
    assert ok is False
    assert "receipt_binding_mismatch" in errors


def test_analyst_requires_evidence_references():
    analyst = {
        "schema_version": RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
        "report": "ok",
        "key_facts": {"desk": "x"},
        "confidence": 0.8,
        "evidence": {"event_id": "x"},
    }
    ok, errors = validate_risk_analyst_output(analyst)
    assert ok is False
    assert "missing_key_risk_analyst_evidence_refs" in errors
