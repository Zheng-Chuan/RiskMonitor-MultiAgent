from __future__ import annotations

from riskmonitor_multiagent.contracts.agent_messages import (
    AGENT_COMMAND_SCHEMA_VERSION,
    AGENT_RECEIPT_SCHEMA_VERSION,
    validate_agent_command,
    validate_agent_receipt,
)
from riskmonitor_multiagent.contracts.agent_outputs import (
    CRITIC_REVIEW_SCHEMA_VERSION,
    ORCHESTRATOR_OUTPUT_SCHEMA_VERSION,
    RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
    SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
    normalize_critic_review,
    normalize_orchestrator_output,
    normalize_risk_analyst_output,
    normalize_system_engineer_output,
    validate_critic_review,
    validate_orchestrator_output,
    validate_risk_analyst_output,
    validate_system_engineer_output,
)
from riskmonitor_multiagent.contracts.intent_output import (
    normalize_intent_output,
    validate_intent_output,
)
from riskmonitor_multiagent.contracts.memory_entry import (
    MemoryEntry,
    _build_trace_ref,
    _infer_memory_type,
    normalize_memory_entry,
    validate_memory_entry,
)
from riskmonitor_multiagent.contracts.run_trace import (
    RUN_TRACE_SCHEMA_VERSION,
    normalize_run_trace,
    validate_run_trace,
)


def test_agent_command_and_receipt_validation_rejects_bad_fields() -> None:
    ok, errors = validate_agent_command(
        {
            "schema_version": "bad",
            "run_id": "",
            "command_id": "",
            "target_agent": "unknown",
            "action": "",
            "params": [],
            "timeout_ms": -1,
            "retry_budget": -1,
            "expected_output_schema": 1,
        }
    )
    assert ok is False
    assert {
        "bad_schema_version",
        "bad_run_id",
        "bad_command_id",
        "bad_target_agent",
        "bad_action",
        "bad_params",
        "bad_timeout_ms",
        "bad_retry_budget",
        "bad_expected_output_schema",
    }.issubset(set(errors))

    ok, errors = validate_agent_receipt(
        {
            "schema_version": AGENT_RECEIPT_SCHEMA_VERSION,
            "run_id": "",
            "command_id": "",
            "tool_name": "",
            "ok": "yes",
            "target_agent": "unknown",
            "inputs": [],
            "status": "weird",
            "latency_ms": -1,
            "side_effect": "no",
            "approval_state": "bad",
            "evidence": [],
            "artifacts": {},
            "outputs": [],
            "error": 123,
            "output": [],
            "failure_classification": "bad",
            "retry_count": -1,
            "retry_budget": -1,
            "timeout_ms": -1,
            "approval_trace": [],
        }
    )
    assert ok is False
    assert "bad_failure_classification" in errors
    assert "bad_output" in errors


def test_agent_output_normalizers_and_validators_cover_fallbacks() -> None:
    normalized_sys = normalize_system_engineer_output({"latency_ms": "bad"})
    assert normalized_sys["schema_version"] == SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION
    assert normalized_sys["latency_ms"] is None
    assert validate_system_engineer_output(normalized_sys)[0] is True

    normalized_analyst = normalize_risk_analyst_output({"confidence": "bad"})
    assert normalized_analyst["schema_version"] == RISK_ANALYST_OUTPUT_SCHEMA_VERSION
    assert normalized_analyst["confidence"] is None
    assert validate_risk_analyst_output(normalized_analyst)[0] is True

    critic = normalize_critic_review({})
    assert critic["schema_version"] == CRITIC_REVIEW_SCHEMA_VERSION
    assert validate_critic_review(critic)[0] is True
    critic["risk_level"] = "BAD"
    critic["evidence"] = []
    ok, errors = validate_critic_review(critic)
    assert ok is False
    assert "bad_risk_level" in errors
    assert "bad_evidence" in errors


