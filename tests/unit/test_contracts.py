import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.contracts.agent_outputs import (
    MANAGER_OUTPUT_SCHEMA_VERSION,
    RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
    SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
    validate_manager_output,
    validate_risk_analyst_output,
    validate_system_engineer_output,
)
from riskmonitor_multiagent.contracts.agent_messages import (
    AGENT_COMMAND_SCHEMA_VERSION,
    AGENT_RECEIPT_SCHEMA_VERSION,
    validate_agent_command,
    validate_agent_receipt,
)
from riskmonitor_multiagent.contracts.risk_event import (
    RISK_EVENT_SCHEMA_VERSION,
    build_breach_event,
    normalize_cdc_event,
    validate_risk_event,
)


def test_normalize_cdc_event_is_valid_and_deterministic_event_id():
    raw = {"desk": "Equity Derivatives", "delta": 123.0, "__op": "u", "__ts_ms": 123}
    ev1 = normalize_cdc_event(
        raw_record=raw,
        topic="risk.positions.cdc",
        partition=1,
        offset=9,
        message_ts_ms=1700000000000,
    )
    ev2 = normalize_cdc_event(
        raw_record=raw,
        topic="risk.positions.cdc",
        partition=1,
        offset=9,
        message_ts_ms=1700000000000,
    )

    assert ev1.event_id == "risk.positions.cdc:1:9"
    assert ev1.event_id == ev2.event_id
    assert ev1.schema_version == RISK_EVENT_SCHEMA_VERSION

    ok, errors = validate_risk_event(ev1.to_dict())
    assert ok, errors


def test_build_breach_event_is_valid_and_links_to_source():
    raw = {"desk": "Commodities", "delta": 999.0}
    source = normalize_cdc_event(
        raw_record=raw,
        topic="risk.positions.cdc",
        partition=0,
        offset=1,
        message_ts_ms=1700000000000,
    )
    breach = build_breach_event(source_event=source, desk="Commodities", exposure=60000.0, threshold=50000.0, now_ms=1700000000100)
    breach_dict = breach.to_dict()

    assert breach_dict["event_id"].endswith(":breach")
    assert breach_dict["causation_id"] == source.event_id
    assert breach_dict["correlation_id"] == source.correlation_id
    assert breach_dict["producer"] == "sentinel"
    assert breach_dict["payload"]["signal_type"] == "desk_exposure_breach"

    ok, errors = validate_risk_event(breach_dict)
    assert ok, errors


def test_agent_output_schemas_validate_minimal_outputs():
    syseng = {
        "schema_version": SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
        "system_issue": False,
        "reason": "ok",
        "latency_ms": None,
        "evidence": {"event_id": "x"},
    }
    ok, errors = validate_system_engineer_output(syseng)
    assert ok, errors

    analyst = {
        "schema_version": RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
        "report": "ok",
        "key_facts": {"desk": "x"},
        "confidence": 0.8,
        "evidence": {"event_id": "x"},
    }
    ok, errors = validate_risk_analyst_output(analyst)
    assert ok, errors

    manager = {
        "schema_version": MANAGER_OUTPUT_SCHEMA_VERSION,
        "decision": "WATCH",
        "action": "do",
        "rationale": "why",
        "commands": None,
        "evidence": {"event_id": "x", "fields": ["event.event_id"]},
    }
    ok, errors = validate_manager_output(manager)
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
