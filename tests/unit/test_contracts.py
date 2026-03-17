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
        "ok": True,
        "latency_ms": 12.3,
        "evidence": {"tool": "get_service_metrics"},
        "artifacts": [{"kind": "metrics_snapshot", "ref": "in_memory"}],
        "error": None,
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