def test_orchestrator_output_detects_binding_and_degraded_errors() -> None:
    out = normalize_orchestrator_output(
        {
            "schema_version": ORCHESTRATOR_OUTPUT_SCHEMA_VERSION,
            "plan_steps": [{"kind": "delegate", "target_agent": "system_engineer"}],
            "commands": [{"command_id": "cmd-1"}],
            "evidence": {"receipt_command_ids": ["cmd-missing"]},
            "degraded": True,
            "degraded_reason": "",
            "degraded_scope": [],
            "task_graph": {"schema_version": "task_graph.v1", "nodes": [], "edges": []},
        }
    )
    ok, errors = validate_orchestrator_output(out)
    assert ok is False
    assert "receipt_binding_mismatch" in errors

    out["evidence"] = {"receipt_command_ids": ["cmd-1"], "fields": ["task.payload.content"]}
    out["degraded_reason"] = "fallback"
    out["degraded_scope"] = ["orchestrator"]
    ok, errors = validate_orchestrator_output(out)
    assert ok is True, errors


def test_intent_output_validation_and_normalization_edge_cases() -> None:
    ok, errors = validate_intent_output(
        {
            "schema_version": "intent_output.v1",
            "primary_intent_type": "",
            "intents": [{"intent_type": "", "confidence": 2, "slots": []}, "bad"],
            "risk_level": "UNKNOWN",
            "permission_requirements": {"side_effects": "yes", "requires_human_approval": "no", "allowed_tools": "bad"},
            "disambiguation": {"has_multiple": True, "explanation": ""},
            "evidence": [],
        }
    )
    assert ok is False
    assert "unsupported_schema_version" in errors
    assert "intent_0_bad_confidence" in errors
    assert "intent_1_not_dict" in errors

    normalized = normalize_intent_output({"intents": [{"intent_type": "b", "confidence": 0.2}, {"intent_type": "a", "confidence": 0.9}]})
    assert normalized["primary_intent_type"] == "a"
    assert normalized["disambiguation"]["has_multiple"] is True
    assert normalized["disambiguation"]["notes"] == []


def test_memory_entry_helpers_and_roundtrip() -> None:
    assert _infer_memory_type("lesson") == "procedural"
    assert _infer_memory_type("knowledge") == "semantic"
    assert _infer_memory_type("other") == "episodic"
    assert _build_trace_ref({"run_id": "run-1", "entry_id": "mem-1"}) == {"run_id": "run-1", "entry_id": "mem-1"}

    normalized = normalize_memory_entry(
        {
            "entry_id": "mem-1",
            "ts_ms": 1,
            "agent_id": "risk_analyst",
            "scope": "bad",
            "kind": "lesson",
            "memory_type": "bad",
            "content": [],
            "confidence": "bad",
            "created_by": "",
            "trace_ref": [],
            "tags": "bad",
            "run_id": "run-1",
        }
    )
    assert normalized["scope"] == "shared"
    assert normalized["memory_type"] == "procedural"
    assert normalized["content"] == {}
    assert normalized["confidence"] == 1.0
    assert normalized["tags"] is None
    assert validate_memory_entry(normalized)[0] is True

    entry = MemoryEntry.from_dict(normalized)
    assert entry.to_dict()["entry_id"] == "mem-1"


def test_run_trace_normalization_and_validation_errors() -> None:
    normalized = normalize_run_trace(
        {
            "run_id": "run-1",
            "entry_type": "system_event",
            "entries": [
                {
                    "category": "task",
                    "trace_type": "task_started",
                    "timestamp_ms": "12",
                    "summary": None,
                    "payload": None,
                },
                "bad",
            ],
        }
    )
    assert normalized["schema_version"] == RUN_TRACE_SCHEMA_VERSION
    assert normalized["entries"][0]["timestamp_ms"] == 12

    ok, errors = validate_run_trace(
        {
            "schema_version": "bad",
            "run_id": "",
            "entry_type": "",
            "status": "",
            "version_snapshot": [],
            "failure_summary": [],
            "entries": [
                {
                    "category": "bad",
                    "trace_type": "",
                    "timestamp_ms": "bad",
                    "summary": [],
                    "payload": [],
                }
            ],
        }
    )
    assert ok is False
    assert "bad_run_trace_schema_version" in errors
    assert "bad_run_trace_entry_category" in errors
